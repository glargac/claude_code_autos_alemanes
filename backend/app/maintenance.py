"""Tareas de mantenimiento puntuales. Uso (desde backend/, con el entorno virtual):

    python -m app.maintenance purge-damaged [--dry-run]
    python -m app.maintenance fix-models [--dry-run]   # corrige el modelo desde el título donde lo contradice
    python -m app.maintenance verify-stale [--dry-run] [--horas 12]
    python -m app.maintenance backfill-co2 [--dry-run] [--limite N]   # CO2 de los AutoScout24 ya guardados
    python -m app.maintenance crear-usuario NOMBRE      # pide la contraseña; el primero hereda los datos de una sola persona
    python -m app.maintenance listar-usuarios
    python -m app.maintenance cambiar-password NOMBRE   # también cierra sus sesiones abiertas
    python -m app.maintenance backup [--destino DIR] [--conservar N]   # copia consistente de la base y las fotos
    python -m app.maintenance probar-ia          # comprueba la clave y el modelo de IA con una petición mínima
    python -m app.maintenance gemini-models      # lista los modelos de Gemini que acepta tu clave

purge-damaged: quita de la base los anuncios de kleinanzeigen marcados como "Beschädigtes Fahrzeug" que se
guardaron antes de que la búsqueda los excluyera. No toca los que tienen seguimiento (estado, notas o cita).
"""
import argparse
import asyncio

from sqlalchemy import select

from .database import SessionLocal, ensure_columns
from .models import Car, User
from .scrapers.kleinanzeigen import KleinanzeigenScraper
from .services.dedupe import apply_duplicates
from .services.scope import has_followup
from .services.settings_store import get_setting
from .config import DEFAULT_SEARCH
from .services.sync import rescore_all


def fix_models(dry_run: bool = False) -> dict:
    """Corrige `modell` desde el título en los coches guardados donde lo contradice con claridad (ver services/modelo.py).
    Guarda el valor del vendedor en `modell_original`. Después recalcula duplicados y scores."""
    from .services.modelo import corregir_modelo

    ensure_columns()
    with SessionLocal() as db:
        cambios = []
        for car in db.scalars(select(Car)):
            nuevo = corregir_modelo(car.marke, car.modell, car.titel)
            if nuevo and nuevo != car.modell:
                cambios.append((car.id, car.marke, car.modell, nuevo, car.titel[:50]))
                if not dry_run:
                    car.modell_original = car.modell_original or car.modell
                    car.modell = nuevo
        if not dry_run:
            db.commit()
            apply_duplicates(db)
            rescore_all(db)
        return {"corregidos" if not dry_run else "se_corregirían": len(cambios), "detalle": cambios}


async def verify_stale(horas: float = 12, dry_run: bool = False) -> dict:
    """Comprueba en kleinanzeigen los anuncios activos que no se han visto en las últimas `horas` (los que ya no salen
    en las búsquedas) y marca como retirados los borrados o vendidos. Es lo mismo que hace la sync al final, pero
    aplicable ahora; no necesita tener la sync en marcha."""
    from datetime import datetime, timedelta

    ensure_columns()
    with SessionLocal() as db:
        corte = datetime.utcnow() - timedelta(hours=horas)
        rows = db.scalars(select(Car).where(Car.source == "kleinanzeigen", Car.aktiv.is_(True), Car.zuletzt_gesehen < corte)).all()
        gone = await KleinanzeigenScraper().inactive_urls([c.url for c in rows])
        retirados = [c for c in rows if c.url in gone]
        if not dry_run:
            for c in retirados:
                c.aktiv = False
            db.commit()
            apply_duplicates(db)
            rescore_all(db)
        return {"revisados": len(rows), "retirados" if not dry_run else "se_retirarían": len(retirados),
                "con_seguimiento_retirados": [(c.id, c.titel[:40], c.status) for c in retirados if has_followup(c)]}


async def backfill_co2(dry_run: bool = False, limite: int | None = None) -> dict:
    """Pide el detalle de los AutoScout24 activos sin CO₂ guardado (la sync solo lo pide para anuncios nuevos).
    Una petición cada 1,5-3 s; ~800 coches tardan ~30 min. Los que ya no existen se dejan como están."""
    from .scrapers.autoscout24 import AutoScout24Scraper, parse_detail

    ensure_columns()
    with SessionLocal() as db:
        rows = db.scalars(select(Car).where(Car.source == "autoscout24", Car.aktiv.is_(True), Car.co2_gkm.is_(None))).all()[:limite]
        if dry_run:
            return {"se_consultarían": len(rows)}
        s, con_co2, sin_dato, fallos = AutoScout24Scraper(), 0, 0, 0
        async with s._context() as ctx:
            page = await ctx.new_page()
            for i, car in enumerate(rows, 1):
                try:
                    props, final = await s._props(page, car.url, gone_ok=True)
                except Exception as exc:  # un fallo suelto no corta el resto; un bloqueo sí (HTTP de error)
                    fallos += 1
                    if isinstance(exc, RuntimeError) or fallos >= 10:
                        print(f"Se detiene: {exc}")
                        break
                    continue
                if "/angebote/" in final and (co2 := parse_detail(props).get("co2_gkm")):
                    car.co2_gkm, con_co2 = co2, con_co2 + 1
                else:
                    sin_dato += 1
                if i % 25 == 0:
                    db.commit()
                    print(f"  {i}/{len(rows)}")
                await s._pause()
        db.commit()
        return {"consultados": len(rows), "con_co2": con_co2, "sin_dato": sin_dato, "fallos": fallos}


async def purge_damaged(dry_run: bool = False) -> dict:
    ensure_columns()
    with SessionLocal() as db:
        scraper = KleinanzeigenScraper()
        primero = db.scalar(select(User.id).order_by(User.id))  # la búsqueda del primer usuario (o la de por defecto)
        damaged = await scraper.damaged_ids(get_setting(db, "search", primero) if primero else DEFAULT_SEARCH)
        rows = db.scalars(select(Car).where(Car.source == "kleinanzeigen", Car.external_id.in_(damaged))).all()
        protected = [c for c in rows if has_followup(c)]
        to_delete = [c for c in rows if not has_followup(c)]
        if not dry_run:
            for car in to_delete:
                db.delete(car)
            db.commit()
            apply_duplicates(db)
            rescore_all(db)
        return {
            "dañados_en_kleinanzeigen": len(damaged),
            "en_tu_base": len(rows),
            "borrados" if not dry_run else "se_borrarían": len(to_delete),
            "protegidos_por_seguimiento": [(c.id, c.titel[:50]) for c in protected],
            "avisos": scraper.warnings,
        }


def backup(destino: str | None = None, conservar: int = 14) -> dict:
    """Copia de seguridad: la base (con la API de copia de SQLite, consistente aunque el backend esté escribiendo) y las
    fotos de las revisiones, en `data/backups/`. Conserva las últimas `conservar` copias de cada tipo."""
    import re
    import sqlite3
    import tarfile
    from datetime import datetime
    from pathlib import Path

    from .config import env
    from .services.inspections import media_dir

    if not env.database_url.startswith("sqlite:///"):
        raise SystemExit("La copia solo está pensada para SQLite.")
    origen = Path(env.database_url.removeprefix("sqlite:///"))
    carpeta = Path(destino) if destino else origen.parent / "backups"
    carpeta.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    db_copia = carpeta / f"autos-{sello}.db"
    src, dst = sqlite3.connect(origen), sqlite3.connect(db_copia)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    fotos = media_dir()
    fotos_copia = carpeta / f"fotos-{sello}.tar.gz"
    with tarfile.open(fotos_copia, "w:gz") as tar:
        tar.add(fotos, arcname="inspections")
    borradas = 0
    for patron in (r"autos-\d{8}-\d{6}\.db", r"fotos-\d{8}-\d{6}\.tar\.gz"):
        antiguas = sorted(f for f in carpeta.iterdir() if re.fullmatch(patron, f.name))[:-conservar] if conservar > 0 else []
        for f in antiguas:
            f.unlink()
            borradas += 1
    return {"base": str(db_copia), "fotos": str(fotos_copia), "kb_base": db_copia.stat().st_size // 1024, "borradas_antiguas": borradas}


def usuarios_cmd(task: str, nombre: str | None) -> None:
    import getpass

    from .database import Base, engine
    from .services import auth

    Base.metadata.create_all(engine)
    ensure_columns()
    with SessionLocal() as db:
        if task == "listar-usuarios":
            for u in db.scalars(select(User).order_by(User.id)):
                print(f"{u.id:>3}  {u.username:<20} creado {u.creado_en:%Y-%m-%d}  {'configurado' if u.configurado else 'sin configurar'}")
            return
        if not nombre:
            raise SystemExit("Indica el nombre de usuario.")
        pw = getpass.getpass("Contraseña: ")
        if pw != getpass.getpass("Repite la contraseña: "):
            raise SystemExit("Las contraseñas no coinciden.")
        try:
            if task == "crear-usuario":
                user = auth.crear_usuario(db, nombre, pw)
                print(f"Usuario «{user.username}» creado" + (" (con los datos que ya había en la base)." if user.configurado else "."))
            else:
                user = db.scalar(select(User).where(User.username == auth.normalizar_usuario(nombre)))
                if not user:
                    raise SystemExit(f"No existe el usuario «{nombre}».")
                auth.cambiar_password(db, user, pw)
                print("Contraseña cambiada; las sesiones abiertas se han cerrado.")
        except ValueError as e:
            raise SystemExit(str(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=["purge-damaged", "verify-stale", "fix-models", "backfill-co2", "probar-ia", "gemini-models",
                                         "crear-usuario", "listar-usuarios", "cambiar-password", "backup"])
    parser.add_argument("--destino", default=None, help="backup: carpeta de destino (por defecto data/backups)")
    parser.add_argument("--conservar", type=int, default=14, help="backup: cuántas copias guardar de cada tipo")
    parser.add_argument("nombre", nargs="?", help="crear-usuario / cambiar-password: nombre de usuario")
    parser.add_argument("--horas", type=float, default=12, help="verify-stale: antigüedad mínima desde que se vio por última vez")
    parser.add_argument("--limite", type=int, default=None, help="backfill-co2: máximo de coches a consultar")
    parser.add_argument("--dry-run", action="store_true", help="solo cuenta, no borra")
    args = parser.parse_args()
    if args.task in ("crear-usuario", "listar-usuarios", "cambiar-password"):
        usuarios_cmd(args.task, args.nombre)
    elif args.task == "backup":
        print(backup(args.destino, args.conservar))
    elif args.task == "purge-damaged":
        print(asyncio.run(purge_damaged(args.dry_run)))
    elif args.task == "fix-models":
        r = fix_models(args.dry_run)
        print({k: v for k, v in r.items() if k != "detalle"})
        for d in r["detalle"]:
            print("  ", d)
    elif args.task == "verify-stale":
        print(asyncio.run(verify_stale(args.horas, args.dry_run)))
    elif args.task == "backfill-co2":
        print(asyncio.run(backfill_co2(args.dry_run, args.limite)))
    elif args.task == "probar-ia":
        from .services import llm

        print(llm.probar())
    else:
        from .services import llm

        if not llm.env.gemini_api_key:
            raise SystemExit("Falta GEMINI_API_KEY en backend/.env")
        for model in llm.modelos_gemini():
            print(f"{model['id']:<42} {model['nombre'] or '':<32} entrada {model['entrada_max']} / salida {model['salida_max']}")

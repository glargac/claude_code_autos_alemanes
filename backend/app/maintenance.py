"""Tareas de mantenimiento puntuales. Uso (desde backend/, con el entorno virtual):

    python -m app.maintenance purge-damaged [--dry-run]
    python -m app.maintenance fix-models [--dry-run]   # corrige el modelo desde el título donde lo contradice
    python -m app.maintenance verify-stale [--dry-run] [--horas 12]
    python -m app.maintenance probar-ia          # comprueba la clave y el modelo de IA con una petición mínima
    python -m app.maintenance gemini-models      # lista los modelos de Gemini que acepta tu clave

purge-damaged: quita de la base los anuncios de kleinanzeigen marcados como "Beschädigtes Fahrzeug" que se
guardaron antes de que la búsqueda los excluyera. No toca los que tienen seguimiento (estado, notas o cita).
"""
import argparse
import asyncio

from sqlalchemy import select

from .database import SessionLocal, ensure_columns
from .models import Car
from .scrapers.kleinanzeigen import KleinanzeigenScraper
from .services.dedupe import apply_duplicates
from .services.scope import has_followup
from .services.settings_store import get_setting
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


async def purge_damaged(dry_run: bool = False) -> dict:
    ensure_columns()
    with SessionLocal() as db:
        scraper = KleinanzeigenScraper()
        damaged = await scraper.damaged_ids(get_setting(db, "search"))
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=["purge-damaged", "verify-stale", "fix-models", "probar-ia", "gemini-models"])
    parser.add_argument("--horas", type=float, default=12, help="verify-stale: antigüedad mínima desde que se vio por última vez")
    parser.add_argument("--dry-run", action="store_true", help="solo cuenta, no borra")
    args = parser.parse_args()
    if args.task == "purge-damaged":
        print(asyncio.run(purge_damaged(args.dry_run)))
    elif args.task == "fix-models":
        r = fix_models(args.dry_run)
        print({k: v for k, v in r.items() if k != "detalle"})
        for d in r["detalle"]:
            print("  ", d)
    elif args.task == "verify-stale":
        print(asyncio.run(verify_stale(args.horas, args.dry_run)))
    elif args.task == "probar-ia":
        from .services import llm

        print(llm.probar())
    else:
        from .services import llm

        if not llm.env.gemini_api_key:
            raise SystemExit("Falta GEMINI_API_KEY en backend/.env")
        for model in llm.modelos_gemini():
            print(f"{model['id']:<42} {model['nombre'] or '':<32} entrada {model['entrada_max']} / salida {model['salida_max']}")

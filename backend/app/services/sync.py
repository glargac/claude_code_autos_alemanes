"""Orquestación: scraping -> dedupe (upsert) -> scoring -> comprobación de vigencia."""
import asyncio
import os
import shutil
import sys
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Car
from ..scrapers.base import Scraper
from ..scrapers.kleinanzeigen import KleinanzeigenScraper
from ..scrapers.autoscout24 import AutoScout24Scraper
from .dedupe import apply_duplicates
from .modelo import corregir_modelo
from .scope import out_of_scope, purge_out_of_scope
from .scoring import MarketIndex, compute_score
from .settings_store import get_setting, save_setting

SCRAPERS: list[Scraper] = [KleinanzeigenScraper(), AutoScout24Scraper()]


def rescore(car: Car, weights: dict, search: dict, market: MarketIndex) -> None:
    car.score, car.score_detail = compute_score(car, weights, search, market)


async def run_sync(db: Session, progress=None) -> dict:
    """Cada fuente se procesa y se guarda por separado: si una falla (bloqueo, cambio de web), las
    demás siguen y lo ya guardado se conserva. Los fallos se devuelven en `fehler`."""
    search, weights = get_setting(db, "search"), get_setting(db, "weights")
    now = datetime.utcnow()
    wanted_fuels = {f.casefold() for f in search["kraftstoffart"]}
    market = MarketIndex(db.scalars(select(Car).where(Car.aktiv.is_(True), Car.duplicado_de.is_(None))))
    nuevos = actualizados = inactivos = 0
    fehler: list[str] = []
    fuentes: dict[str, bool] = {}  # resultado por fuente
    errores: dict[str, str] = {}
    fuentes_ok = descartados = 0

    for i, scraper in enumerate(SCRAPERS):
        def report(phase, done, total, _i=i, _name=scraper.name):
            if progress:
                progress(phase, done, total, _name, _i, len(SCRAPERS))

        try:
            seen: set[str] = set()
            nuevos_f = actualizados_f = inactivos_f = 0  # de esta fuente; se suman solo si se guarda
            known = frozenset(db.scalars(select(Car.external_id).where(Car.source == scraper.name)))
            items = await scraper.search(search, known, report)
            fehler.extend(f"{scraper.name} (aviso): {w}" for w in scraper.warnings)
            for item in items:
                if out_of_scope(item, wanted_fuels):
                    continue  # eléctricos, furgonetas de carga...: fuera de alcance
                seen.add(item.external_id)
                data = {k: v for k, v in item.__dict__.items() if k != "extra" and v not in (None, "")}
                if data.get("modell") and (nuevo := corregir_modelo(item.marke, data["modell"], item.titel)):
                    data["modell_original"], data["modell"] = data["modell"], nuevo  # el título contradecía el modelo registrado
                try:
                    with db.begin_nested():  # savepoint: un coche con datos raros no tumba al resto de la fuente
                        car = db.scalar(
                            select(Car).where(Car.source == item.source, Car.external_id == item.external_id)
                        )
                        created = car is None
                        if car:
                            for k, v in data.items():
                                setattr(car, k, v)
                            car.aktiv, car.zuletzt_gesehen = True, now
                        else:
                            car = Car(**{"marke": "", "modell": "", **data}, erstmals_gesehen=now, zuletzt_gesehen=now)
                            db.add(car)
                        rescore(car, weights, search, market)
                except Exception as exc:
                    fehler.append(f"{scraper.name} (aviso): se omitió el anuncio {item.external_id}: {type(exc).__name__}: {str(exc)[:120]}")
                    continue
                if created:
                    nuevos_f += 1
                else:
                    actualizados_f += 1

            # Vigencia: activos de esta fuente que no aparecieron -> verificar individualmente.
            missing = [
                c for c in db.scalars(select(Car).where(Car.source == scraper.name, Car.aktiv.is_(True)))
                if c.external_id not in seen
            ]
            gone = await scraper.inactive_urls([c.url for c in missing], report)
            for car in missing:
                if car.url in gone:
                    car.aktiv = False
                    inactivos_f += 1
            db.commit()
            nuevos, actualizados, inactivos = nuevos + nuevos_f, actualizados + actualizados_f, inactivos + inactivos_f
            fuentes_ok += 1
            fuentes[scraper.name] = True
            descartados += purge_out_of_scope(db, wanted_fuels)
            apply_duplicates(db)
            rescore_all(db)  # con los coches nuevos ya guardados, el precio de todos se compara con un mercado mayor
        except Exception as exc:
            db.rollback()
            fuentes[scraper.name] = False
            errores[scraper.name] = f"{type(exc).__name__}: {(str(exc).splitlines() or [''])[0][:150]}"
            fehler.append(f"{scraper.name}: {type(exc).__name__}: {exc}")

    return {
        "nuevos": nuevos, "actualizados": actualizados, "inactivos": inactivos,
        "fuentes_ok": fuentes_ok, "fuentes": fuentes, "errores": errores, "descartados": descartados,
        "fehler": fehler,
    }


def rescore_all(db: Session) -> int:
    """Recalcula todos los scores con los pesos y rangos actuales."""
    search, weights = get_setting(db, "search"), get_setting(db, "weights")
    cars = db.scalars(select(Car)).all()
    market = MarketIndex(c for c in cars if c.aktiv and c.duplicado_de is None)  # un coche repetido cuenta una vez
    for car in cars:
        car.score, car.score_detail = compute_score(car, weights, search, market)
    db.commit()
    return len(cars)


# Estado de la sincronización en segundo plano (un solo proceso, una sola sync a la vez).
sync_state: dict = {"running": False, "started_at": None, "result": None, "error": None, "progress": None}

# Peso de cada fase en la barra de progreso (la fase de detalles domina en la primera sync).
_PHASES = {"listas": (0, 10), "detalles": (10, 70), "verificar": (80, 20)}


def _progress(phase: str, done: int, total: int, source: str | None = None, idx: int = 0, n: int = 1) -> None:
    start, span = _PHASES[phase]
    frac = done / total if total else 1
    within = (start + span * frac) / 100  # 0..1 dentro de la fuente actual
    sync_state["progress"] = {
        "phase": phase, "done": done, "total": total, "source": source,
        "percent": round((idx + within) / n * 100),
    }


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


async def wait_for_network(host: str = "www.kleinanzeigen.de", timeout: float = 90.0) -> bool:
    """Espera a que el DNS responda. Tras despertar de un reposo, el Wi-Fi tarda unos segundos en volver y una
    sync lanzada en ese momento fallaba con ENOTFOUND. Si no hay red al agotar el plazo, sigue igualmente
    (la sync fallará con un error claro)."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            await asyncio.get_running_loop().getaddrinfo(host, 443)
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(5)


async def _keep_awake():
    """En macOS impide el reposo del sistema mientras dura la sync (`caffeinate`). Se detiene al terminar o si
    muere el backend. No evita el reposo por cerrar la tapa del portátil."""
    if sys.platform != "darwin" or not shutil.which("caffeinate"):
        return None
    try:
        return await asyncio.create_subprocess_exec(
            "caffeinate", "-i", "-s", "-w", str(os.getpid()),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        return None


async def _run_in_background() -> None:
    from ..database import SessionLocal

    awake = await _keep_awake()
    try:
        await wait_for_network()
        with SessionLocal() as db:
            result = await run_sync(db, _progress)
            # La hora de "última sync" solo avanza si al menos una fuente funcionó; si no, la sync al abrir
            # seguiría creyendo que los datos están frescos sin haber descargado nada.
            meta = {**get_setting(db, "sync_meta"), "last_result": result}  # conserva las últimas horas válidas
            now = _utc_now()
            sources = {k: dict(v) for k, v in meta.get("sources", {}).items()}
            for name, ok in result["fuentes"].items():
                entry = sources.setdefault(name, {"last_sync_at": meta.get("last_sync_at"), "error": None})  # hereda la hora global previa
                if ok:
                    entry.update(last_sync_at=now, error=None)
                else:  # la hora de la última sync buena de esa fuente NO avanza
                    entry["error"] = result["errores"].get(name, "falló")
            meta["sources"] = sources
            if result["fuentes_ok"]:
                meta["last_sync_at"] = now  # global: cuándo hubo algún dato nuevo
            save_setting(db, "sync_meta", meta)
        sync_state["result"] = result
        sync_state["error"] = None
    except Exception as exc:  # se muestra en la UI
        sync_state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if awake and awake.returncode is None:
            awake.terminate()
        sync_state["running"] = False
        sync_state["progress"] = None


def start_sync() -> bool:
    """Lanza la sync si no hay otra en curso. Devuelve False si ya estaba corriendo."""
    if sync_state["running"]:
        return False
    sync_state.update(running=True, started_at=_utc_now(), result=None, error=None, progress=None)
    asyncio.create_task(_run_in_background())
    return True


def _parse_utc(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw.rstrip("Z")) if raw else None


def _last_sync(db: Session, source: str | None = None) -> datetime | None:
    """Última sync buena de una fuente, o la global si no se indica fuente (o la base es antigua)."""
    meta = get_setting(db, "sync_meta")
    entry = meta.get("sources", {}).get(source) if source else None
    if entry is not None:  # con datos por fuente: si nunca funcionó, es None (no se usa la hora de otra fuente)
        return _parse_utc(entry.get("last_sync_at"))
    return _parse_utc(meta["last_sync_at"])  # global, o respaldo para bases antiguas sin datos por fuente


def status(db: Session) -> dict:
    meta = get_setting(db, "sync_meta")
    return {**sync_state, "last_sync_at": meta["last_sync_at"], "fuentes": meta.get("sources", {})}


def start_if_stale(db: Session) -> bool:
    """Sync al abrir la app: solo si está activada y ALGUNA fuente tiene datos con más de `max_age_hours`
    (o nunca se sincronizó). Una fuente que falló no queda oculta por el éxito de la otra."""
    app = get_setting(db, "app")
    limit = timedelta(hours=app["max_age_hours"])
    now = datetime.utcnow()
    stale = any((last := _last_sync(db, s.name)) is None or now - last > limit for s in SCRAPERS)
    return bool(app["auto_sync_on_open"] and stale and start_sync())


async def scheduled_sync() -> None:
    """Trabajo del planificador (solo si la sync diaria está activada)."""
    start_sync()


def apply_schedule(scheduler, app_settings: dict) -> None:
    """Deja el planificador acorde a los ajustes: añade, reprograma o quita la sync diaria."""
    job = scheduler.get_job("daily_sync")
    if not app_settings["daily_sync"]:
        if job:
            scheduler.remove_job("daily_sync")
        return
    if job:
        scheduler.reschedule_job("daily_sync", trigger="cron", hour=app_settings["sync_hour"])
    else:
        # Si el backend estaba ocupado o parado a la hora exacta, aún dispara hasta 1 h tarde.
        scheduler.add_job(
            scheduled_sync, "cron", hour=app_settings["sync_hour"], id="daily_sync", misfire_grace_time=3600, coalesce=True
        )


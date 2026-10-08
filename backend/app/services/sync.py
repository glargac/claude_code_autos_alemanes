"""Orquestación: scraping -> dedupe (upsert) -> scoring -> comprobación de vigencia."""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Car
from ..scrapers.base import Scraper
from ..scrapers.kleinanzeigen import KleinanzeigenScraper
from ..scrapers.mobile_de import MobileDeScraper
from .llm import analyze_profitability
from .scoring import compute_score
from .settings_store import get_setting, save_setting

SCRAPERS: list[Scraper] = [MobileDeScraper(), KleinanzeigenScraper()]


def rescore(car: Car, weights: dict, search: dict) -> None:
    llm_score, analyse = analyze_profitability(car)
    if analyse:
        car.llm_analyse = analyse
    car.score, car.score_detail = compute_score(car, weights, search, llm_score)


async def run_sync(db: Session, progress=None) -> dict:
    search, weights = get_setting(db, "search"), get_setting(db, "weights")
    now = datetime.utcnow()
    nuevos = actualizados = inactivos = 0

    for scraper in SCRAPERS:
        seen: set[str] = set()
        known = frozenset(db.scalars(select(Car.external_id).where(Car.source == scraper.name)))
        for item in await scraper.search(search, known, progress):
            seen.add(item.external_id)
            car = db.scalar(select(Car).where(Car.source == item.source, Car.external_id == item.external_id))
            data = {k: v for k, v in item.__dict__.items() if k != "extra" and v not in (None, "")}
            if car:
                for k, v in data.items():
                    setattr(car, k, v)
                car.aktiv, car.zuletzt_gesehen = True, now
                actualizados += 1
            else:
                car = Car(**data, erstmals_gesehen=now, zuletzt_gesehen=now)
                db.add(car)
                nuevos += 1
            rescore(car, weights, search)

        # Vigencia: activos de esta fuente que no aparecieron -> verificar individualmente.
        missing = [
            c for c in db.scalars(select(Car).where(Car.source == scraper.name, Car.aktiv.is_(True)))
            if c.external_id not in seen
        ]
        gone = await scraper.inactive_urls([c.url for c in missing], progress)
        for car in missing:
            if car.url in gone:
                car.aktiv = False
                inactivos += 1

    db.commit()
    return {"nuevos": nuevos, "actualizados": actualizados, "inactivos": inactivos}


def rescore_all(db: Session) -> int:
    """Recalcula scores con los pesos/rangos actuales reutilizando la nota LLM guardada (sin llamar al LLM)."""
    search, weights = get_setting(db, "search"), get_setting(db, "weights")
    cars = db.scalars(select(Car)).all()
    for car in cars:
        llm = (car.score_detail or {}).get("llm_rentabilidad")
        car.score, car.score_detail = compute_score(car, weights, search, llm)
    db.commit()
    return len(cars)


# Estado de la sincronización en segundo plano (un solo proceso, una sola sync a la vez).
sync_state: dict = {"running": False, "started_at": None, "result": None, "error": None, "progress": None}

# Peso de cada fase en la barra de progreso (la fase de detalles domina en la primera sync).
_PHASES = {"listas": (0, 10), "detalles": (10, 70), "verificar": (80, 20)}


def _progress(phase: str, done: int, total: int) -> None:
    start, span = _PHASES[phase]
    frac = done / total if total else 1
    sync_state["progress"] = {"phase": phase, "done": done, "total": total, "percent": round(start + span * frac)}


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


async def _run_in_background() -> None:
    from ..database import SessionLocal

    try:
        with SessionLocal() as db:
            result = await run_sync(db, _progress)
            save_setting(db, "sync_meta", {"last_sync_at": _utc_now(), "last_result": result})
        sync_state["result"] = result
        sync_state["error"] = None
    except Exception as exc:  # se muestra en la UI
        sync_state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        sync_state["running"] = False
        sync_state["progress"] = None


def start_sync() -> bool:
    """Lanza la sync si no hay otra en curso. Devuelve False si ya estaba corriendo."""
    import asyncio

    if sync_state["running"]:
        return False
    sync_state.update(running=True, started_at=_utc_now(), result=None, error=None, progress=None)
    asyncio.create_task(_run_in_background())
    return True


def _last_sync(db: Session) -> datetime | None:
    raw = get_setting(db, "sync_meta")["last_sync_at"]
    return datetime.fromisoformat(raw.rstrip("Z")) if raw else None


def status(db: Session) -> dict:
    return {**sync_state, "last_sync_at": get_setting(db, "sync_meta")["last_sync_at"]}


def start_if_stale(db: Session) -> bool:
    """Sync al abrir la app: solo si está activada y los datos tienen más de `max_age_hours`."""
    app = get_setting(db, "app")
    last = _last_sync(db)
    stale = last is None or datetime.utcnow() - last > timedelta(hours=app["max_age_hours"])
    return bool(app["auto_sync_on_open"] and stale and start_sync())

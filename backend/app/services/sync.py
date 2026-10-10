"""Orquestación: scraping -> dedupe (upsert) -> scoring -> comprobación de vigencia."""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Car
from ..scrapers.base import Scraper
from ..scrapers.kleinanzeigen import KleinanzeigenScraper
from ..scrapers.autoscout24 import AutoScout24Scraper
from .llm import analyze_prompt, build_prompt, enabled as llm_enabled
from .scoring import MarketIndex, compute_score
from .settings_store import get_setting, save_setting

SCRAPERS: list[Scraper] = [KleinanzeigenScraper(), AutoScout24Scraper()]


async def rescore(car: Car, weights: dict, search: dict, market: MarketIndex) -> None:
    """Recalcula el score. El LLM solo se consulta si el coche aún no tiene análisis (coste: una
    llamada por coche, una sola vez); en el resto se reutiliza la nota guardada."""
    llm_score = (car.score_detail or {}).get("llm_rentabilidad")
    if llm_enabled() and (car.llm_analyse is None or llm_score is None):
        score, analyse = await asyncio.to_thread(analyze_prompt, build_prompt(car))
        if analyse:
            car.llm_analyse, llm_score = analyse, score
    car.score, car.score_detail = compute_score(car, weights, search, llm_score, market)


async def run_sync(db: Session, progress=None) -> dict:
    """Cada fuente se procesa y se guarda por separado: si una falla (bloqueo, cambio de web), las
    demás siguen y lo ya guardado se conserva. Los fallos se devuelven en `fehler`."""
    search, weights = get_setting(db, "search"), get_setting(db, "weights")
    now = datetime.utcnow()
    wanted_fuels = {f.casefold() for f in search["kraftstoffart"]}
    market = MarketIndex(db.scalars(select(Car).where(Car.aktiv.is_(True))))
    nuevos = actualizados = inactivos = 0
    fehler: list[str] = []
    fuentes_ok = 0

    for i, scraper in enumerate(SCRAPERS):
        def report(phase, done, total, _i=i, _name=scraper.name):
            if progress:
                progress(phase, done, total, _name, _i, len(SCRAPERS))

        try:
            seen: set[str] = set()
            known = frozenset(db.scalars(select(Car.external_id).where(Car.source == scraper.name)))
            items = await scraper.search(search, known, report)
            fehler.extend(f"{scraper.name} (aviso): {w}" for w in scraper.warnings)
            for item in items:
                if item.kraftstoffart and item.kraftstoffart.casefold() not in wanted_fuels:
                    continue  # p. ej. eléctricos o híbridos: fuera de alcance
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
                await rescore(car, weights, search, market)

            # Vigencia: activos de esta fuente que no aparecieron -> verificar individualmente.
            missing = [
                c for c in db.scalars(select(Car).where(Car.source == scraper.name, Car.aktiv.is_(True)))
                if c.external_id not in seen
            ]
            gone = await scraper.inactive_urls([c.url for c in missing], report)
            for car in missing:
                if car.url in gone:
                    car.aktiv = False
                    inactivos += 1
            db.commit()
            fuentes_ok += 1
            rescore_all(db)  # con los coches nuevos ya guardados, el precio de todos se compara con un mercado mayor
        except Exception as exc:
            db.rollback()
            fehler.append(f"{scraper.name}: {type(exc).__name__}: {exc}")

    return {
        "nuevos": nuevos, "actualizados": actualizados, "inactivos": inactivos,
        "fuentes_ok": fuentes_ok, "fehler": fehler,
    }


def rescore_all(db: Session) -> int:
    """Recalcula scores con los pesos/rangos actuales reutilizando la nota LLM guardada (sin llamar al LLM)."""
    search, weights = get_setting(db, "search"), get_setting(db, "weights")
    cars = db.scalars(select(Car)).all()
    market = MarketIndex(c for c in cars if c.aktiv)
    for car in cars:
        llm = (car.score_detail or {}).get("llm_rentabilidad")
        car.score, car.score_detail = compute_score(car, weights, search, llm, market)
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


async def _run_in_background() -> None:
    from ..database import SessionLocal

    try:
        with SessionLocal() as db:
            result = await run_sync(db, _progress)
            # La hora de "última sync" solo avanza si al menos una fuente funcionó; si no, la sync al abrir
            # seguiría creyendo que los datos están frescos sin haber descargado nada.
            meta = {**get_setting(db, "sync_meta"), "last_result": result}  # conserva la última hora válida
            if result["fuentes_ok"]:
                meta["last_sync_at"] = _utc_now()
            save_setting(db, "sync_meta", meta)
        sync_state["result"] = result
        sync_state["error"] = None
    except Exception as exc:  # se muestra en la UI
        sync_state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        sync_state["running"] = False
        sync_state["progress"] = None


def start_sync() -> bool:
    """Lanza la sync si no hay otra en curso. Devuelve False si ya estaba corriendo."""
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

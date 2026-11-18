"""Orquestación: scraping -> dedupe (upsert) -> scoring -> comprobación de vigencia."""
import asyncio
import os
import shutil
import sys
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Car, User, UserCar
from ..scrapers.base import Scraper
from ..scrapers.kleinanzeigen import KleinanzeigenScraper
from ..scrapers.autoscout24 import AutoScout24Scraper
from .dedupe import apply_duplicates
from .modelo import corregir_modelo
from .scope import es_furgoneta, out_of_scope, purge_out_of_scope
from .scoring import MarketIndex, compute_score
from .settings_store import get_setting, save_setting

SCRAPERS: list[Scraper] = [KleinanzeigenScraper(), AutoScout24Scraper()]


def combustibles_deseados(db: Session) -> set[str]:
    """Combustibles que quiere ALGÚN usuario (en minúsculas): los coches son de todos, solo se descarta lo que nadie quiere."""
    fuels: set[str] = set()
    for uid in db.scalars(select(User.id)):
        fuels |= {f.casefold() for f in get_setting(db, "search", uid)["kraftstoffart"]}
    return fuels


async def run_sync(db: Session, user_id: int, progress=None) -> dict:
    """Sincroniza con la búsqueda de ESE usuario. Los coches se guardan una sola vez para todos (si ya los trajo otro
    usuario no se vuelve a pedir su detalle); cada usuario recibe su vínculo (`UserCar`) con su propia puntuación.
    Cada fuente se procesa y se guarda por separado: si una falla (bloqueo, cambio de web), las demás siguen y lo ya
    guardado se conserva. Los fallos se devuelven en `fehler`."""
    search, weights = get_setting(db, "search", user_id), get_setting(db, "weights", user_id)
    now = datetime.utcnow()
    wanted_fuels = {f.casefold() for f in search["kraftstoffart"]}  # lo que entra en la lista de ESTE usuario
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
                        car.furgoneta = es_furgoneta(car.modell, car.titel)
                        db.flush()  # un coche nuevo necesita su id para el vínculo
                        uc = db.get(UserCar, (user_id, car.id)) or UserCar(user_id=user_id, car_id=car.id)  # nunca se «des-elimina»
                        db.add(uc)
                        uc.score, uc.score_detail = compute_score(car, weights, search, market)
                except Exception as exc:
                    fehler.append(f"{scraper.name} (aviso): se omitió el anuncio {item.external_id}: {type(exc).__name__}: {str(exc)[:120]}")
                    continue
                if created:
                    nuevos_f += 1
                else:
                    actualizados_f += 1

            # Vigencia: activos de esta fuente que no aparecieron -> verificar individualmente.
            missing = [  # solo los de este usuario: lo que encontró otro con otra búsqueda no es «desaparecido» aquí
                c for c in db.scalars(select(Car).join(UserCar, UserCar.car_id == Car.id).where(
                    UserCar.user_id == user_id, Car.source == scraper.name, Car.aktiv.is_(True)))
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
            descartados += purge_out_of_scope(db, combustibles_deseados(db))
            apply_duplicates(db)
            rescore_all(db, user_id)  # con los coches nuevos ya guardados, el precio de todos se compara con un mercado mayor
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


def rescore_all(db: Session, user_id: int | None = None) -> int:
    """Recalcula las puntuaciones con los pesos y rangos actuales: las de un usuario, o las de todos si no se indica."""
    cars = {c.id: c for c in db.scalars(select(Car))}
    market = MarketIndex(c for c in cars.values() if c.aktiv and c.duplicado_de is None)  # un coche repetido cuenta una vez
    n = 0
    for uid in [user_id] if user_id is not None else list(db.scalars(select(User.id))):
        search, weights = get_setting(db, "search", uid), get_setting(db, "weights", uid)
        for uc in db.scalars(select(UserCar).where(UserCar.user_id == uid)):
            if car := cars.get(uc.car_id):
                uc.score, uc.score_detail = compute_score(car, weights, search, market)
                n += 1
    db.commit()
    return n


# Estado de la sincronización en segundo plano: uno por usuario, en memoria. Solo corre un scraping a la vez en todo el
# servidor (memoria del navegador y amabilidad con los portales): los demás usuarios esperan su turno («en_cola»).
_ESTADO_INICIAL = {"running": False, "en_cola": False, "started_at": None, "result": None, "error": None, "progress": None}
sync_states: dict[int, dict] = {}
_turno: asyncio.Lock | None = None

# Peso de cada fase en la barra de progreso (la fase de detalles domina en la primera sync).
_PHASES = {"listas": (0, 10), "detalles": (10, 70), "verificar": (80, 20)}


def estado_de(user_id: int) -> dict:
    return sync_states.setdefault(user_id, dict(_ESTADO_INICIAL))


def _progress(state: dict, phase: str, done: int, total: int, source: str | None = None, idx: int = 0, n: int = 1) -> None:
    start, span = _PHASES[phase]
    frac = done / total if total else 1
    within = (start + span * frac) / 100  # 0..1 dentro de la fuente actual
    state["progress"] = {
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


async def _run_in_background(user_id: int) -> None:
    global _turno
    from ..database import SessionLocal

    state = estado_de(user_id)
    _turno = _turno or asyncio.Lock()
    try:
        async with _turno:
            state["en_cola"] = False
            awake = await _keep_awake()
            try:
                await wait_for_network()
                with SessionLocal() as db:
                    result = await run_sync(db, user_id, lambda *a: _progress(state, *a))
                    # La hora de "última sync" solo avanza si al menos una fuente funcionó; si no, la sync al abrir
                    # seguiría creyendo que los datos están frescos sin haber descargado nada.
                    meta = {**get_setting(db, "sync_meta", user_id), "last_result": result}  # conserva las últimas horas válidas
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
                    save_setting(db, "sync_meta", meta, user_id)
                state["result"] = result
                state["error"] = None
            finally:
                if awake and awake.returncode is None:
                    awake.terminate()
    except Exception as exc:  # se muestra en la UI
        state["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        state.update(running=False, en_cola=False, progress=None)


def start_sync(user_id: int) -> bool:
    """Lanza la sync de un usuario si no tiene ya una en curso. Si otro usuario está sincronizando, espera su turno."""
    global _turno
    state = estado_de(user_id)
    if state["running"]:
        return False
    _turno = _turno or asyncio.Lock()
    espera = any(st["running"] for uid, st in sync_states.items() if uid != user_id)  # otro usuario ya tiene el turno
    state.update(running=True, en_cola=espera, started_at=_utc_now(), result=None, error=None, progress=None)
    asyncio.create_task(_run_in_background(user_id))
    return True


def _parse_utc(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw.rstrip("Z")) if raw else None


def _last_sync(db: Session, user_id: int, source: str | None = None) -> datetime | None:
    """Última sync buena de una fuente, o la global si no se indica fuente (o la base es antigua)."""
    meta = get_setting(db, "sync_meta", user_id)
    entry = meta.get("sources", {}).get(source) if source else None
    if entry is not None:  # con datos por fuente: si nunca funcionó, es None (no se usa la hora de otra fuente)
        return _parse_utc(entry.get("last_sync_at"))
    return _parse_utc(meta["last_sync_at"])  # global, o respaldo para bases antiguas sin datos por fuente


def status(db: Session, user_id: int) -> dict:
    meta = get_setting(db, "sync_meta", user_id)
    return {**estado_de(user_id), "last_sync_at": meta["last_sync_at"], "fuentes": meta.get("sources", {})}


def start_if_stale(db: Session, user_id: int) -> bool:
    """Sync al abrir la app: solo si está activada y ALGUNA fuente tiene datos con más de `max_age_hours`
    (o nunca se sincronizó). Una fuente que falló no queda oculta por el éxito de la otra."""
    app = get_setting(db, "app", user_id)
    limit = timedelta(hours=app["max_age_hours"])
    now = datetime.utcnow()
    stale = any((last := _last_sync(db, user_id, s.name)) is None or now - last > limit for s in SCRAPERS)
    return bool(app["auto_sync_on_open"] and stale and start_sync(user_id))


async def scheduled_sync(user_id: int) -> None:
    """Trabajo del planificador (solo si ese usuario tiene activada la sync diaria)."""
    start_sync(user_id)


def apply_schedule(scheduler, user_id: int, app_settings: dict) -> None:
    """Deja el planificador acorde a los ajustes de un usuario: añade, reprograma o quita su sync diaria."""
    job_id = f"daily_sync_{user_id}"
    job = scheduler.get_job(job_id)
    if not app_settings["daily_sync"]:
        if job:
            scheduler.remove_job(job_id)
        return
    if job:
        scheduler.reschedule_job(job_id, trigger="cron", hour=app_settings["sync_hour"])
    else:
        # Si el backend estaba ocupado o parado a la hora exacta, aún dispara hasta 1 h tarde.
        scheduler.add_job(
            scheduled_sync, "cron", args=[user_id], hour=app_settings["sync_hour"], id=job_id, misfire_grace_time=3600, coalesce=True
        )

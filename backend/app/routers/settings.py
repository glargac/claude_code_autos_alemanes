from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import AppSettings, SearchSettings, WeightsSettings
from ..services import sync as sync_service
from ..services.settings_store import get_setting, save_setting

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings/search")
def read_search(db: Session = Depends(get_db)):
    return get_setting(db, "search")


@router.put("/settings/search")
def write_search(body: SearchSettings, db: Session = Depends(get_db)):
    saved = save_setting(db, "search", body.model_dump())
    sync_service.rescore_all(db)  # los rangos de km influyen en el score
    return saved


@router.get("/settings/weights")
def read_weights(db: Session = Depends(get_db)):
    return get_setting(db, "weights")


@router.put("/settings/weights")
def write_weights(body: WeightsSettings, db: Session = Depends(get_db)):
    saved = save_setting(db, "weights", body.model_dump())
    sync_service.rescore_all(db)
    return saved


@router.get("/settings/app")
def read_app(db: Session = Depends(get_db)):
    return get_setting(db, "app")


@router.put("/settings/app")
def write_app(body: AppSettings, request: Request, db: Session = Depends(get_db)):
    saved = save_setting(db, "app", body.model_dump())
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler and scheduler.get_job("daily_sync"):
        scheduler.reschedule_job("daily_sync", trigger="cron", hour=saved["sync_hour"])
    return saved


@router.post("/sync", status_code=202)
async def sync_now(db: Session = Depends(get_db)):
    """Lanza el scraping en segundo plano con la configuración guardada. Consultar /api/sync/status."""
    if not sync_service.start_sync():
        raise HTTPException(409, "Ya hay una sincronización en curso")
    return sync_service.status(db)


@router.post("/sync/auto")
async def sync_auto(db: Session = Depends(get_db)):
    """Llamado al abrir la app: lanza la sync solo si los datos están desactualizados."""
    sync_service.start_if_stale(db)
    return sync_service.status(db)


@router.get("/sync/status")
def sync_status(db: Session = Depends(get_db)):
    return sync_service.status(db)

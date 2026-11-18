from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import AppSettings, RentabilidadSettings, SearchSettings, WeightsSettings
from ..services import llm, sync as sync_service
from ..services.auth import current_user
from ..services.settings_store import get_setting, save_setting

router = APIRouter(prefix="/api", tags=["settings"], dependencies=[Depends(current_user)])


@router.get("/settings/search")
def read_search(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return get_setting(db, "search", user.id)


@router.put("/settings/search")
def write_search(body: SearchSettings, user: User = Depends(current_user), db: Session = Depends(get_db)):
    saved = save_setting(db, "search", body.model_dump(), user.id)
    sync_service.rescore_all(db, user.id)  # los rangos de km influyen en el score
    return saved


@router.get("/settings/weights")
def read_weights(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return get_setting(db, "weights", user.id)


@router.put("/settings/weights")
def write_weights(body: WeightsSettings, user: User = Depends(current_user), db: Session = Depends(get_db)):
    saved = save_setting(db, "weights", body.model_dump(), user.id)
    sync_service.rescore_all(db, user.id)
    return saved


@router.get("/settings/ia")
def read_ia():
    """Estado de la IA del informe (solo lectura; las claves se ponen en backend/.env y nunca salen del servidor)."""
    return llm.info()


@router.get("/settings/rentabilidad")
def read_rentabilidad(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return get_setting(db, "rentabilidad", user.id)


@router.put("/settings/rentabilidad")
def write_rentabilidad(body: RentabilidadSettings, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return save_setting(db, "rentabilidad", body.model_dump(), user.id)


@router.get("/settings/app")
def read_app(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return get_setting(db, "app", user.id)


@router.put("/settings/app")
def write_app(body: AppSettings, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    saved = save_setting(db, "app", body.model_dump(), user.id)
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        sync_service.apply_schedule(scheduler, user.id, saved)
    return saved


@router.post("/sync", status_code=202)
async def sync_now(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lanza el scraping en segundo plano con la configuración guardada. Consultar /api/sync/status."""
    if not user.configurado:  # lanzar la primera sync es lo que cierra la bienvenida (elegir preferencias)
        user.configurado = True
        db.commit()
    if not sync_service.start_sync(user.id):
        raise HTTPException(409, "Ya hay una sincronización en curso")
    return sync_service.status(db, user.id)


@router.post("/sync/auto")
async def sync_auto(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Llamado al abrir la app: lanza la sync solo si los datos están desactualizados."""
    if user.configurado:  # sin preferencias elegidas no se scrapea nada (primero la pantalla de bienvenida)
        sync_service.start_if_stale(db, user.id)
    return sync_service.status(db, user.id)


@router.get("/sync/status")
def sync_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return sync_service.status(db, user.id)

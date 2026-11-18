import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import env
from .database import Base, SessionLocal, engine, ensure_columns
from .models import User
from .routers import auth, cars, inspections, settings
from .services.dedupe import apply_duplicates
from .services.scope import etiquetar_furgonetas, purge_out_of_scope
from .services.rentabilidad import reiniciar_interrumpidos
from .services.settings_store import get_setting
from .services.sync import apply_schedule, combustibles_deseados, rescore_all

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    ensure_columns()
    scheduler = AsyncIOScheduler()
    with SessionLocal() as db:
        usuarios = db.scalars(select(User.id)).all()
        if not usuarios:
            log.warning("No hay usuarios: crea el primero con `python -m app.maintenance crear-usuario NOMBRE`.")
        else:  # sin usuarios no se sabe qué combustibles quiere nadie: no se borra nada
            purge_out_of_scope(db, combustibles_deseados(db))
        etiquetar_furgonetas(db)
        apply_duplicates(db)  # barato (~1 s) y mantiene la marca coherente con los datos
        reiniciar_interrumpidos(db)  # análisis de rentabilidad que quedaron a medias por un reinicio
        rescore_all(db)  # tras cambiar el código de scoring, los scores guardados se actualizan solos
        for uid in usuarios:
            apply_schedule(scheduler, uid, get_setting(db, "app", uid))  # solo si ese usuario activó la sync diaria
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()


app = FastAPI(title="Autos Alemanes – Costa del Sol", lifespan=lifespan)
# La lista de coches son ~3 MB de JSON: comprimida baja a una décima parte (importa con datos móviles).
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(cars.router)
app.include_router(settings.router)
app.include_router(inspections.router)
# Fotos de las revisiones (con sesión): antes del montaje de la interfaz, que captura todo lo demás.
app.include_router(inspections.media_router)


@app.get("/api/health")
def health():
    return {"ok": True}


# Si la interfaz está compilada (npm run build), el propio backend la sirve: una sola dirección y un solo
# proceso. Debe ir al final para no tapar las rutas /api. En desarrollo se sigue usando Vite (:5173).
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

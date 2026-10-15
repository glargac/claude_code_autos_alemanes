from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import env
from .database import Base, SessionLocal, engine, ensure_columns
from .routers import cars, settings
from .services.dedupe import apply_duplicates
from .services.scope import purge_out_of_scope
from .services.settings_store import get_setting
from .services.rentabilidad import reiniciar_interrumpidos
from .services.sync import apply_schedule, rescore_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    ensure_columns()
    with SessionLocal() as db:
        purge_out_of_scope(db, {f.casefold() for f in get_setting(db, "search")["kraftstoffart"]})
        apply_duplicates(db)  # barato (~1 s) y mantiene la marca coherente con los datos
        reiniciar_interrumpidos(db)  # análisis de rentabilidad que quedaron a medias por un reinicio
        rescore_all(db)  # tras cambiar el código de scoring, los scores guardados se actualizan solos
        app_settings = get_setting(db, "app")
    scheduler = AsyncIOScheduler()
    apply_schedule(scheduler, app_settings)  # solo si la sync diaria está activada
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown()


app = FastAPI(title="Autos Alemanes – Costa del Sol", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(cars.router)
app.include_router(settings.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# Si la interfaz está compilada (npm run build), el propio backend la sirve: una sola dirección y un solo
# proceso. Debe ir al final para no tapar las rutas /api. En desarrollo se sigue usando Vite (:5173).
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

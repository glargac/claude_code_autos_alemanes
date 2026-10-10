from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import env
from .database import Base, SessionLocal, engine, ensure_columns
from .routers import cars, settings
from .services.dedupe import apply_duplicates
from .services.settings_store import get_setting
from .services.sync import start_sync


async def daily_sync():
    start_sync()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    ensure_columns()
    with SessionLocal() as db:
        apply_duplicates(db)  # barato (~1 s) y mantiene la marca coherente con los datos
        hour = get_setting(db, "app")["sync_hour"]
    scheduler = AsyncIOScheduler()
    # Si el backend estaba ocupado/parado a la hora exacta, aún dispara hasta 1 h tarde.
    scheduler.add_job(daily_sync, "cron", hour=hour, id="daily_sync", misfire_grace_time=3600, coalesce=True)
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

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import env

if env.database_url.startswith("sqlite:///./"):
    Path(env.database_url.replace("sqlite:///./", "")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(env.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

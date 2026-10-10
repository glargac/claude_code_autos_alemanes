from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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


# Columnas añadidas después de la primera versión: create_all no modifica tablas existentes.
_ADDED_COLUMNS = {"cars": {"duplicado_de": "INTEGER"}}


def ensure_columns() -> None:
    """Migración mínima: añade a una base ya creada las columnas que falten (y su índice)."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{name} ON {table} ({name})"))

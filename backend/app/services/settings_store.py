from sqlalchemy.orm import Session

from ..config import DEFAULT_APP, DEFAULT_RENTABILIDAD, DEFAULT_SEARCH, DEFAULT_WEIGHTS
from ..models import Setting

DEFAULTS = {
    "search": DEFAULT_SEARCH,
    "weights": DEFAULT_WEIGHTS,
    "app": DEFAULT_APP,
    "rentabilidad": DEFAULT_RENTABILIDAD,
    "sync_meta": {"last_sync_at": None, "last_result": None, "sources": {}},  # lo escribe la propia sync
}


def get_setting(db: Session, key: str) -> dict:
    row = db.get(Setting, key)
    saved = {k: v for k, v in (row.value if row else {}).items() if k in DEFAULTS[key]}  # descarta claves ya retiradas
    return {**DEFAULTS[key], **saved}


def save_setting(db: Session, key: str, value: dict) -> dict:
    merged = {**DEFAULTS[key], **value}
    row = db.get(Setting, key)
    if row:
        row.value = merged
    else:
        db.add(Setting(key=key, value=merged))
    db.commit()
    return merged

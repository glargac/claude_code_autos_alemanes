from sqlalchemy.orm import Session

from ..config import DEFAULT_APP, DEFAULT_SEARCH, DEFAULT_WEIGHTS
from ..models import Setting

DEFAULTS = {
    "search": DEFAULT_SEARCH,
    "weights": DEFAULT_WEIGHTS,
    "app": DEFAULT_APP,
    "sync_meta": {"last_sync_at": None, "last_result": None},  # lo escribe la propia sync
}


def get_setting(db: Session, key: str) -> dict:
    row = db.get(Setting, key)
    return {**DEFAULTS[key], **(row.value if row else {})}


def save_setting(db: Session, key: str, value: dict) -> dict:
    merged = {**DEFAULTS[key], **value}
    row = db.get(Setting, key)
    if row:
        row.value = merged
    else:
        db.add(Setting(key=key, value=merged))
    db.commit()
    return merged

from sqlalchemy.orm import Session

from ..config import DEFAULT_APP, DEFAULT_RENTABILIDAD, DEFAULT_SEARCH, DEFAULT_WEIGHTS
from ..models import UserSetting

DEFAULTS = {
    "search": DEFAULT_SEARCH,
    "weights": DEFAULT_WEIGHTS,
    "app": DEFAULT_APP,
    "rentabilidad": DEFAULT_RENTABILIDAD,
    "sync_meta": {"last_sync_at": None, "last_result": None, "sources": {}},  # lo escribe la propia sync
}


def get_setting(db: Session, key: str, user_id: int) -> dict:
    """Ajuste de un usuario: lo guardado sobre los valores por defecto."""
    row = db.get(UserSetting, (user_id, key))
    saved = {k: v for k, v in (row.value if row else {}).items() if k in DEFAULTS[key]}  # descarta claves ya retiradas
    return {**DEFAULTS[key], **saved}


def save_setting(db: Session, key: str, value: dict, user_id: int) -> dict:
    merged = {**DEFAULTS[key], **value}
    row = db.get(UserSetting, (user_id, key))
    if row:
        row.value = merged
    else:
        db.add(UserSetting(user_id=user_id, key=key, value=merged))
    db.commit()
    return merged

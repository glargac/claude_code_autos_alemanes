"""Usuarios, contraseñas y sesiones.

Contraseñas con scrypt (biblioteca estándar, sin dependencias). La sesión es un token aleatorio en una cookie
HttpOnly; en la base solo se guarda su hash, así que una copia de la base no permite entrar. Los usuarios los crea
el dueño por línea de comandos (`python -m app.maintenance crear-usuario`): no hay registro abierto, y por eso
tampoco "el primero que llegue" puede quedarse con una app expuesta en internet.
"""
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Car, Inspection, Setting, User, UserCar, UserSession
from .settings_store import DEFAULTS

COOKIE = "autos_sesion"
SESION_DIAS = 30
MIN_PASSWORD = 8
_SCRYPT = dict(n=2**14, r=8, p=1, maxmem=64 * 1024 * 1024)
USUARIO_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,38}[a-z0-9]$")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${h.hex()}"


def verificar_password(password: str, almacenado: str) -> bool:
    try:
        _, salt, h = almacenado.split("$")
        calculado = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
        return hmac.compare_digest(calculado, bytes.fromhex(h))
    except (ValueError, TypeError):
        return False


_FALSO = hash_password(secrets.token_hex(8))  # para gastar el mismo tiempo cuando el usuario no existe


def normalizar_usuario(nombre: str) -> str:
    return (nombre or "").strip().lower()


def validar_nuevo(nombre: str, password: str) -> None:
    if not USUARIO_RE.match(nombre):
        raise ValueError("El usuario debe tener 3-40 caracteres: letras minúsculas, números, punto, guion o guion bajo.")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres.")


def crear_usuario(db: Session, nombre: str, password: str) -> User:
    """Crea un usuario. El primero hereda los datos de la época de una sola persona (ver `adoptar_datos_antiguos`)."""
    nombre = normalizar_usuario(nombre)
    validar_nuevo(nombre, password)
    if db.scalar(select(User).where(User.username == nombre)):
        raise ValueError(f"Ya existe el usuario «{nombre}».")
    primero = db.scalar(select(User.id).limit(1)) is None
    user = User(username=nombre, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    if primero:
        adoptar_datos_antiguos(db, user)
    db.commit()
    return user


def cambiar_password(db: Session, user: User, nueva: str, conservar_token_hash: str | None = None) -> None:
    validar_nuevo(user.username, nueva)
    user.password_hash = hash_password(nueva)
    for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id)):
        if s.token_hash != conservar_token_hash:  # se cierran las demás sesiones (si alguien la tenía, ya no entra)
            db.delete(s)
    db.commit()


def adoptar_datos_antiguos(db: Session, user: User) -> dict:
    """Pasa al primer usuario lo que antes era de «la» persona única: ajustes, scores, coches eliminados y análisis."""
    from ..models import UserSetting

    ajustes = 0
    for row in db.scalars(select(Setting)):
        if row.key in DEFAULTS and not db.get(UserSetting, (user.id, row.key)):
            db.add(UserSetting(user_id=user.id, key=row.key, value=row.value))
            ajustes += 1
    coches = 0
    for car in db.scalars(select(Car)):
        db.add(UserCar(user_id=user.id, car_id=car.id, score=car.score, score_detail=car.score_detail,
                       oculto=car.oculto, rentabilidad=car.rentabilidad))
        coches += 1
    for insp in db.scalars(select(Inspection).where(Inspection.usuario_id.is_(None))):
        insp.usuario_id = user.id
    user.configurado = ajustes > 0 or coches > 0  # si ya usaba la app, no tiene que pasar por la bienvenida
    return {"ajustes": ajustes, "coches": coches}


# ---------------------------------------------------------------- sesiones

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def abrir_sesion(db: Session, user: User) -> str:
    ahora = datetime.utcnow()
    for s in db.scalars(select(UserSession).where(UserSession.expira_en < ahora)):
        db.delete(s)  # limpieza de sesiones caducadas
    token = secrets.token_urlsafe(32)
    db.add(UserSession(token_hash=_hash_token(token), user_id=user.id, expira_en=ahora + timedelta(days=SESION_DIAS)))
    db.commit()
    return token


def cerrar_sesion(db: Session, token: str | None) -> None:
    if token and (s := db.get(UserSession, _hash_token(token))):
        db.delete(s)
        db.commit()


def usuario_de_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    s = db.get(UserSession, _hash_token(token))
    if not s or s.expira_en < datetime.utcnow():
        return None
    return db.get(User, s.user_id)


# ---------------------------------------------------------------- freno a las contraseñas a ciegas

_fallos: dict[str, list[float]] = {}
MAX_FALLOS, VENTANA_S = 5, 600


def _clave(ip: str, usuario: str) -> str:
    return f"{ip}|{usuario}"


def bloqueado(ip: str, usuario: str) -> bool:
    ahora = time.monotonic()
    recientes = [t for t in _fallos.get(_clave(ip, usuario), []) if ahora - t < VENTANA_S]
    _fallos[_clave(ip, usuario)] = recientes
    return len(recientes) >= MAX_FALLOS


def anotar_fallo(ip: str, usuario: str) -> None:
    _fallos.setdefault(_clave(ip, usuario), []).append(time.monotonic())


def limpiar_fallos(ip: str, usuario: str) -> None:
    _fallos.pop(_clave(ip, usuario), None)


def autenticar(db: Session, nombre: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == normalizar_usuario(nombre)))
    ok = verificar_password(password, user.password_hash if user else _FALSO)
    return user if (user and ok) else None


# ---------------------------------------------------------------- dependencia de FastAPI

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = usuario_de_token(db, request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "Inicia sesión para continuar")
    return user

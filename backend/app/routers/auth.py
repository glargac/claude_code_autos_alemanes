from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    usuario: str = Field(max_length=60)
    password: str = Field(max_length=200)


class PasswordIn(BaseModel):
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200)


def _salida(user: User) -> dict:
    return {"usuario": user.username, "configurado": user.configurado}


def _ip(request: Request) -> str:
    # Detrás de un proxy, uvicorn (--proxy-headers) ya pone aquí la IP real; fiarse a mano de X-Forwarded-For permitiría
    # saltarse el freno de contraseñas cambiando esa cabecera.
    return request.client.host if request.client else "?"


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip, nombre = _ip(request), auth.normalizar_usuario(body.usuario)
    if auth.bloqueado(ip, nombre):
        raise HTTPException(429, "Demasiados intentos fallidos. Espera unos minutos e inténtalo de nuevo.")
    user = auth.autenticar(db, nombre, body.password)
    if not user:
        auth.anotar_fallo(ip, nombre)
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    auth.limpiar_fallos(ip, nombre)
    response.set_cookie(auth.COOKIE, auth.abrir_sesion(db, user), max_age=auth.SESION_DIAS * 86400, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https", path="/")  # con --proxy-headers, el esquema real
    return _salida(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.cerrar_sesion(db, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(auth.current_user)):
    return _salida(user)


@router.post("/password")
def cambiar_password(body: PasswordIn, request: Request, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    if not auth.verificar_password(body.actual, user.password_hash):
        raise HTTPException(403, "La contraseña actual no es correcta")
    try:
        auth.cambiar_password(db, user, body.nueva, conservar_token_hash=auth._hash_token(request.cookies.get(auth.COOKIE, "")))
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return {"ok": True}

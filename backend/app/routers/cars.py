from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, aliased

from ..database import get_db
from ..models import Car, Status, User, UserCar
from ..schemas import CarOut, CarUpdate, EliminarIn, FavoritoIn, OtroEnlace
from ..services import rentabilidad as rentabilidad_service
from ..services.auth import current_user
from ..services.scoring import color_for
from ..services.settings_store import get_setting
from ..services.user_cars import asegurar

router = APIRouter(prefix="/api/cars", tags=["cars"], dependencies=[Depends(current_user)])


def _out(car: Car, uc: UserCar, weights: dict, others: dict[int, list[Car]], ajustes_hash: str | None = None) -> CarOut:
    """El coche es compartido; la puntuación, el color y el análisis de rentabilidad son del usuario (`uc`)."""
    out = CarOut.model_validate(car)
    out.score, out.score_detail, out.rentabilidad = uc.score, uc.score_detail, uc.rentabilidad
    out.farbe = color_for(uc.score, weights)
    out.otros_enlaces = [OtroEnlace.model_validate(o) for o in others.get(car.id, [])]
    rent = uc.rentabilidad
    if rent and rent.get("estado") == "listo" and ajustes_hash and rent.get("ajustes_hash") != ajustes_hash:
        out.rentabilidad = {**rent, "desactualizado": True}  # los costes de Ajustes cambiaron tras calcularlo
    return out


def _hash(db: Session, user_id: int) -> str:
    return rentabilidad_service.hash_ajustes(get_setting(db, "rentabilidad", user_id))


def _others(db: Session, ids: list[int]) -> dict[int, list[Car]]:
    """Anuncios duplicados (activos) de cada coche principal: {id principal: [duplicados]}."""
    grouped: dict[int, list[Car]] = {}
    if ids:
        for d in db.scalars(select(Car).where(Car.duplicado_de.in_(ids)).order_by(Car.preis)):
            grouped.setdefault(d.duplicado_de, []).append(d)
    return grouped


def _filtros(
    fuente: Literal["kleinanzeigen", "autoscout24"] | None = None,
    marke: str | None = None,
    modell: str | None = None,
    getriebe: str | None = None,
    status: Status | None = None,
    publicado_dias: int | None = None,
    inaktiv_anzeigen: bool = False,
    furgonetas: Literal["", "solo", "sin"] = "",
    favoritos: bool = False,
    precio_max: int | None = None,
    km_max: int | None = None,
    anio_desde: int | None = None,
) -> dict:
    return dict(fuente=fuente, marke=marke, modell=modell, getriebe=getriebe, status=status,
                publicado_dias=publicado_dias, inaktiv_anzeigen=inaktiv_anzeigen, furgonetas=furgonetas, favoritos=favoritos,
                precio_max=precio_max, km_max=km_max, anio_desde=anio_desde)


def _consulta(f: dict, user_id: int):
    """Coches que ve un usuario. Lista principal: los que encontró su sync (o un duplicado suyo cuyo principal es de otro
    portal) menos los que eliminó. Favoritos: los de todos (son compartidos), menos los que ELIMINÓ de su lista."""
    dup = aliased(Car)
    mios = select(UserCar.car_id).where(UserCar.user_id == user_id)
    eliminados = select(UserCar.car_id).where(UserCar.user_id == user_id, UserCar.oculto.is_(True))
    q = (select(Car, UserCar).outerjoin(UserCar, and_(UserCar.car_id == Car.id, UserCar.user_id == user_id))
         .where(Car.duplicado_de.is_(None))  # los duplicados cuelgan de su principal
         .order_by(UserCar.score.desc().nulls_last(), Car.id))
    if f.get("favoritos"):
        q = q.where(Car.favorito.is_(True))
    else:
        suyo_por_duplicado = select(dup.duplicado_de).where(dup.id.in_(mios), dup.duplicado_de.is_not(None))
        q = q.where(or_(Car.id.in_(mios), Car.id.in_(suyo_por_duplicado)))
    q = q.where(Car.id.not_in(eliminados))  # «Eliminar»: no se borra la fila (la sync la recrearía), no se muestra más
    if not f["inaktiv_anzeigen"]:
        q = q.where(Car.aktiv.is_(True))
    if f.get("furgonetas") == "solo":
        q = q.where(Car.furgoneta.is_(True))
    elif f.get("furgonetas") == "sin":
        q = q.where(Car.furgoneta.is_(False))
    if f["fuente"]:
        q = q.where(Car.source == f["fuente"])
    if f["marke"]:
        q = q.where(Car.marke == f["marke"])
    if f["modell"]:
        q = q.where(Car.modell.ilike(f"%{f['modell']}%"))
    if f["getriebe"]:
        q = q.where(Car.getriebe == f["getriebe"])
    if f["status"]:
        q = q.where(Car.status == f["status"].value)
    if f["publicado_dias"]:
        q = q.where(Car.veroeffentlicht_am >= datetime.utcnow() - timedelta(days=f["publicado_dias"]))
    if f.get("precio_max"):
        q = q.where(Car.preis <= f["precio_max"])
    if f.get("km_max"):
        q = q.where(Car.kilometer <= f["km_max"])
    if f.get("anio_desde"):
        q = q.where(Car.erstzulassung >= f["anio_desde"])
    return q


def _filas(db: Session, f: dict, user_id: int, limit: int | None = None) -> list[tuple[Car, UserCar]]:
    """(coche, vínculo del usuario) de la consulta. Si algún coche visible aún no tiene vínculo (un favorito del otro
    usuario, por ejemplo) se crea con su puntuación y se vuelve a consultar, para que el orden sea el correcto."""
    q = _consulta(f, user_id)
    if limit:
        q = q.limit(limit)
    filas = db.execute(q).all()
    if any(uc is None for _, uc in filas):
        asegurar(db, user_id, [c for c, uc in filas if uc is None])
        filas = db.execute(q).all()
    return [(c, uc) for c, uc in filas]


@router.get("", response_model=list[CarOut])
def list_cars(f: dict = Depends(_filtros), user: User = Depends(current_user), db: Session = Depends(get_db)):
    weights = get_setting(db, "weights", user.id)
    filas = _filas(db, f, user.id)
    others = _others(db, [c.id for c, _ in filas])
    h = _hash(db, user.id)
    return [_out(c, uc, weights, others, h) for c, uc in filas]


@router.post("/analizar-top", status_code=202)
async def analizar_top(n: int = Query(20, ge=1, le=50), f: dict = Depends(_filtros), user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """Lanza «Analizar rentabilidad» en segundo plano para los N primeros coches de la lista (mismos filtros que la
    lista), de uno en uno. Se saltan los que ya tienen informe al día y los «Andere» (sin modelo)."""
    return dict(rentabilidad_service.iniciar_lote(db, _filas(db, f, user.id, n), user.id))


@router.get("/analizar-top/status")
def analizar_top_status(user: User = Depends(current_user)):
    return dict(rentabilidad_service.lote_de(user.id))


@router.post("/favoritos")
def marcar_favoritos(body: FavoritoIn, db: Session = Depends(get_db)):
    """Añade o quita de Favoritos varios coches a la vez. Los favoritos son compartidos: los ven todos los usuarios."""
    cars = db.scalars(select(Car).where(Car.id.in_(body.ids))).all()
    if not cars:
        raise HTTPException(404, "Ningún auto encontrado")
    for car in cars:
        car.favorito = body.favorito
    db.commit()
    return {"actualizados": len(cars)}


@router.post("/eliminar")
def eliminar(body: EliminarIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Elimina coches de TU lista para siempre (los demás usuarios los siguen viendo). La fila se conserva marcada
    (`UserCar.oculto`): si se borrara, la próxima sync volvería a crear el anuncio. Su grupo de duplicados se elimina
    con él. Un favorito eliminado deja de salirte en Favoritos, pero sigue siendo favorito del resto."""
    cars = db.scalars(select(Car).where(Car.id.in_(body.ids))).all()
    if not cars:
        raise HTTPException(404, "Ningún auto encontrado")
    otros = _others(db, [c.id for c in cars])
    todos = cars + [d for c in cars for d in otros.get(c.id, [])]
    for uc in asegurar(db, user.id, todos).values():
        uc.oculto = True
    db.commit()
    return {"eliminados": len(cars)}


@router.patch("/{car_id}", response_model=CarOut)
def update_car(car_id: int, body: CarUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Estado, notas, cita y favorito son COMPARTIDOS: lo que cambia un usuario lo ve el otro."""
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Auto no encontrado")
    if body.status == Status.TERMIN and body.termin_am is None and car.termin_am is None:
        raise HTTPException(422, "Para 'Termin vereinbart' hay que indicar fecha y hora")
    if body.status is not None:
        car.status = body.status.value
        if body.status != Status.TERMIN:
            car.termin_am = None
    if body.termin_am is not None:
        car.termin_am = body.termin_am
    if body.notizen is not None:
        car.notizen = body.notizen
    if body.favorito is not None:
        car.favorito = body.favorito
    db.commit()
    return _salida(db, car, user)


def _salida(db: Session, car: Car, user: User) -> CarOut:
    uc = asegurar(db, user.id, [car])[car.id]
    return _out(car, uc, get_setting(db, "weights", user.id), _others(db, [car.id]), _hash(db, user.id))


@router.get("/{car_id}", response_model=CarOut)
def get_car(car_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Auto no encontrado")
    return _salida(db, car, user)


@router.post("/{car_id}/rentabilidad", response_model=CarOut, status_code=202)
async def analizar_rentabilidad(car_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lanza "Analizar rentabilidad" en segundo plano (precios en España + margen + informe de IA, 20-40 s) con TUS
    costes de Ajustes. Consultar el resultado con GET /api/cars/{id}: `rentabilidad.estado` pasa de "calculando" a
    "listo" o "error"."""
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Auto no encontrado")
    if not (car.preis and car.erstzulassung):
        raise HTTPException(422, "Faltan datos del coche (precio o año) para analizar su rentabilidad")
    uc = asegurar(db, user.id, [car])[car.id]
    rentabilidad_service.iniciar_analisis(db, car, uc)  # si ya hay uno en curso, no hace nada
    return _salida(db, car, user)

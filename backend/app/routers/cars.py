from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Car, Status
from ..schemas import CarOut, CarUpdate, OtroEnlace
from ..services import rentabilidad as rentabilidad_service
from ..services.scoring import color_for
from ..services.settings_store import get_setting

router = APIRouter(prefix="/api/cars", tags=["cars"])


def _out(car: Car, weights: dict, others: dict[int, list[Car]], ajustes_hash: str | None = None) -> CarOut:
    out = CarOut.model_validate(car)
    out.farbe = color_for(car.score, weights)
    out.otros_enlaces = [OtroEnlace.model_validate(o) for o in others.get(car.id, [])]
    rent = car.rentabilidad
    if rent and rent.get("estado") == "listo" and ajustes_hash and rent.get("ajustes_hash") != ajustes_hash:
        out.rentabilidad = {**rent, "desactualizado": True}  # los costes de Ajustes cambiaron tras calcularlo
    return out


def _hash(db: Session) -> str:
    return rentabilidad_service.hash_ajustes(get_setting(db, "rentabilidad"))


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
    mostrar_ocultos: bool = False,
    precio_max: int | None = None,
    km_max: int | None = None,
    anio_desde: int | None = None,
) -> dict:
    return dict(fuente=fuente, marke=marke, modell=modell, getriebe=getriebe, status=status,
                publicado_dias=publicado_dias, inaktiv_anzeigen=inaktiv_anzeigen, mostrar_ocultos=mostrar_ocultos,
                precio_max=precio_max, km_max=km_max, anio_desde=anio_desde)


def _consulta(f: dict):
    q = select(Car).where(Car.duplicado_de.is_(None)).order_by(Car.score.desc().nulls_last())  # los duplicados cuelgan de su principal
    if not f["inaktiv_anzeigen"]:
        q = q.where(Car.aktiv.is_(True))
    if not f["mostrar_ocultos"]:
        q = q.where(Car.oculto.is_(False))
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


@router.get("", response_model=list[CarOut])
def list_cars(f: dict = Depends(_filtros), db: Session = Depends(get_db)):
    weights = get_setting(db, "weights")
    cars = db.scalars(_consulta(f)).all()
    others = _others(db, [c.id for c in cars])
    h = _hash(db)
    return [_out(c, weights, others, h) for c in cars]


@router.post("/analizar-top", status_code=202)
async def analizar_top(n: int = Query(20, ge=1, le=50), f: dict = Depends(_filtros), db: Session = Depends(get_db)):
    """Lanza «Analizar rentabilidad» en segundo plano para los N primeros coches de la lista (mismos filtros que la
    lista, ocultos fuera), de uno en uno. Se saltan los que ya tienen informe al día y los «Andere» (sin modelo)."""
    coches = db.scalars(_consulta({**f, "mostrar_ocultos": False}).limit(n)).all()
    return dict(rentabilidad_service.iniciar_lote(db, coches))


@router.get("/analizar-top/status")
def analizar_top_status():
    return dict(rentabilidad_service.lote)


@router.patch("/{car_id}", response_model=CarOut)
def update_car(car_id: int, body: CarUpdate, db: Session = Depends(get_db)):
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
    if body.oculto is not None:  # el grupo de duplicados se oculta o se muestra junto
        car.oculto = body.oculto
        for d in _others(db, [car.id]).get(car.id, []):
            d.oculto = body.oculto
    db.commit()
    return _out(car, get_setting(db, "weights"), _others(db, [car.id]), _hash(db))


@router.get("/{car_id}", response_model=CarOut)
def get_car(car_id: int, db: Session = Depends(get_db)):
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Auto no encontrado")
    return _out(car, get_setting(db, "weights"), _others(db, [car.id]), _hash(db))


@router.post("/{car_id}/rentabilidad", response_model=CarOut, status_code=202)
async def analizar_rentabilidad(car_id: int, db: Session = Depends(get_db)):
    """Lanza "Analizar rentabilidad" en segundo plano (precios en España + margen + informe de IA, 20-40 s).
    Consultar el resultado con GET /api/cars/{id}: `rentabilidad.estado` pasa de "calculando" a "listo" o "error"."""
    car = db.get(Car, car_id)
    if not car:
        raise HTTPException(404, "Auto no encontrado")
    if not (car.preis and car.erstzulassung):
        raise HTTPException(422, "Faltan datos del coche (precio o año) para analizar su rentabilidad")
    rentabilidad_service.iniciar_analisis(db, car)  # si ya hay uno en curso, no hace nada
    return _out(car, get_setting(db, "weights"), _others(db, [car.id]), _hash(db))


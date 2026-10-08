from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Car, Status
from ..schemas import CarOut, CarUpdate
from ..services.scoring import color_for
from ..services.settings_store import get_setting

router = APIRouter(prefix="/api/cars", tags=["cars"])


def _out(car: Car, weights: dict) -> CarOut:
    out = CarOut.model_validate(car)
    out.farbe = color_for(car.score, weights)
    return out


@router.get("", response_model=list[CarOut])
def list_cars(
    marke: str | None = None,
    modell: str | None = None,
    getriebe: str | None = None,
    status: Status | None = None,
    publicado_dias: int | None = None,
    inaktiv_anzeigen: bool = False,
    db: Session = Depends(get_db),
):
    q = select(Car).order_by(Car.score.desc().nulls_last())
    if not inaktiv_anzeigen:
        q = q.where(Car.aktiv.is_(True))
    if marke:
        q = q.where(Car.marke == marke)
    if modell:
        q = q.where(Car.modell.ilike(f"%{modell}%"))
    if getriebe:
        q = q.where(Car.getriebe == getriebe)
    if status:
        q = q.where(Car.status == status.value)
    if publicado_dias:
        q = q.where(Car.veroeffentlicht_am >= datetime.utcnow() - timedelta(days=publicado_dias))
    weights = get_setting(db, "weights")
    return [_out(c, weights) for c in db.scalars(q)]


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
    db.commit()
    return _out(car, get_setting(db, "weights"))

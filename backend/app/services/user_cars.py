"""Vínculo usuario↔coche (`UserCar`): puntuación, «eliminado» y análisis de rentabilidad de cada usuario."""
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Car, UserCar
from .scoring import MarketIndex, compute_score
from .settings_store import get_setting


def mercado_global(db: Session) -> MarketIndex:
    """Índice de precios con todos los coches activos (cada coche cuenta una vez): es de todos, no de un usuario."""
    return MarketIndex(db.scalars(select(Car).where(Car.aktiv.is_(True), Car.duplicado_de.is_(None))))


def asegurar(db: Session, user_id: int, cars: Iterable[Car], market: MarketIndex | None = None) -> dict[int, UserCar]:
    """Devuelve el `UserCar` de cada coche, creando (con su puntuación) los que falten. Hace falta cuando un usuario ve
    un coche que no encontró su sync: un favorito del otro usuario, o el principal de un duplicado suyo."""
    cars = list({c.id: c for c in cars}.values())  # sin repetidos
    ids = [c.id for c in cars]
    existentes = {uc.car_id: uc for uc in db.scalars(select(UserCar).where(UserCar.user_id == user_id, UserCar.car_id.in_(ids)))} if ids else {}
    faltan = [c for c in cars if c.id not in existentes]
    if faltan:
        search, weights = get_setting(db, "search", user_id), get_setting(db, "weights", user_id)
        market = market or mercado_global(db)
        for car in faltan:
            score, detail = compute_score(car, weights, search, market)
            uc = UserCar(user_id=user_id, car_id=car.id, score=score, score_detail=detail)
            db.add(uc)
            existentes[car.id] = uc
        db.commit()
    return existentes

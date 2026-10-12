"""Qué queda fuera del alcance de la app: combustibles no deseados (eléctricos...) y furgonetas de carga.

El criterio de furgoneta es conservador y solo usa indicios explícitos de carga en el modelo o el título:
mejor dejar pasar una furgoneta dudosa (un Caddy, un Vito sin más pistas pueden ser turismos) que
descartar un coche legítimo. Se aplica a los anuncios nuevos al guardar y a los ya guardados al limpiar.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Car

# Modelos que son siempre furgonetas/comerciales (se compara con el modelo sin espacios ni guiones).
CARGO_MODELS = ("sprinter", "crafter", "transporter", "eload")
# Palabras sueltas del título que delatan carga (palabra completa: "Kofferraum" no cuenta).
CARGO_WORDS = {"kasten", "kastenwagen", "koffer", "kühlkoffer", "pritsche", "nfz", "lkw", "nutzfahrzeug", "kastenwagen"}


def _norm(text: str | None) -> str:
    return re.sub(r"[\s_-]+", "", (text or "").lower())


def is_cargo_van(modell: str | None, titel: str | None) -> bool:
    if any(m in _norm(modell) for m in CARGO_MODELS) or any(m in _norm(titel) for m in CARGO_MODELS):
        return True
    words = set(re.findall(r"[a-zäöüß]+", (titel or "").lower()))
    return bool(words & CARGO_WORDS)


def out_of_scope(item, wanted_fuels: set[str]) -> str | None:
    """Motivo por el que un anuncio (ScrapedCar o Car) no interesa, o None. `wanted_fuels` va en minúsculas."""
    fuel = (item.kraftstoffart or "").casefold()
    if fuel and fuel not in wanted_fuels:
        return f"combustible {item.kraftstoffart}"
    if is_cargo_van(item.modell, item.titel):
        return "furgoneta de carga"
    return None


def has_followup(car: Car) -> bool:
    return (car.status or "Neu") != "Neu" or bool((car.notizen or "").strip()) or car.termin_am is not None


def purge_out_of_scope(db: Session, wanted_fuels: set[str]) -> int:
    """Borra los coches guardados que ya no cumplen el alcance, salvo los que tienen seguimiento (no se
    pierde trabajo del usuario). Como la sync también los filtra al guardar, no se vuelven a crear."""
    removed = 0
    for car in db.scalars(select(Car)).all():
        if out_of_scope(car, wanted_fuels) and not has_followup(car):
            db.delete(car)
            removed += 1
    db.commit()
    return removed

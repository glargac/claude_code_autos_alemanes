"""Qué queda fuera del alcance de la app (combustibles no deseados: eléctricos...) y qué es una furgoneta.

Las furgonetas (Vito, Citan, Caddy, Sprinter...) SÍ entran: se etiquetan con `Car.furgoneta` y la lista las puede
filtrar. Antes se descartaban; las ya borradas se recuperan en la próxima sync. Se aplica al guardar y a los ya guardados al limpiar.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Car

# Modelos de furgoneta (palabras completas del modelo o del título; "Touran" o "Sharan" son monovolúmenes, no entran).
VAN_WORDS = {"sprinter", "crafter", "transporter", "vito", "citan", "caddy", "viano", "multivan", "california", "caravelle"}
# Palabras del título que delatan carga o que es un comercial (palabra completa: "Kofferraum" no cuenta).
CARGO_WORDS = {"kasten", "kastenwagen", "koffer", "kühlkoffer", "pritsche", "nfz", "lkw", "nutzfahrzeug"}


def es_furgoneta(modell: str | None, titel: str | None) -> bool:
    """Furgoneta (de carga, mixta o de pasajeros) según el modelo o el título. Solo sirve para etiquetar y filtrar."""
    words = set(re.findall(r"[a-zäöüß]+", f"{modell or ''} {titel or ''}".lower()))
    if "eload" in re.sub(r"[\s_-]+", "", f"{modell or ''} {titel or ''}".lower()):
        return True
    return bool(words & (VAN_WORDS | CARGO_WORDS))


def out_of_scope(item, wanted_fuels: set[str]) -> str | None:
    """Motivo por el que un anuncio (ScrapedCar o Car) no interesa, o None. `wanted_fuels` va en minúsculas."""
    fuel = (item.kraftstoffart or "").casefold()
    if fuel and fuel not in wanted_fuels:
        return f"combustible {item.kraftstoffart}"
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


def etiquetar_furgonetas(db: Session) -> int:
    """Pone `Car.furgoneta` a todos los coches guardados (barato; se llama al arrancar). Devuelve cuántos cambiaron."""
    cambiados = 0
    for car in db.scalars(select(Car)).all():
        valor = es_furgoneta(car.modell, car.titel)
        if car.furgoneta != valor:
            car.furgoneta, cambiados = valor, cambiados + 1
    db.commit()
    return cambiados

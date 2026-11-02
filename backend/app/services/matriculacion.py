"""Impuesto de matriculación (IEDMT) según las emisiones de CO₂ del coche.

Tramos de la península y Baleares (Ley 38/1992, art. 70): <120 g/km 0 %, 120-159 4,75 %, 160-199 9,75 %,
>=200 14,75 %. Canarias, Ceuta y Melilla tienen otros tipos y no se contemplan. Es una ESTIMACIÓN: la base real
es el valor de Hacienda del modelo con la depreciación por antigüedad, no el precio de compra, y la cifra de CO₂
que cuenta es la de la ficha técnica / certificado de conformidad.

El CO₂ sale del detalle de AutoScout24 (`Car.co2_gkm`). Kleinanzeigen no lo publica: se busca en el texto del
anuncio y, si no, se estima con la mediana de coches parecidos de la base. Sin ninguna de las tres, se usa el
porcentaje fijo de Ajustes y se avisa.
"""
import re
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Car

TRAMOS = ((120, 0.0), (160, 4.75), (200, 9.75), (None, 14.75))  # (límite superior exclusivo en g/km, % de la base)
MIN_COMPARABLES = 3
ANIOS_COMPARABLES = 3


def tipo_por_co2(co2: float) -> float:
    for limite, pct in TRAMOS:
        if limite is None or co2 < limite:
            return pct
    raise AssertionError("unreachable")


def co2_de_texto(texto: str) -> int | None:
    """CO₂ combinado que el vendedor escribe en el anuncio («CO2: 138 g/km», «138 g CO2/km»)."""
    for patron in (r"co\s*[2₂]\D{0,25}?(\d{2,3})\s*g\b", r"(\d{2,3})\s*g\s*(?:/\s*km\s*)?co\s*[2₂]"):
        for m in re.finditer(patron, texto or "", re.I):
            if 40 <= int(m.group(1)) <= 450:  # descarta números ajenos (consumo, años...)
                return int(m.group(1))
    return None


def estimar_co2(db: Session, car: Car) -> tuple[int | None, str]:
    """(g/km, origen) con origen «anuncio», «texto del anuncio» o «estimado con N coches parecidos»."""
    if car.co2_gkm:
        return car.co2_gkm, "anuncio"
    if valor := co2_de_texto(f"{car.titel} {car.beschreibung}"):
        return valor, "texto del anuncio"
    if not (car.marke and car.modell and car.erstzulassung) or car.modell.lower() == "andere":
        return None, "sin datos"
    q = select(Car.co2_gkm).where(
        Car.co2_gkm.is_not(None), Car.id != car.id, Car.marke == car.marke, Car.modell == car.modell,
        Car.erstzulassung.between(car.erstzulassung - ANIOS_COMPARABLES, car.erstzulassung + ANIOS_COMPARABLES),
    )
    if car.kraftstoffart:
        q = q.where(Car.kraftstoffart == car.kraftstoffart)
    valores = list(db.scalars(q))
    if len(valores) < MIN_COMPARABLES:
        return None, "sin datos"
    return round(median(valores)), f"estimado con {len(valores)} coches parecidos"

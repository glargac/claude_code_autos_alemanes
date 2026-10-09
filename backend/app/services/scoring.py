"""Scoring 1-10: componentes deterministas + rentabilidad estimada por LLM.

Cada componente devuelve 0-10; el score final es la media ponderada por los pesos
configurables (config.DEFAULT_WEIGHTS). Si no hay análisis LLM, su peso se
redistribuye entre los componentes deterministas.
"""
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from statistics import median

from ..models import Car

SPRING_SUMMER = {3, 4, 5, 6, 7, 8, 9}


def score_kilometer(km: int | None, km_min: int, km_max: int) -> float:
    if km is None:
        return 5.0
    if km <= km_min:
        return 10.0
    if km >= km_max:
        return 1.0
    return 10.0 - 9.0 * (km - km_min) / (km_max - km_min)


def score_tuev(tuev_bis: str | None, today: date | None = None) -> float:
    today = today or date.today()
    if not tuev_bis:
        return 3.0
    if tuev_bis.lower() == "neu":
        return 10.0
    try:
        year, month = (int(p) for p in tuev_bis.split("-"))
    except ValueError:
        return 3.0
    months_left = (year - today.year) * 12 + (month - today.month)
    if months_left <= 0:
        return 1.0
    return min(10.0, 3.0 + months_left * 7.0 / 24)  # 24+ meses = 10


def score_cabrio(is_cabrio: bool, today: date | None = None) -> float:
    if not is_cabrio:
        return 5.0  # neutro
    today = today or date.today()
    return 10.0 if today.month in SPRING_SUMMER else 4.0


# Precio: se compara con coches comparables de la propia base (mismo modelo, año ±2).
MIN_COMPARABLES = 5
YEAR_WINDOW = 2
GENERIC_MODELS = {"", "andere", "sonstige", "sonstiges", "other"}  # no identifican un modelo
CHEAP_RATIO, EXPENSIVE_RATIO = 0.70, 1.30  # precio/mediana que da 10 y 1 puntos


def _model_key(car: Car) -> tuple[str, str] | None:
    model = re.sub(r"[\s_-]+", "", (car.modell or "").lower())
    return None if model in GENERIC_MODELS else ((car.marke or "").lower(), model)


class MarketIndex:
    """Precios de los coches activos agrupados por modelo, para estimar un precio de referencia."""

    def __init__(self, cars: Iterable[Car]):
        self._groups: dict[tuple[str, str], list[tuple[int | None, int, int]]] = defaultdict(list)
        for c in cars:
            key = _model_key(c)
            if key and c.preis and c.erstzulassung:
                self._groups[key].append((c.id, c.erstzulassung, c.preis))

    def reference(self, car: Car) -> float | None:
        """Mediana de los precios comparables (mismo modelo, año ±2), sin contar el propio coche."""
        key = _model_key(car)
        if not key or not car.erstzulassung:
            return None
        prices = [
            p for cid, year, p in self._groups.get(key, [])
            if abs(year - car.erstzulassung) <= YEAR_WINDOW and (cid is None or cid != car.id)
        ]
        return median(prices) if len(prices) >= MIN_COMPARABLES else None


def score_precio(price: int | None, reference: float | None) -> float:
    """10 si cuesta un 30 % menos que sus comparables, 5 si igual, 1 si un 30 % más. Sin referencia: 5 (neutro)."""
    if not price or not reference:
        return 5.0
    ratio = price / reference
    if ratio <= 1:
        return min(10.0, 5.0 + 5.0 * (1 - ratio) / (1 - CHEAP_RATIO))
    return max(1.0, 5.0 - 4.0 * (ratio - 1) / (EXPENSIVE_RATIO - 1))


def compute_score(
    car: Car, weights: dict, search: dict, llm_score: float | None, market: MarketIndex | None = None
) -> tuple[float, dict]:
    parts = {
        "kilometer": score_kilometer(car.kilometer, search["kilometer_ab"], search["kilometer_bis"]),
        "klimaanlage": 10.0 if car.klimaanlage else 2.0,
        "tuev": score_tuev(car.tuev_bis),
        "cabrio_saison": score_cabrio(car.cabrio),
        "precio": score_precio(car.preis, market.reference(car) if market else None),
    }
    if llm_score is not None:
        parts["llm_rentabilidad"] = llm_score

    total_w = sum(weights[k] for k in parts) or 1.0
    score = sum(parts[k] * weights[k] for k in parts) / total_w
    return round(score, 1), {k: round(v, 1) for k, v in parts.items()}


def color_for(score: float | None, weights: dict) -> str:
    if score is None:
        return "gris"
    if score >= weights["umbral_verde"]:
        return "verde"
    if score >= weights["umbral_amarillo"]:
        return "amarillo"
    return "rojo"

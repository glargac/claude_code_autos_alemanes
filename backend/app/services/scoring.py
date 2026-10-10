"""Scoring 1-10: componentes deterministas + rentabilidad estimada por LLM.

Cada componente devuelve 0-10; el score final es la media ponderada por los pesos
configurables (config.DEFAULT_WEIGHTS). Si no hay análisis LLM, su peso se
redistribuye entre los componentes deterministas.
"""
import math
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date

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


# Precio: se compara con el precio esperado del mismo modelo, ajustado por año y km.
MIN_COMPARABLES = 5  # otros coches del mismo modelo necesarios para tener referencia
MIN_GROUP = 6  # tamaño de grupo (modelo) que aporta a la estimación de las pendientes
MIN_SLOPE_SAMPLES = 40  # coches necesarios para fiarse de las pendientes aprendidas
# Pendientes por defecto (fracción de log-precio) si hay pocos datos, y límites razonables.
DEFAULT_YEAR_SLOPE, DEFAULT_KM_SLOPE = 0.06, -0.003  # +6 % por año más reciente, -0,3 % por 1.000 km
YEAR_SLOPE_RANGE, KM_SLOPE_RANGE = (0.0, 0.12), (-0.008, 0.0)
GENERIC_MODELS = {"", "andere", "sonstige", "sonstiges", "other"}  # no identifican un modelo
CHEAP_RATIO, EXPENSIVE_RATIO = 0.70, 1.30  # precio/precio esperado que da 10 y 1 puntos


def _model_key(car: Car) -> tuple[str, str] | None:
    model = re.sub(r"[\s_-]+", "", (car.modell or "").lower())
    return None if model in GENERIC_MODELS else ((car.marke or "").lower(), model)


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


class MarketIndex:
    """Estima el precio esperado de un coche a partir de los demás del mismo modelo.

    Modelo hedónico en log-precio: ln(precio) = media del modelo + b_año·(año − media) + b_km·(km − media).
    Las pendientes b se aprenden de todos los modelos a la vez (regresión intra-grupo), y el coche
    evaluado se excluye de su propia referencia. Con 67 modelos reales predice mejor (error ≈23 %)
    que la mediana de coches de año parecido (≈26 %) y que la media sin ajustar (≈27 %).
    """

    def __init__(self, cars: Iterable[Car]):
        self._groups: dict[tuple[str, str], list[tuple[int | None, int, float, float]]] = defaultdict(list)
        for c in cars:
            key = _model_key(c)
            if key and c.preis and c.erstzulassung and c.kilometer is not None:
                self._groups[key].append((c.id, c.erstzulassung, c.kilometer / 1000, math.log(c.preis)))
        self.year_slope, self.km_slope = self._fit_slopes()

    def _fit_slopes(self) -> tuple[float, float]:
        sxx = sxy = syy = sxz = syz = 0.0
        n = 0
        for g in self._groups.values():
            if len(g) < MIN_GROUP:
                continue
            my, mk, ml = (sum(r[i] for r in g) / len(g) for i in (1, 2, 3))
            for _, y, km, lp in g:
                a, b, z = y - my, km - mk, lp - ml
                sxx, sxy, syy, sxz, syz, n = sxx + a * a, sxy + a * b, syy + b * b, sxz + a * z, syz + b * z, n + 1
        det = sxx * syy - sxy * sxy
        if n < MIN_SLOPE_SAMPLES or abs(det) < 1e-9:
            return DEFAULT_YEAR_SLOPE, DEFAULT_KM_SLOPE
        year = (sxz * syy - syz * sxy) / det
        km = (syz * sxx - sxz * sxy) / det
        return _clamp(year, YEAR_SLOPE_RANGE), _clamp(km, KM_SLOPE_RANGE)

    def reference(self, car: Car) -> float | None:
        """Precio esperado (€) de este coche según sus pares, o None si no hay suficientes."""
        key = _model_key(car)
        if not key or not car.erstzulassung:
            return None
        others = [r for r in self._groups.get(key, []) if r[0] is None or r[0] != car.id]
        if len(others) < MIN_COMPARABLES:
            return None
        my, mk, ml = (sum(r[i] for r in others) / len(others) for i in (1, 2, 3))
        km_term = self.km_slope * (car.kilometer / 1000 - mk) if car.kilometer is not None else 0.0
        return math.exp(ml + self.year_slope * (car.erstzulassung - my) + km_term)


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

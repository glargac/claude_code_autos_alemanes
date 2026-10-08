"""Scoring 1-10: componentes deterministas + rentabilidad estimada por LLM.

Cada componente devuelve 0-10; el score final es la media ponderada por los pesos
configurables (config.DEFAULT_WEIGHTS). Si no hay análisis LLM, su peso se
redistribuye entre los componentes deterministas.
"""
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


def compute_score(car: Car, weights: dict, search: dict, llm_score: float | None) -> tuple[float, dict]:
    parts = {
        "kilometer": score_kilometer(car.kilometer, search["kilometer_ab"], search["kilometer_bis"]),
        "klimaanlage": 10.0 if car.klimaanlage else 2.0,
        "tuev": score_tuev(car.tuev_bis),
        "cabrio_saison": score_cabrio(car.cabrio),
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

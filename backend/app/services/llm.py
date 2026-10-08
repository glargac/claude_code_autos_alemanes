"""Análisis de rentabilidad en la Costa del Sol mediante LLM (Anthropic)."""
import json

from ..config import env
from ..models import Car

PROMPT = """Eres analista de importación de coches usados de Alemania a la Costa del Sol (España).
Evalúa este vehículo: demanda histórica del modelo en la Costa del Sol, margen de reventa
tras costes de importación (transporte, matriculación, ITV, impuesto), y riesgo mecánico
conocido para ese modelo/motor/kilometraje.

Vehículo: {marke} {modell} ({titel}), Erstzulassung {erstzulassung}, {kilometer} km,
{preis} EUR, {kraftstoffart}, {getriebe}, TÜV: {tuev_bis}, Klimaanlage: {klimaanlage}.

Responde SOLO con JSON: {{"score": <0-10>, "analyse": "<máx. 2 frases en español>"}}"""


def analyze_profitability(car: Car) -> tuple[float | None, str | None]:
    if not env.anthropic_api_key:
        return None, None
    import anthropic

    client = anthropic.Anthropic(api_key=env.anthropic_api_key)
    msg = client.messages.create(
        model=env.llm_model,
        max_tokens=300,
        messages=[{"role": "user", "content": PROMPT.format(
            marke=car.marke, modell=car.modell, titel=car.titel,
            erstzulassung=car.erstzulassung, kilometer=car.kilometer, preis=car.preis,
            kraftstoffart=car.kraftstoffart, getriebe=car.getriebe,
            tuev_bis=car.tuev_bis, klimaanlage="sí" if car.klimaanlage else "no",
        )}],
    )
    try:
        data = json.loads(msg.content[0].text)
        return float(data["score"]), str(data["analyse"])
    except (ValueError, KeyError, IndexError):
        return None, None

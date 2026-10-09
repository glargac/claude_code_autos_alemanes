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


_client = None


def enabled() -> bool:
    return bool(env.anthropic_api_key)


def build_prompt(car: Car) -> str:
    """Se construye en el hilo principal: lee atributos del objeto ORM."""
    return PROMPT.format(
        marke=car.marke, modell=car.modell, titel=car.titel,
        erstzulassung=car.erstzulassung, kilometer=car.kilometer, preis=car.preis,
        kraftstoffart=car.kraftstoffart, getriebe=car.getriebe,
        tuev_bis=car.tuev_bis, klimaanlage="sí" if car.klimaanlage else "no",
    )


def analyze_prompt(prompt: str) -> tuple[float | None, str | None]:
    """Llamada bloqueante, apta para ejecutarse en un hilo. Nunca lanza: ante cualquier fallo
    (red, límite de uso, clave inválida, respuesta rara) devuelve (None, None) y se reintentará en la
    siguiente sync, para que un problema del LLM no aborte una sincronización de 30 minutos."""
    global _client
    if not enabled():
        return None, None
    try:
        import anthropic

        _client = _client or anthropic.Anthropic(api_key=env.anthropic_api_key, timeout=30.0)
        msg = _client.messages.create(
            model=env.llm_model, max_tokens=300, messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text
        data = json.loads(text[text.index("{") : text.rindex("}") + 1])  # tolera ```json ... ```
        return min(10.0, max(0.0, float(data["score"]))), str(data["analyse"])
    except Exception:
        return None, None

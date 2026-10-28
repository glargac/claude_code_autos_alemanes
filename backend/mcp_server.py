"""Servidor MCP: deja que Claude (Desktop o Code) consulte tus coches en lenguaje natural.

Es una capa fina sobre la API local de la app (el backend tiene que estar en marcha). No toca la base de datos ni
guarda nada: cada herramienta llama a un endpoint de `/api`. Se lanza solo, por stdio, desde la configuración de
Claude (ver README). Variable opcional: AUTOS_API_URL (por defecto http://127.0.0.1:8000).
"""
import asyncio
import os

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

BASE = os.environ.get("AUTOS_API_URL", "http://127.0.0.1:8000").rstrip("/")
mcp = MCPServer("autos-alemanes")


async def _api(method: str, path: str, **kw):
    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.request(method, f"/api{path}", **kw)
    except httpx.TransportError:
        raise ToolError(f"No se pudo conectar con la app en {BASE}. ¿Está en marcha el backend? (scripts/abrir.command)")
    if r.status_code >= 400:
        try:
            detalle = r.json().get("detail", r.text)
        except ValueError:
            detalle = r.text
        raise ToolError(f"La app respondió {r.status_code}: {detalle}")
    return r.json()


def _resumen(c: dict) -> dict:
    r = c.get("rentabilidad") or {}
    calc = r.get("calculo") or {}
    return {
        "id": c["id"], "coche": f"{c['marke']} {c['modell']}", "titulo": c["titel"], "anio": c["erstzulassung"],
        "km": c["kilometer"], "precio_eur": c["preis"], "combustible": c["kraftstoffart"], "cambio": c["getriebe"],
        "lugar": c["ort"], "fuente": c["source"], "url": c["url"], "puntuacion": c["score"], "estado": c["status"],
        "tuv_hasta": c["tuev_bis"], "oculto": c["oculto"],
        "rentabilidad": {"estado": r["estado"], "veredicto": r.get("veredicto"), "margen_neto_eur": calc.get("margen_neto"),
                         "roi_pct": calc.get("roi_pct")} if r else None,
    }


@mcp.tool()
async def listar_coches(marca: str = "", modelo: str = "", cambio: str = "", fuente: str = "", precio_max: int = 0,
                        km_max: int = 0, anio_desde: int = 0, publicado_dias: int = 0, estado: str = "",
                        limite: int = 10) -> list[dict]:
    """Lista coches de la lista principal, ordenados de mejor a peor puntuación (0-10).

    marca: Mercedes-Benz, BMW, Audi, Volkswagen o Porsche. cambio: Automatik o Manuell. fuente: kleinanzeigen o
    autoscout24. precio_max en euros; anio_desde es el año de matriculación mínimo. estado: Neu, Kontaktiert,
    "Termin vereinbart", Kaufoption o Abgelehnt. Los campos vacíos o 0 no filtran. Devuelve un resumen por coche; usa
    ver_coche para el detalle."""
    params = {"marke": marca, "modell": modelo, "getriebe": cambio, "fuente": fuente, "precio_max": precio_max,
              "km_max": km_max, "anio_desde": anio_desde, "publicado_dias": publicado_dias, "status": estado}
    coches = await _api("GET", "/cars", params={k: v for k, v in params.items() if v not in ("", 0)})
    return [_resumen(c) for c in coches[: max(1, min(limite, 50))]]


@mcp.tool()
async def ver_coche(id: int) -> dict:
    """Ficha completa de un coche: datos, desglose de la puntuación, notas, otros anuncios del mismo coche y, si ya
    se analizó, el informe de rentabilidad (mercado en España, margen, veredicto, riesgos y qué revisar)."""
    c = await _api("GET", f"/cars/{id}")
    out = _resumen(c)
    out |= {"descripcion": c.get("beschreibung") or None, "desglose_puntuacion": c["score_detail"], "notas": c["notizen"],
            "modelo_original_del_vendedor": c["modell_original"],
            "otros_anuncios": [f"{o['source']}: {o['url']} ({o['preis']} €)" for o in c["otros_enlaces"]]}
    r = c.get("rentabilidad")
    if r and r.get("estado") == "listo":
        out["informe_rentabilidad"] = {
            "veredicto": r.get("veredicto"), "calculo": r.get("calculo"), "informe_ia": r.get("informe"),
            "mercado_espana": {k: (r.get("mercado") or {}).get(k) for k in ("mediana", "n", "confianza", "confianza_motivo")},
            "desactualizado": r.get("desactualizado", False),
        }
    elif r:
        out["informe_rentabilidad"] = {"estado": r.get("estado"), "error": r.get("error")}
    return out


@mcp.tool()
async def analizar_rentabilidad(id: int) -> dict:
    """Calcula la rentabilidad de reventa de un coche en España: compara con anuncios de AutoScout24.es, calcula el
    margen neto y pide un informe a la IA. GASTA TOKENS de IA (~2.000) y tarda 20-40 s: úsala solo si el usuario lo
    pide o ya hay un coche concreto de interés."""
    await _api("POST", f"/cars/{id}/rentabilidad")
    for _ in range(40):
        await asyncio.sleep(3)
        if ((await _api("GET", f"/cars/{id}")).get("rentabilidad") or {}).get("estado") != "calculando":
            break
    return await ver_coche(id)


@mcp.tool()
async def estado_sync() -> dict:
    """Cuándo se actualizó cada fuente por última vez, si hay una sincronización en curso y su resultado."""
    return await _api("GET", "/sync/status")


if __name__ == "__main__":
    mcp.run()

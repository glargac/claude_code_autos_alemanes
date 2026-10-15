"""Precios de mercado en España (AutoScout24.es) para estimar el precio de reventa de un coche.

Los anuncios españoles tienen la misma estructura que los alemanes (JSON `__NEXT_DATA__`) y se filtran por
país (`cy=E`), modelo (ruta `/lst/<marca>/<modelo>`), año, km, combustible (`fuel=B|D`) y cambio (`gear=A|M`).
El texto del modelo que ya guardamos (de kleinanzeigen o AutoScout24.de) resuelve el modelo correcto en el sitio
español: probado con 13 modelos (116, 118, X1, A1, A3, Golf, Polo, Up, A 180, B 180, C 200, Citan, Tiguan).

Son precios de ANUNCIO, no de venta: `rentabilidad.py` aplica un descuento configurable. No usa tokens.
"""
import asyncio
import math
import random
import re
import statistics
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from ..scrapers.autoscout24 import BRAND_SLUG, page_props

BASE = "https://www.autoscout24.es"
MIN_COMPARABLES = 8  # con menos se amplía el criterio
MIN_USABLE = 3  # con menos de esto no hay estimación fiable
MAX_PAGINAS = 3  # 20 anuncios por página: la consulta amplia baja hasta 60 anuncios

# Ajuste de cada comparable al año y km del coche evaluado (fracción de log-precio; ver scoring.MarketIndex,
# que aprende estas pendientes de la base alemana: ≈ +5,7 % por año más reciente y −0,3 % por cada 1.000 km).
YEAR_SLOPE = 0.055
KM_SLOPE = -0.003

FUEL_CODE = {"benzin": "B", "diesel": "D"}
GEAR_CODE = {"automatik": "A", "manuell": "M"}


@dataclass(frozen=True)
class Criterio:
    """Qué tan estricta es la búsqueda de comparables."""

    anio: int  # ± años de Erstzulassung
    km_pct: float | None  # ± fracción de km; None = sin filtro
    mismo_combustible: bool
    mismo_cambio: bool

    def describir(self) -> str:
        partes = [f"año ±{self.anio}", f"km ±{round(self.km_pct * 100)} %" if self.km_pct else "cualquier km"]
        if self.mismo_combustible:
            partes.append("mismo combustible")
        if self.mismo_cambio:
            partes.append("mismo cambio")
        return ", ".join(partes)


# Del más estricto al más laxo: se para en el primero que da suficientes comparables.
ESCALERA = [
    Criterio(1, 0.25, True, True),
    Criterio(1, 0.25, True, False),
    Criterio(1, 0.40, True, False),
    Criterio(2, 0.50, True, False),
    Criterio(2, None, False, False),
]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def build_url(marke: str, modell: str, anio: int, km: int | None, combustible: str | None, cambio: str | None,
              criterio: Criterio, page: int = 1) -> str:
    query = {
        "atype": "C",
        "cy": "E",
        "fregfrom": anio - criterio.anio,
        "fregto": anio + criterio.anio,
        "damaged_listing": "exclude",
        "sort": "standard",
        "desc": 0,
    }
    if criterio.km_pct and km:
        query["kmfrom"] = max(0, round(km * (1 - criterio.km_pct)))
        query["kmto"] = round(km * (1 + criterio.km_pct))
    if criterio.mismo_combustible and (combustible or "").lower() in FUEL_CODE:
        query["fuel"] = FUEL_CODE[combustible.lower()]
    if criterio.mismo_cambio and (cambio or "").lower() in GEAR_CODE:
        query["gear"] = GEAR_CODE[cambio.lower()]
    if page > 1:
        query["page"] = page
    return f"{BASE}/lst/{BRAND_SLUG[marke]}/{_slug(modell)}?{urlencode(query)}"


def _combustible(texto: str | None) -> str | None:
    t = (texto or "").lower()
    return "benzin" if t.startswith(("gasolina", "benzin")) else "diesel" if t.startswith(("di", )) else None


def _cambio(texto: str | None) -> str | None:
    t = (texto or "").lower()
    return "automatik" if t.startswith("autom") else "manuell" if t.startswith(("manual", "schalt")) else None


def parse_listing(props: dict) -> list[dict]:
    """Anuncios de una página de resultados de AutoScout24.es."""
    out = []
    for x in props.get("listings", []):
        v, t = x.get("vehicle", {}), x.get("tracking", {})
        try:
            precio = int(x["price"]["priceRaw"])
            km = int(t["mileage"])
            anio = int(t["firstRegistration"][-4:])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({
            "modell": v.get("model") or "", "grupo": v.get("modelGroup") or "", "precio": precio, "km": km, "anio": anio,
            "combustible": _combustible(v.get("fuel")), "cambio": _cambio(v.get("transmission")),
            "url": BASE + x["url"].split("?")[0] if x.get("url") else None,
            "ort": ((x.get("location") or {}).get("city") or "").strip().title(),
            "vendedor": (x.get("seller") or {}).get("type"),
        })
    return out


def filtrar(anuncios: list[dict], criterio: Criterio, anio: int, km: int | None,
            combustible: str | None, cambio: str | None) -> list[dict]:
    """Subconjunto de anuncios que cumple un criterio. Se hace en local sobre lo ya descargado: una sola consulta
    amplia sirve para todos los niveles de la escalera (antes cada nivel era una consulta nueva y tardaba ~55 s)."""
    out = []
    for a in anuncios:
        if abs(a["anio"] - anio) > criterio.anio:
            continue
        if criterio.km_pct and km and not (km * (1 - criterio.km_pct) <= a["km"] <= km * (1 + criterio.km_pct)):
            continue
        if criterio.mismo_combustible and combustible and a["combustible"] and a["combustible"] != combustible.lower():
            continue
        if criterio.mismo_cambio and cambio and a["cambio"] and a["cambio"] != cambio.lower():
            continue
        out.append(a)
    return out


def elegir_criterio(anuncios: list[dict], anio: int, km: int | None, combustible: str | None,
                    cambio: str | None) -> tuple[int, list[dict]]:
    """Índice del criterio más estricto de la escalera que da comparables suficientes (o el que más da)."""
    mejor: tuple[int, list[dict]] | None = None
    for indice, criterio in enumerate(ESCALERA):
        subconjunto = filtrar(anuncios, criterio, anio, km, combustible, cambio)
        if len(subconjunto) >= MIN_COMPARABLES:
            return indice, subconjunto
        if mejor is None or len(subconjunto) > len(mejor[1]):
            mejor = (indice, subconjunto)
    return mejor


def deduplicar(anuncios: list[dict]) -> list[dict]:
    """Quita anuncios repetidos: un mismo coche aparece en dos páginas, o una cadena de concesionarios lo anuncia
    en varias sedes con distinta URL y localidad (visto: 4 sedes para los mismos 119.535 km y 9.490 €). Misma
    firma = mismo año, km y precio. Si no, inflan la muestra y sesgan la mediana."""
    vistos: dict[tuple, dict] = {}
    for a in anuncios:
        vistos.setdefault((a["anio"], a["km"], a["precio"]), a)
    return list(vistos.values())


def es_el_modelo(anuncio: dict, modell: str) -> bool:
    """El filtro de la URL a veces no acota del todo: se comprueba que el modelo del anuncio coincide."""
    objetivo = _norm(modell)
    return bool(objetivo) and objetivo in (_norm(anuncio["modell"]), _norm(anuncio["grupo"]))


def precio_ajustado(anuncio: dict, anio: int, km: int | None) -> float:
    """Precio del comparable trasladado al año y km del coche evaluado."""
    ajuste = YEAR_SLOPE * (anio - anuncio["anio"])
    if km:
        ajuste += KM_SLOPE * (km - anuncio["km"]) / 1000
    return anuncio["precio"] * math.exp(ajuste)


def _cuantil(valores: list[float], q: float) -> float:
    s = sorted(valores)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def estadisticas(anuncios: list[dict], anio: int, km: int | None) -> dict | None:
    """Mediana y rango del precio ajustado, descartando atípicos (1,5 × IQR). None si hay muy pocos."""
    if len(anuncios) < MIN_USABLE:
        return None
    ajustados = [(a, precio_ajustado(a, anio, km)) for a in anuncios]
    valores = [p for _, p in ajustados]
    q1, q3 = _cuantil(valores, 0.25), _cuantil(valores, 0.75)
    iqr = q3 - q1
    limpios = [(a, p) for a, p in ajustados if q1 - 1.5 * iqr <= p <= q3 + 1.5 * iqr] or ajustados
    precios = [p for _, p in limpios]
    particulares = [p for a, p in limpios if (a.get("vendedor") or "").lower().startswith("private")]  # "PrivateSeller" | "Dealer"
    cercanos = sorted(limpios, key=lambda ap: abs(ap[0]["anio"] - anio) * 30000 + abs(ap[0]["km"] - (km or ap[0]["km"])))[:6]
    return {
        "n": len(limpios),
        "n_descartados": len(ajustados) - len(limpios),
        "mediana": round(statistics.median(precios)),
        "p25": round(_cuantil(precios, 0.25)),
        "p75": round(_cuantil(precios, 0.75)),
        "n_particulares": len(particulares),
        "mediana_particulares": round(statistics.median(particulares)) if len(particulares) >= 3 else None,
        "minimo": min(a["precio"] for a, _ in limpios),
        "maximo": max(a["precio"] for a, _ in limpios),
        "muestra": [
            {k: a[k] for k in ("precio", "km", "anio", "ort", "vendedor", "url")} | {"modell": a["modell"]}
            for a, _ in cercanos
        ],
    }


def confianza(n: int, indice_criterio: int) -> str:
    """alta: muchos comparables con criterio estricto; baja: pocos o con criterio muy ampliado."""
    if n >= MIN_COMPARABLES and indice_criterio <= 1:
        return "alta"
    if n >= 5 and indice_criterio <= 3:
        return "media"
    return "baja"


class MercadoES:
    """Consulta AutoScout24.es con un navegador. Pocas peticiones por coche (normalmente 1-3)."""

    @asynccontextmanager
    async def _context(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(locale="es-ES")
                ctx.set_default_timeout(60000)
                yield ctx
            finally:
                await browser.close()

    @staticmethod
    async def _pause():
        await asyncio.sleep(random.uniform(1.5, 3.0))

    async def _fetch(self, page, url: str) -> dict:
        from ..scrapers.base import retry

        async def go():
            resp = await page.goto(url, wait_until="domcontentloaded")
            if resp is None or resp.status >= 400:
                raise RuntimeError(f"AutoScout24.es respondió HTTP {resp.status if resp else '?'} (¿bloqueo anti-bot?)")
            props = page_props(await page.content())
            if "pageQuery" not in props:
                raise PlaywrightError("la página no trajo datos (__NEXT_DATA__)")
            return props

        return await retry(go)

    async def _recoger(self, page, marke, modell, anio, km, combustible, criterio: Criterio, max_paginas: int) -> list[dict]:
        encontrados: list[dict] = []
        for n in range(1, max_paginas + 1):
            props = await self._fetch(page, build_url(marke, modell, anio, km, combustible, None, criterio, n))
            encontrados = deduplicar(encontrados + [a for a in parse_listing(props) if es_el_modelo(a, modell)])
            if n >= props.get("numberOfPages", 1):
                break
            await self._pause()
        return encontrados

    async def comparables(self, marke: str, modell: str, anio: int, km: int | None,
                          combustible: str | None, cambio: str | None) -> dict:
        """Estadísticas de precio en España para un coche. Una consulta amplia (año ±2, km ±50 %, mismo combustible)
        y, sobre lo descargado, se aplica la escalera de criterios en local hasta tener comparables suficientes."""
        if _norm(modell) in {"", "andere", "sonstige", "sonstiges", "other"}:
            raise ValueError("El anuncio no indica el modelo (\"Andere\"): no se pueden buscar comparables en España. "
                             "Si conoces el modelo, no hay forma de indicarlo todavía.")
        if marke not in BRAND_SLUG or not _slug(modell):
            raise ValueError(f"No se puede buscar en AutoScout24.es: marca {marke!r}, modelo {modell!r}")
        async with self._context() as ctx:
            page = await ctx.new_page()
            anuncios = await self._recoger(page, marke, modell, anio, km, combustible, ESCALERA[3], MAX_PAGINAS)
            if len(anuncios) < MIN_USABLE:  # último recurso: sin filtro de km ni de combustible
                await self._pause()
                anuncios = deduplicar(anuncios + await self._recoger(page, marke, modell, anio, km, combustible, ESCALERA[4], 2))

        indice, unicos = elegir_criterio(anuncios, anio, km, combustible, cambio)
        criterio = ESCALERA[indice]
        stats = estadisticas(unicos, anio, km)
        if stats is None:
            raise LookupError(
                f"Solo {len(unicos)} anuncio(s) comparable(s) en España para {marke} {modell} {anio}: no hay base para estimar el precio"
                + (". Puede que AutoScout24.es llame al modelo de otra forma." if not anuncios else "")
            )
        return {
            **stats,
            "confianza": confianza(stats["n"], indice),
            "criterio": criterio.describir(),
            "fuente": "autoscout24.es",
            "consultado_el": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }

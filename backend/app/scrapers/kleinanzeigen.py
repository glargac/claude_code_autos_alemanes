"""Scraper de kleinanzeigen.de (categoría Autos, c216).

Estrategia (verificada contra el sitio real):
  * La URL de búsqueda lleva los filtros: /s-autos/<ort>/preis:A:B/c216l<ID>r<km>+autos.marke_s:..
    El id de ubicación `l<ID>` es obligatorio (sin él se busca en toda Alemania) y se
    obtiene de s-ort-empfehlungen.json. Los rangos usan %2C: autos.ez_i:2010%2C2020.
  * La lista da id, título, precio, km, EZ, ubicación, foto y fecha.
  * El detalle incluye un bloque con atributos limpios (Getriebe, Kraftstoffart, HU_*, ...)
    y solo se pide para anuncios que aún no están en la base.
  * Un anuncio retirado redirige a la lista de búsqueda (la URL final ya no es /s-anzeige/).
"""
import asyncio
import random
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, async_playwright

from .base import Progress, ScrapedCar, Scraper

BASE = "https://www.kleinanzeigen.de"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
MAX_PAGES = 4  # 25 anuncios por página
RADII = [1, 2, 3, 5, 10, 20, 30, 50, 100, 150, 200]
BRAND_SLUG = {
    "Mercedes-Benz": "mercedes_benz",
    "BMW": "bmw",
    "Audi": "audi",
    "Volkswagen": "volkswagen",
    "Porsche": "porsche",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "deutschland"


def _radius(km: int) -> int:
    return min(RADII, key=lambda r: abs(r - km))


def build_url(params: dict, marke: str, loc_id: str, page: int = 1) -> str:
    ort = params["ort_oder_plz"]
    path = f"/s-autos/{_slug(ort)}/preis:{params['preis_ab']}:{params['preis_bis']}"
    if page > 1:
        path += f"/seite:{page}"
    modell = (params.get("modell") or "").strip()
    suffix = f"k0c216l{loc_id}r{_radius(params['umkreis_km'])}" if modell else f"c216l{loc_id}r{_radius(params['umkreis_km'])}"
    if modell:
        path += f"/{quote(_slug(modell))}"
    filters = [
        f"autos.marke_s:{BRAND_SLUG[marke]}",
        f"autos.ez_i:{params['erstzulassung_ab']}%2C{params['erstzulassung_bis']}",
        f"autos.km_i:{params['kilometer_ab']}%2C{params['kilometer_bis']}",
    ]
    fuels = [f.lower() for f in params.get("kraftstoffart", [])]
    if len(fuels) == 1:  # con Benzin+Diesel no hace falta filtrar
        filters.append(f"autos.fuel_s:{fuels[0]}")
    if params.get("getriebe"):
        filters.append(f"autos.shift_s:{params['getriebe'].lower()}")
    return f"{BASE}{path}/{suffix}+" + "+".join(filters)


# ---------- parsing (funciones puras, testeables con HTML guardado) ----------

def _int(text: str) -> int | None:
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


def _parse_date(text: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now()
    m = re.search(r"(Heute|Gestern),\s*(\d{1,2}):(\d{2})", text)
    if m:
        day = now if m.group(1) == "Heute" else now - timedelta(days=1)
        return day.replace(hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0)
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def parse_listing(html: str, marke: str, now: datetime | None = None) -> list[ScrapedCar]:
    soup = BeautifulSoup(html, "lxml")
    cars = []
    for art in soup.select("article[data-adid]"):
        href = art.get("data-href", "")
        lines = [t.strip() for t in art.get_text("\n").split("\n") if t.strip()]
        title_el = art.select_one("h3")
        if not title_el or not href:
            continue
        price = next((_int(l) for l in lines if "€" in l and not l.startswith("(")), None)
        km = next((_int(l) for l in lines if re.fullmatch(r"[\d.]+ km", l)), None)
        ez = next((int(m.group(1)) for l in lines if (m := re.fullmatch(r"EZ \d{2}/(\d{4})", l))), None)
        ort = next((l for l in lines if re.match(r"\d{5} ", l)), None)
        img = art.select_one("img[src*='img.kleinanzeigen.de']")
        snippet = art.select_one("p")
        cars.append(ScrapedCar(
            source="kleinanzeigen",
            external_id=art["data-adid"],
            url=BASE + href,
            marke=marke,
            modell="",
            titel=title_el.get_text(strip=True),
            image_url=img["src"].replace("rule=$_2.AUTO", "rule=$_59.AUTO") if img else None,  # $_2 = miniatura
            erstzulassung=ez,
            kilometer=km,
            preis=price,
            ort=ort,
            beschreibung=snippet.get_text(" ", strip=True) if snippet else "",
            veroeffentlicht_am=next((d for l in lines if (d := _parse_date(l, now))), None),
        ))
    return cars


def parse_detail(html: str) -> dict:
    """Extrae los atributos del vehículo del bloque de tracking + descripción de la página."""
    soup = BeautifulSoup(html, "lxml")
    attrs = dict(re.findall(r'"([A-Za-z_]+)":"([^"]*)"', html[html.find('"Erstzulassungsjahr"') - 2500:][:5000]))
    desc_el = soup.select_one("#viewad-description-text")
    desc = desc_el.get_text("\n", strip=True) if desc_el else ""
    title_el = soup.select_one("#viewad-title")
    title = title_el.get_text(" ", strip=True) if title_el else ""
    text = f"{title} {desc}".lower()

    out: dict = {"beschreibung": desc}
    info = soup.select_one("#viewad-extra-info")
    if info and (d := _parse_date(info.get_text(" "))):
        out["veroeffentlicht_am"] = d
    if attrs.get("Modell"):
        out["modell"] = attrs["Modell"].replace("_", " ").title() if not attrs["Modell"].isdigit() else attrs["Modell"]
    if attrs.get("Kraftstoffart"):
        out["kraftstoffart"] = attrs["Kraftstoffart"].capitalize()
    if attrs.get("Getriebe") in ("automatik", "manuell"):
        out["getriebe"] = attrs["Getriebe"].capitalize()
    out["klimaanlage"] = attrs.get("Klimaanlage") == "true" or "klima" in text
    out["cabrio"] = attrs.get("Fahrzeugtyp") == "cabrio" or "cabrio" in text or "cabriolet" in text
    if attrs.get("HU_Jahr") and attrs.get("HU_Monat"):
        out["tuev_bis"] = f"{int(attrs['HU_Jahr'])}-{int(attrs['HU_Monat']):02d}"
    elif m := re.search(r"(?:tüv|hu)[^\d\n]{0,12}(\d{1,2})[/.](20)?(\d{2})\b", text):
        out["tuev_bis"] = f"20{m.group(3)}-{int(m.group(1)):02d}"
    elif re.search(r"(?:tüv|hu)\s*(?:/\s*au\s*)?neu", text):
        out["tuev_bis"] = "neu"
    return out


# ---------- scraper ----------

class KleinanzeigenScraper(Scraper):
    name = "kleinanzeigen"

    @asynccontextmanager
    async def _context(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                yield await browser.new_context(locale="de-DE", user_agent=UA)
            finally:
                await browser.close()

    @staticmethod
    async def _pause():
        await asyncio.sleep(random.uniform(1.5, 3.0))

    async def _resolve_location(self, ctx: BrowserContext, query: str) -> str:
        r = await ctx.request.get(f"{BASE}/s-ort-empfehlungen.json?query={quote(query)}")
        ids = [k[1:] for k in (await r.json()) if k != "_0"]
        if not ids:
            raise ValueError(f"Ort oder PLZ no encontrado en kleinanzeigen.de: {query!r}")
        return ids[0]

    async def search(
        self, params: dict, known_ids: frozenset[str] = frozenset(), progress: Progress | None = None
    ) -> list[ScrapedCar]:
        report = progress or (lambda *_: None)
        results: dict[str, ScrapedCar] = {}
        async with self._context() as ctx:
            loc_id = await self._resolve_location(ctx, params["ort_oder_plz"])
            page = await ctx.new_page()
            marken = params["marken"]
            report("listas", 0, len(marken))
            for i, marke in enumerate(marken, 1):
                for n in range(1, MAX_PAGES + 1):
                    await page.goto(build_url(params, marke, loc_id, n), wait_until="domcontentloaded")
                    await page.wait_for_selector("article[data-adid], h1", timeout=15000)
                    cars = parse_listing(await page.content(), marke)
                    for c in cars:
                        results.setdefault(c.external_id, c)
                    if len(cars) < 25:
                        break
                    await self._pause()
                report("listas", i, len(marken))
                await self._pause()

            pending = [c for c in results.values() if c.external_id not in known_ids]  # los conocidos ya tienen detalle
            report("detalles", 0, len(pending))
            for done, car in enumerate(pending, 1):
                report("detalles", done - 1, len(pending))
                await page.goto(car.url, wait_until="domcontentloaded")
                if "/s-anzeige/" not in page.url:
                    continue
                detail = parse_detail(await page.content())
                for k, v in detail.items():
                    if v or k in ("klimaanlage", "cabrio"):
                        setattr(car, k, v)
                await self._pause()
            report("detalles", len(pending), len(pending))
        for car in results.values():
            if car.external_id not in known_ids:
                car.modell = car.modell or car.titel.split(" ")[0]
        return list(results.values())

    async def inactive_urls(self, urls: list[str], progress: Progress | None = None) -> set[str]:
        gone: set[str] = set()
        if not urls:
            return gone
        async with self._context() as ctx:
            page = await ctx.new_page()
            for i, url in enumerate(urls, 1):
                r = await page.goto(url, wait_until="domcontentloaded")
                if not (r and r.status < 400 and "/s-anzeige/" in page.url):
                    gone.add(url)
                if progress:
                    progress("verificar", i, len(urls))
                await self._pause()
        return gone

    async def is_active(self, url: str) -> bool:
        async with self._context() as ctx:
            page = await ctx.new_page()
            r = await page.goto(url, wait_until="domcontentloaded")
            return bool(r and r.status < 400 and "/s-anzeige/" in page.url)

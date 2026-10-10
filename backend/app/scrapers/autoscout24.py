"""Scraper de autoscout24.de (turismos usados).

Estrategia (verificada contra el sitio real):
  * Cada página (lista y detalle) incluye un bloque JSON `__NEXT_DATA__` con los datos estructurados;
    no se parsea HTML.
  * Los filtros van en la URL: /lst/<marca>[/<modelo>]?fregfrom=..&pricefrom=..&kmfrom=..&zip=..&zipr=..
    &fuel=B,D&gear=A|M. `zip` acepta PLZ o nombre de ciudad; si no reconoce el lugar lo sustituye en
    silencio por otro, así que se comprueba que el lugar devuelto contenga el pedido.
  * La lista no trae TÜV, Klimaanlage ni fecha de publicación: salen del detalle, que solo se pide
    para anuncios nuevos.
  * Un anuncio retirado redirige a la lista de la marca (la URL final ya no es /angebote/).
"""
import asyncio
import json
import random
import re
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright

from playwright.async_api import Error as PlaywrightError

from .base import Progress, ScrapedCar, Scraper, check_failure_rate, retry

BASE = "https://www.autoscout24.de"
MAX_PAGES = 5  # 20 anuncios por página, ordenados del más reciente al más antiguo
RADII = [10, 20, 30, 50, 100, 150, 200, 250]
BRAND_SLUG = {
    "Mercedes-Benz": "mercedes-benz",
    "BMW": "bmw",
    "Audi": "audi",
    "Volkswagen": "volkswagen",
    "Porsche": "porsche",
}
FUEL_CODE = {"Benzin": "B", "Diesel": "D"}
GEAR_CODE = {"Automatik": "A", "Manuell": "M"}
BERLIN = ZoneInfo("Europe/Berlin")
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _radius(km: int) -> int:
    return min(RADII, key=lambda r: abs(r - km))


def build_url(params: dict, marke: str, page: int = 1) -> str:
    path = f"/lst/{BRAND_SLUG[marke]}"
    if (params.get("modell") or "").strip():
        path += f"/{_slug(params['modell'])}"
    query = {
        "atype": "C",
        "cy": "D",
        "fregfrom": params["erstzulassung_ab"],
        "fregto": params["erstzulassung_bis"],
        "pricefrom": params["preis_ab"],
        "priceto": params["preis_bis"],
        "kmfrom": params["kilometer_ab"],
        "kmto": params["kilometer_bis"],
        "zip": params["ort_oder_plz"],
        "zipr": _radius(params["umkreis_km"]),
        "fuel": ",".join(FUEL_CODE[f] for f in params["kraftstoffart"]),  # siempre: excluye eléctricos
        "damaged_listing": "exclude",
        "sort": "age",  # más recientes primero
        "desc": 1,
    }
    if params.get("getriebe"):
        query["gear"] = GEAR_CODE[params["getriebe"]]
    if page > 1:
        query["page"] = page
    return f"{BASE}{path}?{urlencode(query, safe=',')}"


# ---------- parsing (funciones puras, testeables con HTML guardado) ----------

def page_props(html: str) -> dict:
    m = NEXT_DATA.search(html)
    return json.loads(m.group(1))["props"]["pageProps"] if m else {}


def _int(value) -> int | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return int(digits) if digits else None


def _getriebe(text: str | None) -> str | None:
    if not text:
        return None
    return "Automatik" if "automatik" in text.lower() else "Manuell" if "schalt" in text.lower() else None


def parse_listing(props: dict) -> list[ScrapedCar]:
    cars = []
    for x in props.get("listings", []):
        v, loc, t = x.get("vehicle", {}), x.get("location", {}), x.get("tracking", {})
        if not x.get("id") or not x.get("url"):
            continue
        img = (x.get("images") or [None])[0]
        cars.append(ScrapedCar(
            source="autoscout24",
            external_id=x["id"],
            url=BASE + x["url"].split("?")[0],
            marke=v.get("make") or "",
            modell=v.get("model") or v.get("modelGroup") or v.get("variant") or "",  # algunos anuncios (furgonetas) no lo traen
            titel=" ".join(p for p in (v.get("make"), v.get("model"), v.get("modelVersionInput")) if p),
            image_url=re.sub(r"/\d+x\d+\.webp$", "/720x540.webp", img) if img else None,
            erstzulassung=_int((t.get("firstRegistration") or "")[-4:]),
            kilometer=_int(t.get("mileage")),
            preis=x.get("price", {}).get("priceRaw"),
            kraftstoffart=v.get("fuel"),
            getriebe=_getriebe(v.get("transmission")),
            ort=" ".join(p for p in (loc.get("zip"), (loc.get("city") or "").strip()) if p) or None,
            beschreibung=v.get("subtitle") or "",
        ))
    return cars


def _html_to_text(html: str) -> str:
    return BeautifulSoup((html or "").replace("<br />", "\n").replace("<br>", "\n"), "lxml").get_text("\n", strip=True)


def parse_detail(props: dict) -> dict:
    """Atributos que no vienen en la lista. Devuelve {} si el anuncio ya no está activo."""
    d = props.get("listingDetails") or {}
    if not d or d.get("status") != "Active":
        return {}
    v = d.get("vehicle", {})
    equipment = [
        e.get("id", "")
        for cat in (v.get("equipment") or {}).values() if isinstance(cat, list)
        for e in cat if isinstance(e, dict)
    ]
    desc = _html_to_text(d.get("description", ""))
    body = f"{v.get('bodyType', '')} {(v.get('rawData', {}).get('bodyType', {}) or {}).get('raw', '')}".lower()

    out: dict = {
        "klimaanlage": any("klima" in e.lower() for e in equipment) or "klima" in desc.lower(),
        "cabrio": any(k in body for k in ("cabrio", "convertible", "roadster")),
    }
    if desc:
        out["beschreibung"] = desc
    if m := re.fullmatch(r"(\d{2})/(\d{4})", v.get("nextVehicleSafetyInspection") or ""):
        out["tuev_bis"] = f"{m.group(2)}-{m.group(1)}"
    elif v.get("newInspection"):
        out["tuev_bis"] = "neu"
    if ts := d.get("createdTimestampWithOffset"):
        out["veroeffentlicht_am"] = (
            datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(BERLIN).replace(tzinfo=None)
        )
    return out


def location_ok(requested: str, props: dict) -> bool:
    """AutoScout24 sustituye en silencio un lugar desconocido por otro: el devuelto debe contener el pedido."""
    returned = (props.get("pageQuery") or {}).get("zip", "")
    return requested.strip().casefold() in returned.casefold()


# ---------- scraper ----------

class AutoScout24Scraper(Scraper):
    name = "autoscout24"

    @asynccontextmanager
    async def _context(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(locale="de-DE")
                ctx.set_default_timeout(60000)  # el equipo puede ir lento (p. ej. tras reposo)
                yield ctx
            finally:
                await browser.close()

    @staticmethod
    async def _pause():
        await asyncio.sleep(random.uniform(1.5, 3.0))

    @staticmethod
    async def _props(page: Page, url: str, gone_ok: bool = False) -> tuple[dict, str]:
        """(pageProps, url final). Un HTTP de error es un fallo (posible bloqueo), salvo 404/410 si `gone_ok`."""
        resp = await page.goto(url, wait_until="domcontentloaded")
        status = resp.status if resp else 0
        if status in (404, 410) and gone_ok:
            return {}, page.url
        if status >= 400 or not resp:
            raise RuntimeError(f"AutoScout24 respondió HTTP {status} (¿bloqueo anti-bot?)")
        return page_props(await page.content()), page.url

    async def search(
        self, params: dict, known_ids: frozenset[str] = frozenset(), progress: Progress | None = None
    ) -> list[ScrapedCar]:
        report = progress or (lambda *_: None)
        self.warnings = []
        modell = re.sub(r"[\s-]", "", (params.get("modell") or "").lower())
        results: dict[str, ScrapedCar] = {}
        async with self._context() as ctx:
            page = await ctx.new_page()
            marken = params["marken"]
            report("listas", 0, len(marken))
            failed_brands = 0
            for i, marke in enumerate(marken, 1):
                n = 1
                try:
                    for n in range(1, MAX_PAGES + 1):
                        props, _ = await retry(lambda: self._props(page, build_url(params, marke, n)))
                        if n == 1 and not location_ok(params["ort_oder_plz"], props):
                            raise ValueError(
                                f"Ort oder PLZ no reconocido por AutoScout24: {params['ort_oder_plz']!r} "
                                f"(lo interpretó como {props.get('pageQuery', {}).get('zip')!r})"
                            )
                        cars = parse_listing(props)
                        for c in cars:
                            text = re.sub(r"[\s-]", "", c.titel.lower())
                            if not modell or modell in text:  # el filtro de modelo de la URL puede ignorarse
                                results.setdefault(c.external_id, c)
                        if len(cars) < 20 or n >= props.get("numberOfPages", 1):
                            break
                        await self._pause()
                except PlaywrightError as exc:
                    self.warnings.append(
                        f"{marke}: la página {n} no cargó ({type(exc).__name__}); se conserva lo leído antes"
                    )
                    failed_brands += n == 1
                report("listas", i, len(marken))
                await self._pause()

            if failed_brands == len(marken):
                raise RuntimeError(f"{self.name}: no se pudo cargar ninguna marca (¿sin conexión o bloqueo?)")

            pending = [c for c in results.values() if c.external_id not in known_ids]
            report("detalles", 0, len(pending))
            failed = 0
            for done, car in enumerate(pending, 1):
                report("detalles", done - 1, len(pending))
                try:
                    props, final_url = await retry(lambda: self._props(page, car.url, gone_ok=True))
                except PlaywrightError:
                    # Sin detalle no hay TÜV/Klima/fecha: se descarta y se reintentará en la próxima sync
                    # (si se guardara a medias, nunca se volvería a pedir el detalle).
                    del results[car.external_id]
                    failed += 1
                    check_failure_rate(failed, done, self.name)
                    continue
                if "/angebote/" in final_url:
                    for k, v in parse_detail(props).items():
                        setattr(car, k, v)
                await self._pause()
            report("detalles", len(pending), len(pending))
        return list(results.values())

    async def inactive_urls(self, urls: list[str], progress: Progress | None = None) -> set[str]:
        gone: set[str] = set()
        if not urls:
            return gone
        async with self._context() as ctx:
            page = await ctx.new_page()
            for i, url in enumerate(urls, 1):
                try:
                    props, final_url = await retry(lambda: self._props(page, url, gone_ok=True))
                except PlaywrightError:
                    continue  # no se pudo comprobar: se asume vigente y se reintenta en la próxima sync
                if "/angebote/" not in final_url or not parse_detail(props):
                    gone.add(url)
                if progress:
                    progress("verificar", i, len(urls))
                await self._pause()
        return gone

    async def is_active(self, url: str) -> bool:
        return url not in await self.inactive_urls([url])

from .base import Progress, ScrapedCar, Scraper


class MobileDeScraper(Scraper):
    name = "mobile_de"

    async def search(
        self, params: dict, known_ids: frozenset[str] = frozenset(), progress: Progress | None = None
    ) -> list[ScrapedCar]:
        # TODO (Fase 2): Playwright -> https://suchen.mobile.de/fahrzeuge/search.html
        #   con ?minFirstRegistrationDate / maxFirstRegistrationDate, minPrice / maxPrice,
        #   maxMileage, zipcode / ort, fuels, transmissions; paginar y parsear con BeautifulSoup.
        #   mobile.de tiene anti-bot: usar navegador real (headful), pausas y límites de ritmo.
        return []

    async def is_active(self, url: str) -> bool:
        # TODO: abrir `url`; 404 / redirección a la búsqueda / "nicht mehr verfügbar" => False.
        return True

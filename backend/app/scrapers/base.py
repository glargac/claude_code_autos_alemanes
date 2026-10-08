from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScrapedCar:
    source: str
    external_id: str
    url: str
    marke: str
    modell: str
    titel: str = ""
    image_url: str | None = None
    erstzulassung: int | None = None
    kilometer: int | None = None
    preis: int | None = None
    kraftstoffart: str | None = None
    getriebe: str | None = None
    ort: str | None = None
    tuev_bis: str | None = None
    klimaanlage: bool | None = None  # None = sin datos (detalle no consultado)
    cabrio: bool | None = None
    beschreibung: str = ""
    veroeffentlicht_am: datetime | None = None
    extra: dict = field(default_factory=dict)


# progress(fase, hecho, total) con fase en {"listas", "detalles", "verificar"}
Progress = Callable[[str, int, int], None]


class Scraper(ABC):
    name: str

    @abstractmethod
    async def search(
        self, params: dict, known_ids: frozenset[str] = frozenset(), progress: Progress | None = None
    ) -> list[ScrapedCar]:
        """Devuelve los anuncios activos que cumplen `params` (claves de DEFAULT_SEARCH).

        Para `known_ids` (ya en la base) basta con los datos de la lista: se omite el detalle.
        """

    @abstractmethod
    async def is_active(self, url: str) -> bool:
        """True si el anuncio sigue publicado (False = vendido / retirado)."""

    async def inactive_urls(self, urls: list[str], progress: Progress | None = None) -> set[str]:
        """URLs de `urls` que ya no están publicadas. Las fuentes pueden sobreescribirlo para reutilizar el navegador."""
        gone = set()
        for i, url in enumerate(urls, 1):
            if not await self.is_active(url):
                gone.add(url)
            if progress:
                progress("verificar", i, len(urls))
        return gone

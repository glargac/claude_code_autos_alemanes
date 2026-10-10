from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Status


class OtroEnlace(BaseModel):
    """Otro anuncio del mismo coche (otro portal, o repetido en el mismo)."""

    model_config = ConfigDict(from_attributes=True)

    source: str
    url: str
    preis: int | None
    ort: str | None


class CarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    url: str
    image_url: str | None
    marke: str
    modell: str
    titel: str
    erstzulassung: int | None
    kilometer: int | None
    preis: int | None
    kraftstoffart: str | None
    getriebe: str | None
    ort: str | None
    tuev_bis: str | None
    veroeffentlicht_am: datetime | None
    score: float | None
    score_detail: dict | None
    llm_analyse: str | None
    status: str
    termin_am: datetime | None
    notizen: str
    aktiv: bool
    farbe: str = "gris"
    otros_enlaces: list[OtroEnlace] = []


class CarUpdate(BaseModel):
    status: Status | None = None
    termin_am: datetime | None = None
    notizen: str | None = None


class SearchSettings(BaseModel):
    marken: list[Literal["Mercedes-Benz", "BMW", "Audi", "Volkswagen", "Porsche"]] = Field(min_length=1)
    modell: str = ""
    ort_oder_plz: str = Field(min_length=2)
    umkreis_km: int = Field(ge=1, le=200)
    erstzulassung_ab: int = Field(ge=1990, le=2030)
    erstzulassung_bis: int = Field(ge=1990, le=2030)
    preis_ab: int = Field(ge=0)
    preis_bis: int = Field(ge=0)
    kilometer_ab: int = Field(ge=0)
    kilometer_bis: int = Field(ge=0)
    kraftstoffart: list[Literal["Benzin", "Diesel"]] = Field(min_length=1)
    getriebe: Literal["", "Automatik", "Manuell"] = ""

    @model_validator(mode="after")
    def ranges_ordered(self):
        for lo, hi in (("erstzulassung_ab", "erstzulassung_bis"), ("preis_ab", "preis_bis"), ("kilometer_ab", "kilometer_bis")):
            if getattr(self, lo) > getattr(self, hi):
                raise ValueError(f"{lo} no puede ser mayor que {hi}")
        return self


class WeightsSettings(BaseModel):
    kilometer: float = Field(ge=0, le=1)
    klimaanlage: float = Field(ge=0, le=1)
    tuev: float = Field(ge=0, le=1)
    cabrio_saison: float = Field(ge=0, le=1)
    precio: float = Field(ge=0, le=1)
    llm_rentabilidad: float = Field(ge=0, le=1)
    umbral_verde: float = Field(ge=0, le=10)
    umbral_amarillo: float = Field(ge=0, le=10)

    @model_validator(mode="after")
    def thresholds_ordered(self):
        if self.umbral_amarillo >= self.umbral_verde:
            raise ValueError("umbral_amarillo debe ser menor que umbral_verde")
        if self.kilometer + self.klimaanlage + self.tuev + self.cabrio_saison + self.precio + self.llm_rentabilidad <= 0:
            raise ValueError("al menos un peso debe ser mayor que 0")
        return self


class AppSettings(BaseModel):
    sync_hour: int = Field(ge=0, le=23)
    auto_sync_on_open: bool
    max_age_hours: int = Field(ge=1, le=168)

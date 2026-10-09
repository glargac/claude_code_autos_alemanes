import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Status(str, enum.Enum):
    NEU = "Neu"
    KONTAKTIERT = "Kontaktiert"
    TERMIN = "Termin vereinbart"
    KAUFOPTION = "Kaufoption"
    ABGELEHNT = "Abgelehnt"


class Car(Base):
    __tablename__ = "cars"
    # Anti-duplicados: un anuncio es único por (fuente, id externo).
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))  # kleinanzeigen | autoscout24
    external_id: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(500))
    image_url: Mapped[str | None] = mapped_column(String(500))

    marke: Mapped[str] = mapped_column(String(50), index=True)
    modell: Mapped[str] = mapped_column(String(100), index=True)
    titel: Mapped[str] = mapped_column(String(300), default="")
    erstzulassung: Mapped[int | None] = mapped_column(Integer)
    kilometer: Mapped[int | None] = mapped_column(Integer)
    preis: Mapped[int | None] = mapped_column(Integer)
    kraftstoffart: Mapped[str | None] = mapped_column(String(30))
    getriebe: Mapped[str | None] = mapped_column(String(30), index=True)
    ort: Mapped[str | None] = mapped_column(String(100))
    tuev_bis: Mapped[str | None] = mapped_column(String(10))  # "YYYY-MM" o "neu"
    klimaanlage: Mapped[bool] = mapped_column(default=False)
    cabrio: Mapped[bool] = mapped_column(default=False)
    beschreibung: Mapped[str] = mapped_column(Text, default="")
    veroeffentlicht_am: Mapped[datetime | None] = mapped_column(DateTime)

    score: Mapped[float | None] = mapped_column(Float)
    score_detail: Mapped[dict | None] = mapped_column(JSON)
    llm_analyse: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(30), default=Status.NEU.value, index=True)
    termin_am: Mapped[datetime | None] = mapped_column(DateTime)
    notizen: Mapped[str] = mapped_column(Text, default="")

    aktiv: Mapped[bool] = mapped_column(default=True, index=True)  # False = Verkauft / Inaktiv
    erstmals_gesehen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    zuletzt_gesehen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    """Clave/valor JSON: 'search' (filtros) y 'weights' (pesos del scoring)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)

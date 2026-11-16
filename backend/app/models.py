import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    # Si el modelo se corrigió desde el título (el del vendedor lo contradecía), el valor que registró el vendedor
    modell_original: Mapped[str | None] = mapped_column(String(100))
    erstzulassung: Mapped[int | None] = mapped_column(Integer)
    erstzulassung_monat: Mapped[int | None] = mapped_column(Integer)
    kilometer: Mapped[int | None] = mapped_column(Integer)
    co2_gkm: Mapped[int | None] = mapped_column(Integer)  # g/km combinado (solo AutoScout24 lo publica)
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
    # Si es el mismo coche que otro anuncio (otro portal o repetido): id de la fila principal. Ver services/dedupe.py
    # Informe de "Analizar rentabilidad" (bajo demanda): estado, mercado en España, cálculo de margen e informe de IA
    rentabilidad: Mapped[dict | None] = mapped_column(JSON)
    duplicado_de: Mapped[int | None] = mapped_column(Integer, index=True)
    # «Eliminado» por el usuario (botón Eliminar): la fila se conserva para que la sync no recree el anuncio.
    furgoneta: Mapped[bool] = mapped_column(default=False, index=True)  # Vito, Citan, Caddy, Sprinter...; solo etiqueta/filtro
    favorito: Mapped[bool] = mapped_column(default=False, index=True)  # los que le interesan: único sitio con seguimiento
    oculto: Mapped[bool] = mapped_column(default=False, index=True)
    erstmals_gesehen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    zuletzt_gesehen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Setting(Base):
    """Clave/valor JSON: 'search' (filtros) y 'weights' (pesos del scoring)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class MercadoCache(Base):
    """Precios de mercado en España ya consultados (se reutilizan entre coches parecidos y entre días)."""

    __tablename__ = "mercado_cache"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)



class Inspection(Base):
    """Revisión técnica en campo de un coche (una por coche). El checklist vive en services/checklist.py."""

    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), unique=True, index=True)
    estado: Mapped[str] = mapped_column(String(20), default="en_curso", index=True)  # en_curso | en_qc | finalizada
    cliente: Mapped[str] = mapped_column(String(120), default="")
    vin: Mapped[str] = mapped_column(String(32), default="")
    informe_ia: Mapped[dict | None] = mapped_column(JSON)  # se genera bajo demanda (botón «Generar análisis IA»)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finalizada_en: Mapped[datetime | None] = mapped_column(DateTime)


class InspectionItem(Base):
    __tablename__ = "inspection_items"
    __table_args__ = (UniqueConstraint("inspection_id", "codigo", name="uq_inspection_codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(30))  # EXTERIOR-02: referencia en services/checklist.py
    estado: Mapped[str | None] = mapped_column(String(12))  # ok | aviso | incidencia | None (sin revisar)
    valor: Mapped[dict | None] = mapped_column(JSON)  # {"v": ...}: el valor extra según el tipo del punto
    observaciones: Mapped[str] = mapped_column(Text, default="")


class InspectionMedia(Base):
    __tablename__ = "inspection_media"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inspection_items.id"), index=True)
    archivo: Mapped[str] = mapped_column(String(120))  # nombre en data/inspections/<inspection_id>/; la miniatura lleva «_t»
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

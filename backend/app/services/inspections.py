"""Revisión técnica en campo: creación, progreso, resumen determinista y fotos de evidencia."""
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import env
from ..models import Car, Inspection, InspectionItem, InspectionMedia, User
from . import checklist, inspection_report, llm

MEDIA_URL = "/api/media/inspections"
ESTADOS_REVISION = ("en_curso", "en_qc", "finalizada")
MAX_LADO, MAX_LADO_MINIATURA = 1600, 360
MAX_FOTO_BYTES = 25 * 1024 * 1024


def media_dir() -> Path:
    ruta = Path(env.inspections_dir) if env.inspections_dir else Path(__file__).resolve().parents[2] / "data" / "inspections"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def crear_o_recuperar(db: Session, car: Car, cliente: str = "", usuario_id: int | None = None) -> Inspection:
    """Una revisión por coche: si ya existe se devuelve (para reanudarla), no se duplica."""
    insp = db.scalar(select(Inspection).where(Inspection.car_id == car.id))
    if not insp:
        insp = Inspection(car_id=car.id, cliente=cliente.strip(), usuario_id=usuario_id)
        db.add(insp)
        db.flush()
    asegurar_items(db, insp)
    db.commit()
    return insp


def asegurar_items(db: Session, insp: Inspection) -> list[InspectionItem]:
    """Crea los puntos que falten (revisión nueva o checklist ampliado) y devuelve solo los vigentes."""
    items = db.scalars(select(InspectionItem).where(InspectionItem.inspection_id == insp.id)).all()
    existentes = {i.codigo for i in items}
    for codigo in checklist.POR_CODIGO:
        if codigo not in existentes:
            nuevo = InspectionItem(inspection_id=insp.id, codigo=codigo)
            db.add(nuevo)
            items.append(nuevo)
    db.flush()
    return [i for i in items if i.codigo in checklist.POR_CODIGO]


def _conteo(items) -> dict:
    c = {"ok": 0, "aviso": 0, "incidencia": 0}
    for i in items:
        if i.estado in c:
            c[i.estado] += 1
    return c


def resultado_global(conteo: dict, revisados: int) -> str | None:
    """aprobado | atencion | no_recomendado (None si aún no se ha revisado nada). Reglas simples y visibles."""
    if revisados == 0:
        return None
    if conteo["incidencia"] >= 3:
        return "no_recomendado"
    if conteo["incidencia"] >= 1 or conteo["aviso"] >= 3:
        return "atencion"
    return "aprobado"


def resumen(items) -> dict:
    """Conteos globales y por categoría, progreso y resultado global (todo calculable sin IA)."""
    items = [i for i in items if i.codigo in checklist.POR_CODIGO]
    total = len(checklist.PUNTOS)
    conteo = _conteo(items)
    revisados = sum(conteo.values())
    por_cat = []
    for cat in checklist.CATEGORIAS:
        sub = [i for i in items if checklist.POR_CODIGO[i.codigo]["categoria"] == cat["clave"]]
        c = _conteo(sub)
        por_cat.append({"clave": cat["clave"], "nombre": cat["nombre"], "total": cat["total"],
                        "revisados": sum(c.values()), **c})
    return {"total": total, "revisados": revisados, "progreso": round(100 * revisados / total) if total else 0,
            **conteo, "categorias": por_cat, "resultado": resultado_global(conteo, revisados)}


def _url(insp_id: int, archivo: str) -> str:
    return f"{MEDIA_URL}/{insp_id}/{archivo}"


def detalle(db: Session, insp: Inspection) -> dict:
    items = asegurar_items(db, insp)
    db.commit()
    fotos: dict[int, list[InspectionMedia]] = {}
    ids = [i.id for i in items]
    for m in db.scalars(select(InspectionMedia).where(InspectionMedia.item_id.in_(ids)).order_by(InspectionMedia.id)):
        fotos.setdefault(m.item_id, []).append(m)
    orden = {c: n for n, c in enumerate(checklist.POR_CODIGO)}
    puntos = []
    for i in sorted(items, key=lambda i: orden[i.codigo]):
        punto = checklist.POR_CODIGO[i.codigo]
        puntos.append({**punto, "estado": i.estado, "valor": (i.valor or {}).get("v"), "observaciones": i.observaciones,
                       "fotos": [{"id": m.id, "url": _url(insp.id, m.archivo), "miniatura": _url(insp.id, _miniatura(m.archivo))}
                                 for m in fotos.get(i.id, [])]})
    car = db.get(Car, insp.car_id)
    autor = db.get(User, insp.usuario_id) if insp.usuario_id else None
    return {"id": insp.id, "car_id": insp.car_id, "estado": insp.estado, "cliente": insp.cliente, "vin": insp.vin,
            "creado_por": autor.username if autor else None,
            "creado_en": insp.creado_en, "actualizado_en": insp.actualizado_en, "finalizada_en": insp.finalizada_en,
            "informe_ia": _informe_ia(insp, puntos), "coche": _coche(car), "resumen": resumen(items), "puntos": puntos,
            "diagnostico_basico": inspection_report.diagnostico_basico(resumen(items), puntos), "ia": llm.info()}


def _informe_ia(insp: Inspection, puntos: list[dict]) -> dict | None:
    """Análisis de IA guardado; `desactualizado` si después de generarlo cambió algún punto."""
    if not insp.informe_ia:
        return None
    return {**insp.informe_ia, "desactualizado": insp.informe_ia.get("hash") != inspection_report.hash_revision(puntos)}


def _coche(car: Car | None) -> dict | None:
    if not car:
        return None
    return {k: getattr(car, k) for k in ("id", "marke", "modell", "titel", "erstzulassung", "kilometer", "preis",
                                          "image_url", "url", "source", "kraftstoffart", "getriebe")}


def _miniatura(archivo: str) -> str:
    return f"{Path(archivo).stem}_t.jpg"


def guardar_foto(insp_id: int, datos: bytes) -> str:
    """Guarda la foto reducida (≈1600 px) y su miniatura; las del móvil pesan 5-10 MB. Devuelve el nombre del archivo.
    Lanza ValueError si no es una imagen."""
    if len(datos) > MAX_FOTO_BYTES:
        raise ValueError("La foto pesa más de 25 MB")
    try:
        import io
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos)))  # respeta la orientación del móvil
        img = img.convert("RGB")
    except Exception:
        raise ValueError("El archivo no es una imagen válida") from None
    carpeta = media_dir() / str(insp_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"{uuid.uuid4().hex}.jpg"
    grande = img.copy()
    grande.thumbnail((MAX_LADO, MAX_LADO))
    grande.save(carpeta / nombre, "JPEG", quality=85, optimize=True)
    img.thumbnail((MAX_LADO_MINIATURA, MAX_LADO_MINIATURA))
    img.save(carpeta / _miniatura(nombre), "JPEG", quality=75)
    return nombre


def borrar_archivos(insp_id: int, archivo: str) -> None:
    for nombre in (archivo, _miniatura(archivo)):
        (media_dir() / str(insp_id) / nombre).unlink(missing_ok=True)


def borrar_carpeta(insp_id: int) -> None:
    shutil.rmtree(media_dir() / str(insp_id), ignore_errors=True)


def inicio_del_dia_utc() -> datetime:
    """Medianoche local de hoy, expresada en UTC naive (como se guardan las fechas)."""
    local = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).replace(tzinfo=None)

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Car, Inspection, InspectionItem, InspectionMedia
from ..schemas import InspeccionIn, InspeccionUpdate, PuntoUpdate
from ..services import checklist, inspection_report, inspections as svc

router = APIRouter(prefix="/api/inspections", tags=["inspections"])
MAX_FOTOS_POR_SUBIDA = 10


def _get(db: Session, insp_id: int) -> Inspection:
    insp = db.get(Inspection, insp_id)
    if not insp:
        raise HTTPException(404, "Revisión no encontrada")
    return insp


def _tocar(insp: Inspection) -> None:
    insp.actualizado_en = datetime.utcnow()


@router.get("/checklist")
def get_checklist():
    """Definición del checklist (categorías y puntos) para pintar el formulario."""
    return {"categorias": checklist.CATEGORIAS, "puntos": checklist.PUNTOS, "total": len(checklist.PUNTOS)}


@router.get("")
def listar(db: Session = Depends(get_db)):
    """Todas las revisiones con su coche y resumen, más las más recientes primero, y los KPIs del inicio."""
    todas = db.scalars(select(Inspection).order_by(Inspection.actualizado_en.desc())).all()
    items_por: dict[int, list[InspectionItem]] = {}
    for i in db.scalars(select(InspectionItem).where(InspectionItem.estado.is_not(None))):
        items_por.setdefault(i.inspection_id, []).append(i)
    filas = []
    for insp in todas:
        r = svc.resumen(items_por.get(insp.id, []))
        filas.append({"id": insp.id, "car_id": insp.car_id, "estado": insp.estado, "cliente": insp.cliente, "vin": insp.vin,
                      "creado_en": insp.creado_en, "actualizado_en": insp.actualizado_en, "finalizada_en": insp.finalizada_en,
                      "coche": svc._coche(db.get(Car, insp.car_id)),
                      "resumen": {k: v for k, v in r.items() if k != "categorias"}})
    hoy = svc.inicio_del_dia_utc()
    mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    en_curso = [f for f in filas if f["estado"] == "en_curso"]
    kpis = {
        "pendientes": len(en_curso),
        "en_qc": sum(f["estado"] == "en_qc" for f in filas),
        "completadas_hoy": sum(bool(f["finalizada_en"] and f["finalizada_en"] >= hoy) for f in filas),
        "total_mes": sum(f["creado_en"] >= mes for f in filas),
        "avance_medio": round(sum(f["resumen"]["progreso"] for f in en_curso) / len(en_curso)) if en_curso else 0,
        "completadas": sum(f["estado"] == "finalizada" for f in filas),
    }
    return {"kpis": kpis, "continuar": en_curso[0] if en_curso else None, "revisiones": filas}


@router.post("", status_code=201)
def crear(body: InspeccionIn, db: Session = Depends(get_db)):
    """Inicia la revisión de un coche, o devuelve la que ya tiene (una por coche)."""
    car = db.get(Car, body.car_id)
    if not car:
        raise HTTPException(404, "Auto no encontrado")
    return svc.detalle(db, svc.crear_o_recuperar(db, car, body.cliente))


@router.get("/{insp_id}")
def ver(insp_id: int, db: Session = Depends(get_db)):
    return svc.detalle(db, _get(db, insp_id))


@router.patch("/{insp_id}")
def actualizar(insp_id: int, body: InspeccionUpdate, db: Session = Depends(get_db)):
    insp = _get(db, insp_id)
    if body.cliente is not None:
        insp.cliente = body.cliente.strip()
    if body.vin is not None:
        insp.vin = body.vin.strip().upper()
    if body.estado is not None and body.estado != insp.estado:
        insp.estado = body.estado
        insp.finalizada_en = datetime.utcnow() if body.estado == "finalizada" else None
    _tocar(insp)
    db.commit()
    return svc.detalle(db, insp)


@router.delete("/{insp_id}")
def borrar(insp_id: int, db: Session = Depends(get_db)):
    """Borra la revisión con sus puntos y fotos (los archivos también)."""
    insp = _get(db, insp_id)
    ids = db.scalars(select(InspectionItem.id).where(InspectionItem.inspection_id == insp.id)).all()
    for m in db.scalars(select(InspectionMedia).where(InspectionMedia.item_id.in_(ids))):
        db.delete(m)
    for i in db.scalars(select(InspectionItem).where(InspectionItem.inspection_id == insp.id)):
        db.delete(i)
    db.delete(insp)
    db.commit()
    svc.borrar_carpeta(insp_id)
    return {"borrada": insp_id}


def _punto(db: Session, insp: Inspection, codigo: str) -> InspectionItem:
    if codigo not in checklist.POR_CODIGO:
        raise HTTPException(404, "Punto de control desconocido")
    svc.asegurar_items(db, insp)
    return db.scalar(select(InspectionItem).where(InspectionItem.inspection_id == insp.id, InspectionItem.codigo == codigo))


@router.patch("/{insp_id}/items/{codigo}")
def actualizar_punto(insp_id: int, codigo: str, body: PuntoUpdate, db: Session = Depends(get_db)):
    """Guarda un punto (se llama con cada toque, así no se pierde nada en campo). Devuelve el resumen actualizado."""
    insp = _get(db, insp_id)
    item = _punto(db, insp, codigo)
    enviados = body.model_fields_set
    if "estado" in enviados:
        item.estado = body.estado
    if "valor" in enviados:
        try:
            v = checklist.validar_valor(checklist.POR_CODIGO[codigo], body.valor)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        item.valor = None if v is None else {"v": v}
    if "observaciones" in enviados:
        item.observaciones = (body.observaciones or "").strip()
    _tocar(insp)
    db.commit()
    todos = svc.asegurar_items(db, insp)
    return {"codigo": codigo, "estado": item.estado, "valor": (item.valor or {}).get("v"),
            "observaciones": item.observaciones, "resumen": svc.resumen(todos)}


@router.post("/{insp_id}/items/{codigo}/media", status_code=201)
async def subir_fotos(insp_id: int, codigo: str, files: list[UploadFile], db: Session = Depends(get_db)):
    """Adjunta una o varias fotos como evidencia del punto."""
    if not 1 <= len(files) <= MAX_FOTOS_POR_SUBIDA:
        raise HTTPException(422, f"Sube entre 1 y {MAX_FOTOS_POR_SUBIDA} fotos a la vez")
    insp = _get(db, insp_id)
    item = _punto(db, insp, codigo)
    nuevas = []
    for f in files:
        try:
            archivo = await run_in_threadpool(svc.guardar_foto, insp.id, await f.read())
        except ValueError as e:
            raise HTTPException(422, f"{f.filename}: {e}") from None
        m = InspectionMedia(item_id=item.id, archivo=archivo)
        db.add(m)
        nuevas.append(m)
    _tocar(insp)
    db.commit()
    return [{"id": m.id, "url": svc._url(insp.id, m.archivo), "miniatura": svc._url(insp.id, svc._miniatura(m.archivo))} for m in nuevas]


@router.delete("/media/{media_id}")
def borrar_foto(media_id: int, db: Session = Depends(get_db)):
    m = db.get(InspectionMedia, media_id)
    if not m:
        raise HTTPException(404, "Foto no encontrada")
    item = db.get(InspectionItem, m.item_id)
    svc.borrar_archivos(item.inspection_id, m.archivo)
    db.delete(m)
    db.commit()
    return {"borrada": media_id}


@router.post("/{insp_id}/informe-ia")
async def generar_informe_ia(insp_id: int, db: Session = Depends(get_db)):
    """Genera el análisis de IA (diagnóstico + insight) a partir de los puntos marcados. Bajo demanda: gasta ~1.000-2.000
    tokens y tarda 5-20 s. Sin clave de IA responde 422 con el motivo."""
    insp = _get(db, insp_id)
    det = svc.detalle(db, insp)
    if det["resumen"]["revisados"] == 0:
        raise HTTPException(422, "Revisa al menos un punto antes de generar el análisis")
    informe, aviso = await run_in_threadpool(inspection_report.generar_ia, det["coche"] or {}, det["resumen"], det["puntos"])
    if not informe:
        raise HTTPException(422, aviso)
    insp.informe_ia = informe
    db.commit()
    return svc.detalle(db, insp)

"""Análisis de rentabilidad bajo demanda ("Analizar rentabilidad") de un coche.

Tres capas, de la más barata a la más cara:
  1. Precios de mercado en España (`mercado_es.py`): scraping, sin tokens, con caché de 3 días.
  2. Margen (`calcular_margen`): aritmética exacta con los costes y el perfil de Ajustes, sin tokens.
  3. Informe de IA (`llm.py`): valora la operación y redacta; solo recibe los números ya calculados.

Todo es ESTIMACIÓN ORIENTATIVA con cifras editables: no es asesoramiento fiscal. No incluye impuestos sobre el
beneficio (IRPF / Sociedades), ITP del comprador ni imprevistos.
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta

from playwright.async_api import Error as PlaywrightError
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Car, MercadoCache
from . import llm
from .mercado_es import MercadoES, _norm
from .settings_store import get_setting

log = logging.getLogger("uvicorn.error")
CACHE_DIAS = 3
_lock = asyncio.Lock()  # una consulta a AutoScout24.es a la vez: pocas peticiones y amables
_tasks: set[asyncio.Task] = set()  # referencias para que no se recojan las tareas en curso


# ---------------------------------------------------------------- cálculo de margen (puro)

def precio_referencia(mercado: dict, perfil: str) -> tuple[float, str]:
    """Precio de anuncio en España que se toma como referencia. Un particular compite con otros particulares."""
    if perfil == "particular" and mercado.get("mediana_particulares"):
        return mercado["mediana_particulares"], "anuncios de particulares"
    return mercado["mediana"], "todos los anuncios"


def _escenario(precio_anuncio_es: float, precio_de: float, a: dict) -> dict:
    """Margen neto para un precio de anuncio en España. Devuelve también las líneas del desglose (suman el margen)."""
    empresa = a["perfil"] == "empresa"
    iva_es, iva_de = a["iva_es_pct"] / 100, a["iva_de_pct"] / 100
    venta = precio_anuncio_es * (1 - a["descuento_venta_pct"] / 100)  # precio de venta esperado (IVA incluido si procede)
    compra_bruta = precio_de * (1 - a["descuento_compra_pct"] / 100)
    avisos = []

    if empresa and a["compra_con_iva_deducible"]:
        compra = compra_bruta / (1 + iva_de)  # adquisición intracomunitaria: sin IVA alemán; el español se autorepercute y deduce
        rebu = False
        if a["iva_reventa"] == "rebu":
            avisos.append("El REBU no es aplicable si compras con IVA deducible: se usa el régimen general.")
    else:
        compra = compra_bruta
        rebu = empresa and a["iva_reventa"] == "rebu"

    matriculacion = compra * a["impuesto_matriculacion_pct"] / 100
    costes = {
        "Transporte a la Costa del Sol": a["transporte"],
        "Gestoría, tasa DGT, ITV de importación y placas": a["gestoria_matriculacion"],
        f"Impuesto de matriculación ({a['impuesto_matriculacion_pct']:g} % de la compra)": matriculacion,
        "Preparación y pequeñas reparaciones": a["preparacion"],
        "Seguro y placas de tránsito": a["seguro_y_placas_transito"],
        "Gastos de venta (anuncios)": a["gastos_venta"],
        "Otros costes": a["otros_costes"],
    }
    costes = {k: v for k, v in costes.items() if v}

    iva_reventa = 0.0
    if empresa:
        if rebu:  # IVA solo sobre el margen (que lleva el IVA incluido)
            iva_reventa = max(0.0, venta - compra) * iva_es / (1 + iva_es)
        else:  # régimen general: el precio de venta lleva IVA incluido
            iva_reventa = venta - venta / (1 + iva_es)

    lineas = [("Venta esperada en España", venta)]
    if iva_reventa:
        lineas.append((f"IVA de la reventa ({'REBU, sobre el margen' if rebu else 'régimen general'})", -iva_reventa))
    lineas.append(("Compra en Alemania" + (" (sin IVA)" if compra != compra_bruta else ""), -compra))
    lineas += [(k, -v) for k, v in costes.items()]

    costes_total = sum(costes.values())
    inversion = compra + costes_total
    margen = venta - iva_reventa - compra - costes_total
    return {
        "venta_esperada": round(venta), "compra": round(compra), "costes_total": round(costes_total),
        "iva_reventa": round(iva_reventa), "inversion": round(inversion), "margen_neto": round(margen),
        "roi_pct": round(margen / inversion * 100, 1) if inversion else None,
        "lineas": [{"concepto": c, "importe": round(i)} for c, i in lineas], "avisos": avisos,
    }


def veredicto_numerico(margen: float, roi_pct: float | None, confianza: str, a: dict) -> str:
    """Veredicto solo con números (se usa si no hay informe de IA). Con poca confianza nunca da "Comprar"."""
    if margen >= a["margen_comprar_eur"] and (roi_pct or 0) >= a["roi_comprar_pct"]:
        return "Dudoso" if confianza == "baja" else "Comprar"
    return "Dudoso" if margen >= a["margen_dudoso_eur"] else "Descartar"


def calcular_margen(precio_de: int, mercado: dict, ajustes: dict) -> dict:
    """Margen neto estimado (central, pesimista con P25 y optimista con P75 del mercado español)."""
    ref, ref_fuente = precio_referencia(mercado, ajustes["perfil"])
    escala = ref / mercado["mediana"]  # traslada el rango P25-P75 al precio de referencia elegido
    central = _escenario(ref, precio_de, ajustes)
    pesimista = _escenario(mercado["p25"] * escala, precio_de, ajustes)
    optimista = _escenario(mercado["p75"] * escala, precio_de, ajustes)
    return {
        "perfil": ajustes["perfil"],
        "precio_de": precio_de,
        "referencia_es": round(ref),
        "referencia_fuente": ref_fuente,
        **central,
        "margen_pesimista": pesimista["margen_neto"],
        "margen_optimista": optimista["margen_neto"],
        "veredicto_numerico": veredicto_numerico(central["margen_neto"], central["roi_pct"], mercado["confianza"], ajustes),
    }


def hash_ajustes(ajustes: dict) -> str:
    """Huella de los ajustes con que se calculó: permite avisar si cambiaron los costes después."""
    return hashlib.sha1(json.dumps(ajustes, sort_keys=True).encode()).hexdigest()[:10]


# ---------------------------------------------------------------- textos para la IA

def _eur(x) -> str:
    return f"{x:,.0f} €".replace(",", ".") if x is not None else "?"


def _coche(car: Car) -> dict:
    return {
        "marca y modelo": f"{car.marke} {car.modell}", "título": car.titel, "primera matriculación": car.erstzulassung,
        "kilometraje": f"{car.kilometer:,} km".replace(",", ".") if car.kilometer else None,
        "combustible": car.kraftstoffart, "cambio": car.getriebe, "TÜV hasta": car.tuev_bis,
        "aire acondicionado": "sí" if car.klimaanlage else "no consta", "descapotable": "sí" if car.cabrio else None,
        "precio pedido en Alemania": _eur(car.preis), "ubicación": car.ort, "portal": car.source,
        "descripcion": car.beschreibung,
    }


def _calculo_txt(c: dict) -> str:
    lineas = "\n".join(f"  {l['concepto']}: {_eur(l['importe'])}" for l in c["lineas"])
    return (
        f"Margen neto estimado: {_eur(c['margen_neto'])} (rango {_eur(c['margen_pesimista'])} a {_eur(c['margen_optimista'])})\n"
        f"Rentabilidad sobre lo invertido: {c['roi_pct']} % | inversión total: {_eur(c['inversion'])}\n"
        f"Veredicto solo por números: {c['veredicto_numerico']}\nDesglose:\n{lineas}"
    )


def _mercado_txt(m: dict, c: dict) -> str:
    part = f" | mediana de particulares: {_eur(m['mediana_particulares'])} ({m['n_particulares']})" if m.get("mediana_particulares") else ""
    return (
        f"{m['n']} anuncios comparables | mediana ajustada: {_eur(m['mediana'])} | rango típico: {_eur(m['p25'])}-{_eur(m['p75'])} | "
        f"mín-máx: {_eur(m['minimo'])}-{_eur(m['maximo'])}{part}\nCriterio de comparación: {m['criterio']} | "
        f"confianza: {m['confianza']}\nReferencia usada: {_eur(c['referencia_es'])} ({c['referencia_fuente']}; "
        f"son precios de anuncio y se aplica un descuento de venta)"
    )


# ---------------------------------------------------------------- orquestación

def _clave_cache(car: Car) -> str:
    return "|".join([car.marke, _norm(car.modell), str(car.erstzulassung), (car.kraftstoffart or "").lower(),
                     (car.getriebe or "").lower(), str((car.kilometer or 0) // 10000)])


async def _mercado(db: Session, car: Car) -> tuple[dict, bool]:
    """Precios en España del coche (de la caché si es reciente). Devuelve (mercado, desde_cache)."""
    clave = _clave_cache(car)
    hit = db.get(MercadoCache, clave)
    if hit and datetime.utcnow() - hit.fetched_at < timedelta(days=CACHE_DIAS):
        return hit.data, True
    async with _lock:
        mercado = await MercadoES().comparables(car.marke, car.modell, car.erstzulassung, car.kilometer,
                                                 car.kraftstoffart, car.getriebe)
    db.merge(MercadoCache(key=clave, data=mercado, fetched_at=datetime.utcnow()))
    db.commit()
    return mercado, False


def _mensaje_error(exc: Exception) -> str:
    if isinstance(exc, (LookupError, ValueError)):  # pocos comparables, modelo no soportado...: el mensaje ya es claro
        return str(exc)
    if isinstance(exc, RuntimeError):  # p. ej. HTTP 403 (bloqueo)
        return f"AutoScout24.es no respondió como se esperaba: {exc}"
    if isinstance(exc, (PlaywrightError, OSError, TimeoutError)):
        return f"No se pudo consultar AutoScout24.es ({type(exc).__name__}). Comprueba la conexión y vuelve a intentarlo."
    return f"Error inesperado al analizar ({type(exc).__name__}). Revisa el registro del backend."


def _guardar(db: Session, car: Car, datos: dict) -> None:
    car.rentabilidad = datos  # se reasigna entero: SQLAlchemy no detecta cambios dentro de un JSON
    db.commit()


async def _analizar(car_id: int) -> None:
    with SessionLocal() as db:
        car = db.get(Car, car_id)
        if car is None:
            return
        ahora = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        try:
            ajustes = get_setting(db, "rentabilidad")
            mercado, de_cache = await _mercado(db, car)
            calculo = calcular_margen(car.preis, mercado, ajustes)
            informe, aviso_ia = None, None
            if llm.enabled():
                prompt = llm.build_report_prompt(_coche(car), _calculo_txt(calculo), _mercado_txt(mercado, calculo), ajustes["perfil"])
                informe, aviso_ia = await asyncio.to_thread(llm.analyze_report, prompt)
            else:
                aviso_ia = llm.SIN_CLAVE
            _guardar(db, car, {
                "estado": "listo", "error": None, "calculado_el": ahora, "perfil": ajustes["perfil"],
                "ajustes_hash": hash_ajustes(ajustes), "mercado": mercado, "mercado_de_cache": de_cache, "calculo": calculo,
                "informe": informe, "aviso_ia": aviso_ia,
                "veredicto": informe["veredicto"] if informe else calculo["veredicto_numerico"],
                "veredicto_origen": "ia" if informe else "numerico",
            })
        except Exception as exc:  # se muestra en la tarjeta
            if not isinstance(exc, (LookupError, ValueError, RuntimeError, PlaywrightError, OSError, TimeoutError)):
                log.exception("Fallo inesperado en el análisis de rentabilidad del coche %s", car_id)
            _guardar(db, car, {"estado": "error", "error": _mensaje_error(exc), "calculado_el": ahora})


def iniciar_analisis(db: Session, car: Car) -> bool:
    """Lanza el análisis en segundo plano. False si ya hay uno en curso para ese coche."""
    if (car.rentabilidad or {}).get("estado") == "calculando":
        return False
    _guardar(db, car, {"estado": "calculando", "error": None,
                       "iniciado_el": datetime.utcnow().isoformat(timespec="seconds") + "Z"})
    tarea = asyncio.create_task(_analizar(car.id))
    _tasks.add(tarea)
    tarea.add_done_callback(_tasks.discard)
    return True


def reiniciar_interrumpidos(db: Session) -> int:
    """Al arrancar: un análisis que figura "calculando" quedó cortado por un reinicio del backend."""
    n = 0
    for car in db.query(Car).filter(Car.rentabilidad.isnot(None)):
        if (car.rentabilidad or {}).get("estado") == "calculando":
            car.rentabilidad = {"estado": "error", "error": "El análisis se interrumpió (el backend se reinició). Vuelve a lanzarlo."}
            n += 1
    db.commit()
    return n

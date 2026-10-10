"""Detección de anuncios duplicados (el mismo coche publicado en varios portales o repetido en uno).

Los duplicados NO se borran: cada fila se conserva (la sync identifica los anuncios por fuente + id
externo y, si se borraran, los volvería a crear). Una de las filas de cada grupo es la "principal" y las
demás apuntan a ella con `duplicado_de`; la lista solo muestra las principales, con los enlaces de las otras.

Un falso positivo esconde un coche distinto de la lista, así que las reglas son conservadoras: exigen
misma marca, modelo, año, combustible y Getriebe, y varias señales a la vez (km casi idénticos, precio
parecido y localidad o título parecidos).
"""
import re
from collections import defaultdict
from datetime import datetime
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Car

GENERIC_MODELS = {"", "andere", "sonstige", "sonstiges", "other"}


def _norm(text: str | None) -> str:
    return re.sub(r"[\s_-]+", "", (text or "").lower())


def _model_key(car: Car) -> tuple[str, str, int] | None:
    model = _norm(car.modell)
    if model in GENERIC_MODELS or not car.erstzulassung:
        return None
    return ((car.marke or "").lower(), model, car.erstzulassung)


def _plz(car: Car) -> str | None:
    m = re.match(r"\d{5}", car.ort or "")
    return m.group(0) if m else None


def _city(car: Car) -> str:
    m = re.match(r"\d{5}\s+([^\s,(]+)", car.ort or "")
    return m.group(1).lower() if m else ""


def _title_tokens(car: Car) -> set[str]:
    return {t for t in re.findall(r"[a-zäöüß0-9]+", (car.titel or "").lower()) if len(t) > 1}


def _similar_title(a: Car, b: Car) -> float:
    ta, tb = _title_tokens(a), _title_tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def is_duplicate(a: Car, b: Car) -> bool:
    """¿Son el mismo coche? Conservador: mejor dejar un duplicado sin detectar que esconder un coche distinto."""
    key = _model_key(a)
    if a.id == b.id or key is None or key != _model_key(b):
        return False
    if not (a.kilometer and b.kilometer and a.preis and b.preis):
        return False
    for field in ("kraftstoffart", "getriebe"):
        x, y = getattr(a, field), getattr(b, field)
        if x and y and x.lower() != y.lower():
            return False

    km_rel = abs(a.kilometer - b.kilometer) / max(a.kilometer, b.kilometer)
    price_rel = abs(a.preis - b.preis) / max(a.preis, b.preis)
    round_km = a.kilometer % 100 == 0 or b.kilometer % 100 == 0  # los vendedores redondean (98.500, 109.800...)
    same_place = (_plz(a) is not None and _plz(a) == _plz(b)) or (_city(a) != "" and _city(a) == _city(b))

    # 1) km idénticos y precio casi igual, en el mismo sitio (o con un km tan concreto que no es casualidad)
    if km_rel == 0 and price_rel <= 0.03 and (same_place or not round_km):
        return True
    # 2) km casi idénticos (≤0,3 %), precio ±2 % y algo más que lo respalde: mismo sitio o título parecido
    if km_rel <= 0.003 and price_rel <= 0.02 and (same_place or _similar_title(a, b) >= 0.5):
        return True
    # 3) km casi idénticos (≤0,1 %) y no redondos, precio ±2 %: el odómetro se actualizó entre publicaciones
    if km_rel <= 0.001 and price_rel <= 0.02 and not round_km:
        return True
    return False


def _completeness(car: Car) -> int:
    return sum(v is not None for v in (car.tuev_bis, car.getriebe, car.veroeffentlicht_am, car.kraftstoffart, car.image_url))


def _preference(car: Car) -> tuple:
    """Orden para elegir la principal: la que ya tiene seguimiento, la más completa y la más antigua."""
    has_crm = (car.status or "Neu") != "Neu" or bool((car.notizen or "").strip()) or car.termin_am is not None
    return (not has_crm, -_completeness(car), car.erstmals_gesehen or datetime.min, car.id or 0)


def find_duplicates(cars: Iterable[Car]) -> dict[int, int]:
    """{id del duplicado: id de la principal}. Agrupa por componentes conexas de la relación `is_duplicate`."""
    blocks: dict[tuple, list[Car]] = defaultdict(list)
    for c in cars:
        key = _model_key(c)
        if key:
            blocks[key].append(c)

    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for group in blocks.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if is_duplicate(a, b):
                    parent[find(a.id)] = find(b.id)

    clusters: dict[int, list[Car]] = defaultdict(list)
    by_id = {c.id: c for g in blocks.values() for c in g}
    for cid in list(parent):
        clusters[find(cid)].append(by_id[cid])

    result: dict[int, int] = {}
    for members in clusters.values():
        if len(members) < 2:
            continue
        primary = min(members, key=_preference)
        result.update({m.id: primary.id for m in members if m.id != primary.id})
    return result


def apply_duplicates(db: Session) -> dict:
    """Recalcula `duplicado_de` para todos los coches. Solo participan los activos; el resto queda sin marcar."""
    cars = db.scalars(select(Car)).all()
    mapping = find_duplicates(c for c in cars if c.aktiv)
    changed = 0
    for car in cars:
        new = mapping.get(car.id)
        if car.duplicado_de != new:
            car.duplicado_de, changed = new, changed + 1
    db.commit()
    return {"duplicados": len(mapping), "cambios": changed}

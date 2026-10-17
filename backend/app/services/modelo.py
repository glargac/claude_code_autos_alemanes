"""Coherencia entre el título de un anuncio y su modelo registrado, y corrección del modelo desde el título.

El campo «Modell» de kleinanzeigen lo elige el vendedor en un desplegable y a veces contradice el título que escribe
él mismo: «B 200 CDI» registrado como «C 200», «A180» como «A 160», «Golf Plus» como «Golf». Con el modelo equivocado
los comparables de España son de otro coche y el margen sale mal sin avisar.

Reglas prudentes, por marca, que solo actúan ante una contradicción CLARA: se ignoran potencias («150 PS»), títulos
más genéricos («A-Klasse» para un «A 160») y títulos que mencionan varias motorizaciones («318d 320d»). El valor
original se conserva (`Car.modell_original`) para poder revisar o revertir la corrección.
"""
import re

_NO_ES_MODELO = r"(?!\s?(?:ps|kw|hp|km|tkm|kg|cm|tsd|mm)\b)"  # «150 PS», «85 kW»: potencia, no modelo
_MERCEDES = re.compile(r"(?<!\w)(cl[aks]?|sl[kc]?|ml|gl[acke]?|[abce])\s?-?\s?(\d{2,3})(?!\w)" + _NO_ES_MODELO, re.I)
_BMW = re.compile(r"(?<!\w)([1-8]\d{2})(?:[a-z]{1,2})?(?!\w)" + _NO_ES_MODELO + r"|(?<!\w)(x[1-7])(?!\w)", re.I)
_AUDI = re.compile(r"(?<!\w)([aq]\d)(?!\w)", re.I)

# Variantes del Golf que son otro modelo (con otro precio) y cómo se llaman en AutoScout24.
GOLF_VARIANTES = {"plus": "Golf Plus", "variant": "Golf Variant", "sportsvan": "Golf Sportsvan",
                  "alltrack": "Golf Alltrack", "cabrio": "Golf Cabriolet"}


def _norm(texto: str | None) -> str:
    return re.sub(r"[\s_-]+", "", (texto or "").lower())


def designaciones(marke: str, texto: str) -> list[tuple[str, str]]:
    """Designaciones de modelo distintas que aparecen en un texto, como (clave normalizada, nombre legible).
    Ej. Mercedes «B 200 CDI» -> [("b200", "B 200")]; BMW «116i» -> [("116", "116")]; Audi «A3» -> [("a3", "A3")]."""
    vistas: dict[str, str] = {}
    if marke == "Mercedes-Benz":
        for m in _MERCEDES.finditer(texto or ""):
            vistas.setdefault(f"{m.group(1)}{m.group(2)}".lower(), f"{m.group(1).upper()} {m.group(2)}")
    elif marke == "BMW":
        for m in _BMW.finditer(texto or ""):
            valor = m.group(1) or m.group(2)
            vistas.setdefault(valor.lower(), valor.upper())
    elif marke == "Audi":
        for m in _AUDI.finditer(texto or ""):
            vistas.setdefault(m.group(1).lower(), m.group(1).upper())
    return list(vistas.items())


def _variantes_golf(titel: str) -> list[str]:
    palabras = set(re.findall(r"[a-zäöüß]+", (titel or "").lower()))
    return [v for v in GOLF_VARIANTES if v in palabras]


def conflicto_modelo(marke: str, modell: str, titel: str) -> str | None:
    """Mensaje si el título contradice claramente el modelo registrado; None si es coherente o no se puede saber."""
    if not _norm(modell) or not titel:
        return None
    en_modelo = {k for k, _ in designaciones(marke, modell)}
    en_titulo = designaciones(marke, titel)
    if en_modelo and en_titulo and not en_modelo & {k for k, _ in en_titulo}:  # ninguna designación del título es la registrada
        return f"El título dice «{en_titulo[0][1]}» pero el modelo registrado es «{modell}»: la comparación con España puede ser de otro modelo."
    if marke == "Volkswagen" and _norm(modell) == "golf":
        extra = _variantes_golf(titel)
        if extra:
            return f"El título menciona «{GOLF_VARIANTES[extra[0]]}» pero el modelo registrado es «Golf»: es otro modelo, con otro precio."
    return None


def corregir_modelo(marke: str, modell: str, titel: str) -> str | None:
    """Modelo que sale del título cuando contradice al registrado y la lectura es inequívoca; None si no hay que
    corregir o es ambiguo (el título menciona varias designaciones o varias variantes: se deja el aviso)."""
    if conflicto_modelo(marke, modell, titel) is None:
        return None
    if marke == "Volkswagen":
        extra = _variantes_golf(titel)
        return GOLF_VARIANTES[extra[0]] if len(extra) == 1 else None
    en_titulo = designaciones(marke, titel)
    return en_titulo[0][1] if len(en_titulo) == 1 else None

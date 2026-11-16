"""Definición de los puntos de control de la revisión técnica en campo.

Es la única fuente de verdad: el total de puntos, el progreso y los códigos de referencia (`EXTERIOR-02`) salen de aquí.
Cada punto lleva SIEMPRE un estado (ok / aviso / incidencia) y, según su `tipo`, un valor extra:
  estado  — solo el estado
  sino    — «si» / «no»
  numero  — número (con `unidad` y `max`)
  opcion  — una de `opciones`
Para añadir o quitar puntos basta con editar esta lista: las revisiones existentes se completan solas
(`inspections.asegurar_items`) y los puntos retirados dejan de contar.
"""

ESTADOS = ("ok", "aviso", "incidencia")

# (clave, nombre, [(etiqueta, tipo, extra)])
_CATEGORIAS = [
    ("documentacion", "Documentación", [
        ("Foto de portada", "sino", {}),
        ("Vídeo 360° realizado", "sino", {}),
        ("Número de llaves", "numero", {"unidad": "llaves", "max": 9}),
        ("Placa del fabricante", "estado", {}),
        ("VIN coincide con la documentación", "estado", {}),
        ("Permiso de circulación (Zulassungsbescheinigung)", "estado", {}),
        ("TÜV / HU vigente", "estado", {}),
        ("Libro de mantenimiento (Scheckheft)", "estado", {}),
        ("Historial de siniestros / kilometraje verificado", "estado", {}),
    ]),
    ("exterior", "Exterior", [
        ("Espesímetro frontal (capó y aletas delanteras)", "numero", {"unidad": "µm", "max": 2000}),
        ("Espesímetro laterales (puertas)", "numero", {"unidad": "µm", "max": 2000}),
        ("Espesímetro trasera (portón y aletas traseras)", "numero", {"unidad": "µm", "max": 2000}),
        ("Espesímetro techo", "numero", {"unidad": "µm", "max": 2000}),
        ("Tornillería del capó", "opcion", {"opciones": ["Originales", "Tocados"]}),
        ("Tornillería de las puertas", "opcion", {"opciones": ["Originales", "Tocados"]}),
        ("Tornillería de las aletas", "opcion", {"opciones": ["Originales", "Tocados"]}),
        ("Originalidad de las lunas", "opcion", {"opciones": ["Originales", "Sustituidas"]}),
        ("Luna delantera", "estado", {}),
        ("Tapa de combustible", "estado", {}),
        ("Bola de remolque", "sino", {}),
        ("Pintura y carrocería (golpes, rayones)", "estado", {}),
        ("Alineación de huecos y juntas", "estado", {}),
        ("Faros y pilotos", "estado", {}),
        ("Llantas", "estado", {}),
        ("Espejos retrovisores", "estado", {}),
    ]),
    ("interior", "Interior", [
        ("Cuadro de instrumentos", "estado", {}),
        ("Testigos encendidos con el contacto", "estado", {}),
        ("Desgaste de volante, pomo y pedales vs. kilometraje", "estado", {}),
        ("Asientos y tapicería", "estado", {}),
        ("Techo interior", "estado", {}),
        ("Moquetas y señales de humedad", "estado", {}),
        ("Bandeja de maletero", "estado", {}),
        ("Rueda de repuesto / kit y herramientas", "estado", {}),
        ("Aire acondicionado / climatizador", "estado", {}),
        ("Elevalunas y cierre centralizado", "estado", {}),
        ("Multimedia y electrónica", "estado", {}),
    ]),
    ("motor", "Motor en frío", [
        ("Arranque en frío", "estado", {}),
        ("Ruidos al ralentí", "estado", {}),
        ("Humo de escape", "estado", {}),
        ("Nivel y aspecto del aceite", "estado", {}),
        ("Refrigerante", "estado", {}),
        ("Fugas visibles en el vano motor", "estado", {}),
        ("Correas / cadena (ruidos)", "estado", {}),
        ("Batería", "estado", {}),
        ("Líquido de frenos", "estado", {}),
        ("Manipulaciones o cableado sospechoso", "estado", {}),
        ("Lectura de averías (OBD)", "estado", {}),
    ]),
    ("bajos", "Bajos y ruedas", [
        ("Profundidad de neumáticos", "numero", {"unidad": "mm", "max": 12}),
        ("Desgaste uniforme de neumáticos", "estado", {}),
        ("Discos y pastillas", "estado", {}),
        ("Amortiguadores", "estado", {}),
        ("Escape", "estado", {}),
        ("Fugas en los bajos", "estado", {}),
        ("Óxido y corrosión de bajos", "estado", {}),
    ]),
    ("conduccion", "Prueba de conducción", [
        ("Cambio de marchas", "estado", {}),
        ("Embrague (si es manual)", "estado", {}),
        ("Dirección", "estado", {}),
        ("Frenada", "estado", {}),
        ("Suspensión (ruidos y rebotes)", "estado", {}),
        ("Potencia y respuesta", "estado", {}),
        ("Ruidos y vibraciones en marcha", "estado", {}),
    ]),
]


def _construir() -> list[dict]:
    puntos = []
    for clave, nombre, items in _CATEGORIAS:
        for n, (etiqueta, tipo, extra) in enumerate(items, 1):
            puntos.append({"codigo": f"{clave.upper()}-{n:02d}", "categoria": clave, "categoria_nombre": nombre,
                           "etiqueta": etiqueta, "tipo": tipo, **extra})
    return puntos


PUNTOS: list[dict] = _construir()
POR_CODIGO: dict[str, dict] = {p["codigo"]: p for p in PUNTOS}
CATEGORIAS: list[dict] = [{"clave": c, "nombre": n, "total": len(i)} for c, n, i in _CATEGORIAS]


def validar_valor(punto: dict, valor):
    """Normaliza el valor extra de un punto o lanza ValueError con un mensaje legible. None = sin valor."""
    if valor is None or valor == "":
        return None
    tipo = punto["tipo"]
    if tipo == "estado":
        raise ValueError(f"«{punto['etiqueta']}» no lleva valor, solo estado")
    if tipo == "sino":
        if valor not in ("si", "no"):
            raise ValueError("El valor debe ser «si» o «no»")
        return valor
    if tipo == "opcion":
        if valor not in punto["opciones"]:
            raise ValueError(f"El valor debe ser uno de: {', '.join(punto['opciones'])}")
        return valor
    if tipo == "numero":
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not 0 <= valor <= punto["max"]:
            raise ValueError(f"El valor debe ser un número entre 0 y {punto['max']} {punto['unidad']}")
        return valor
    raise ValueError("Tipo de punto desconocido")

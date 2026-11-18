"""Genera los iconos de la PWA (frontend/public/*.png). Solo hace falta volver a ejecutarlo si cambia el diseño:
    backend/.venv/bin/python scripts/generar-iconos.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

SALIDA = Path(__file__).resolve().parents[1] / "frontend" / "public"
FONDO, CUERPO, CRISTAL, RUEDA, ACENTO = "#0b132b", "#e2e8f0", "#2563eb", "#020617", "#38bdf8"
SS = 4  # se dibuja al cuádruple y se reduce: bordes suaves


def coche(lado: int, escala: float) -> Image.Image:
    """Silueta de un coche centrada sobre fondo azul marino. `escala` deja margen (el icono «maskable» se recorta)."""
    n = lado * SS
    img = Image.new("RGB", (n, n), FONDO)
    d = ImageDraw.Draw(img)
    u = n * escala / 100  # 100 unidades de ancho para el coche
    ox, oy = (n - 100 * u) / 2, n / 2 - 24 * u

    def P(x, y):
        return ox + x * u, oy + y * u

    d.rounded_rectangle([*P(0, 26), *P(100, 62)], radius=9 * u, fill=CUERPO)  # carrocería
    d.polygon([P(20, 28), P(32, 4), P(70, 4), P(86, 28)], fill=CUERPO)  # cabina
    d.polygon([P(27, 26), P(36, 10), P(48, 10), P(48, 26)], fill=CRISTAL)  # ventanas
    d.polygon([P(53, 26), P(53, 10), P(67, 10), P(79, 26)], fill=CRISTAL)
    d.rectangle([*P(0, 52), *P(100, 56)], fill=ACENTO)  # franja
    for cx in (24, 76):
        d.ellipse([*P(cx - 13, 48), *P(cx + 13, 74)], fill=RUEDA)
        d.ellipse([*P(cx - 6, 55), *P(cx + 6, 67)], fill=CUERPO)
    return img.resize((lado, lado), Image.LANCZOS)


for nombre, lado, escala in [("icon-192.png", 192, 0.72), ("icon-512.png", 512, 0.72), ("icon-maskable-512.png", 512, 0.54), ("apple-touch-icon.png", 180, 0.66)]:
    coche(lado, escala).save(SALIDA / nombre, optimize=True)
    print("generado", nombre)

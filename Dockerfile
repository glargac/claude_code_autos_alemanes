# Imagen única: compila la interfaz y la sirve junto con el backend (FastAPI + Playwright/Chromium).
# Construir y arrancar: docker compose up -d --build   (ver deploy/README.md)

# ---- 1) interfaz
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2) backend
FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app/backend

COPY backend/requirements.txt ./
# tzdata: la sync programada y los nombres de las copias usan la hora de TZ (ver docker-compose.yml)
# libatomic1: el driver de Node de Playwright no arranca sin ella (error 127) en la imagen slim
RUN pip install --no-cache-dir -r requirements.txt \
 && apt-get update && apt-get install -y --no-install-recommends tzdata libatomic1 \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

COPY backend/ ./
# main.py busca la interfaz en <raíz>/frontend/dist
COPY --from=web /web/dist /app/frontend/dist

# Sin root: la base y las fotos viven en /app/backend/data (volumen)
RUN useradd --create-home --uid 1000 app && mkdir -p data && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# --proxy-headers: detrás de Caddy, la IP y el esquema reales vienen de sus cabeceras (el puerto 8000 no se publica)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

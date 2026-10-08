# Autos Alemanes · Costa del Sol

App de escritorio local para buscar, puntuar y seguir vehículos alemanes (mobile.de y kleinanzeigen.de) para reventa en la Costa del Sol.

## Estructura

```
backend/    FastAPI + SQLAlchemy (SQLite en backend/data/autos.db)
  app/scrapers/   mobile_de.py, kleinanzeigen.py (Playwright + BeautifulSoup) — stubs
  app/services/   scoring.py (determinista), llm.py (rentabilidad), sync.py (scraping→dedupe→score→vigencia)
  app/routers/    /api/cars, /api/settings/{search|weights}, /api/sync
frontend/   React + Vite + TailwindCSS 4
```

## Puesta en marcha

Requisitos: Python 3.11+ y Node 20+ (`brew install node`).

**Backend**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env        # añade ANTHROPIC_API_KEY para el análisis de rentabilidad
uvicorn app.main:app --reload --port 8000
```
Docs interactivas: http://localhost:8000/docs

**Frontend** (otra terminal)
```bash
cd frontend
npm install
npm run dev
```
Abre http://localhost:5173 (el proxy envía `/api` al backend).

## Estado

Hecho:
- Scraper de **kleinanzeigen.de** (Playwright + BeautifulSoup): filtros por URL, resolución de Ort/PLZ, detalle del anuncio (Getriebe, Kraftstoffart, TÜV, Klimaanlage), detección de anuncios vendidos.
- Modelo de datos con dedupe (fuente + id), estado activo/inactivo y CRM (Neu → Kontaktiert → Termin vereinbart → Kaufoption / Abgelehnt, con cita y notas).
- Scoring determinista (km, Klimaanlage, TÜV, cabrio/estación) + análisis de rentabilidad por LLM (opcional, requiere `ANTHROPIC_API_KEY`). Pesos y umbrales configurables.
- Sincronización en segundo plano con barra de progreso, sync diaria programada y sync al abrir si los datos están desactualizados (configurable en Ajustes).
- Interfaz: dashboard con filtros, panel de seguimiento y pantalla de ajustes.

Pendiente: scraper de mobile.de, empaquetado de escritorio (Tauri/Electron), guardado incremental por marca durante la sync.

## Notas

- Los datos viven en `backend/data/autos.db` (no se versiona). La clave del LLM va en `backend/.env` (no se versiona).
- Raspar sitios web puede ir contra sus condiciones de uso: el scraper limita el ritmo (pausas de 1,5–3 s) y el número de páginas por marca. Úsalo bajo tu responsabilidad.

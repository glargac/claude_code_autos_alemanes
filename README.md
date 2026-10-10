# Autos Alemanes · Costa del Sol

App de escritorio local para buscar, puntuar y seguir vehículos alemanes (kleinanzeigen.de y AutoScout24) para reventa en la Costa del Sol.

## Estructura

```
backend/    FastAPI + SQLAlchemy (SQLite en backend/data/autos.db)
  app/scrapers/   kleinanzeigen.py, autoscout24.py (Playwright + BeautifulSoup)
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

## Uso diario (macOS)

Con la interfaz compilada (`cd frontend && npm run build`), el backend la sirve en **http://localhost:8000** (solo accesible desde tu Mac). No hace falta Vite ni dos terminales.

```bash
scripts/instalar-agente.sh      # una vez: el backend arranca al iniciar sesión y se reinicia si se cae
scripts/abrir.command           # doble clic: abre la app (arranca el backend si hace falta)
scripts/desinstalar-agente.sh   # quita el agente (no toca la base de datos)
```

Registro del backend: `~/Library/Logs/autos-alemanes.log`. La sync diaria solo se ejecuta si el Mac está despierto a esa hora; si no, la sync al abrir cubre el hueco. Tras cambiar el código hay que reiniciarlo: `launchctl kickstart -k gui/$(id -u)/com.autos-alemanes.costa-del-sol`.

Para desarrollar con recarga en caliente, usa los dos comandos de arriba (backend en :8000 y Vite en :5173) con el agente desinstalado.

## Estado

Hecho:
- Scrapers de **kleinanzeigen.de** y **AutoScout24** (Playwright): filtros por URL, resolución de Ort/PLZ, detalle del anuncio (Getriebe, Kraftstoffart, TÜV, Klimaanlage), detección de anuncios vendidos. Cada fuente se guarda por separado y un fallo en una no afecta a la otra.
- Modelo de datos con dedupe (fuente + id), estado activo/inactivo y CRM (Neu → Kontaktiert → Termin vereinbart → Kaufoption / Abgelehnt, con cita y notas).
- Scoring determinista (km, Klimaanlage, TÜV, cabrio/estación) + análisis de rentabilidad por LLM (opcional, requiere `ANTHROPIC_API_KEY`). Pesos y umbrales configurables.
- Sincronización en segundo plano con barra de progreso, sync diaria programada y sync al abrir si los datos están desactualizados (configurable en Ajustes).
- Interfaz: dashboard con filtros, panel de seguimiento y pantalla de ajustes.

Pendiente: empaquetado de escritorio (Tauri/Electron). mobile.de no está soportado: bloquea el acceso automatizado.

## Notas

- Los datos viven en `backend/data/autos.db` (no se versiona). La clave del LLM va en `backend/.env` (no se versiona).
- Raspar sitios web puede ir contra sus condiciones de uso: el scraper limita el ritmo (pausas de 1,5–3 s) y el número de páginas por marca. Úsalo bajo tu responsabilidad.

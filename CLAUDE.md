# Autos Alemanes · Costa del Sol

App local para buscar, puntuar y seguir coches alemanes (Mercedes-Benz, BMW, Audi, Volkswagen, Porsche) en Alemania y revenderlos en la Costa del Sol. Backend FastAPI + SQLAlchemy (SQLite), frontend React + Vite + Tailwind 4. UI y textos en español; términos de búsqueda en alemán (Marke, Modell, Erstzulassung, Kilometer, Preis, Ort oder PLZ, Kraftstoffart, Getriebe).

## Arranque

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev          # http://localhost:5173, el proxy envía /api al backend
```

No pegues comentarios `#` al final de un comando en zsh interactivo: se pasan como argumento (Vite lo tomó como directorio raíz).

## Estructura

- `backend/app/scrapers/` — un scraper por fuente (`base.py` define `Scraper`, `ScrapedCar`). Solo `kleinanzeigen.py` está implementado; `mobile_de.py` es un esqueleto.
- `backend/app/services/` — `sync.py` (scraping → upsert → scoring → vigencia, y estado de la sync en segundo plano), `scoring.py` (determinista), `llm.py` (rentabilidad, opcional), `settings_store.py`.
- `backend/app/routers/` — `/api/cars`, `/api/settings/{search|weights|app}`, `/api/sync`, `/api/sync/status`, `/api/sync/auto`.
- `frontend/src/` — `App.jsx` (dashboard, filtros, barra de sync), `CarCard.jsx` (tarjeta + seguimiento CRM), `Settings.jsx`.

## Cosas no obvias

**kleinanzeigen.de** (verificado contra el sitio real, puede cambiar):
- El filtro de ciudad solo se aplica con el id de ubicación `l<ID>` en la URL; sin él busca en toda Alemania. El id sale de `/s-ort-empfehlungen.json?query=<Ort o PLZ>` (Stuttgart = 9280).
- Los rangos usan `%2C`: `autos.ez_i:2010%2C2020`, `autos.km_i:50000%2C170000`. Con `:` el filtro se descarta en silencio.
- Marca: `autos.marke_s:<slug>` (`mercedes_benz`, `bmw`, `audi`, `volkswagen`, `porsche`). Con `k0` en la ruta, `preis:` se interpreta como texto de búsqueda; solo se usa `k0` si hay Modell.
- La lista no trae Getriebe, combustible, TÜV ni Klimaanlage: salen del bloque JSON de la página de detalle, que solo se pide para anuncios nuevos.
- Un anuncio retirado devuelve HTTP 200 pero redirige a la lista: se detecta porque la URL final ya no contiene `/s-anzeige/`.
- Ritmo: pausas de 1,5–3 s y máximo 4 páginas por marca. Una sync completa tarda 30–40 min la primera vez.

**Sync y scoring:**
- `POST /api/sync` responde 202 y corre en segundo plano; el estado vive en memoria (`sync_state`) y la hora de la última sync en la tabla `settings` (`sync_meta`). Todo se guarda al final: si falla a mitad, no queda nada.
- Al guardar ajustes de búsqueda o pesos se recalculan todos los scores sin llamar al LLM (`rescore_all`), reutilizando la nota LLM guardada.
- El LLM se consulta una sola vez por coche (solo si no tiene análisis guardado) y en un hilo aparte, para no bloquear el backend. Si la llamada falla, el coche queda sin análisis y se reintenta en la siguiente sync; el fallo no aborta la sync.
- Los pesos se normalizan. Sin `ANTHROPIC_API_KEY` no hay nota LLM y su peso se reparte entre los componentes deterministas.
- `ScrapedCar` usa `None` para "sin datos": el upsert ignora `None` y `""` para no pisar datos ya enriquecidos.

## Pruebas y datos

No hay suite de tests: se verifica con scripts desechables y navegador headless (Playwright, ya instalado en el venv). Prueba contra una base temporal (`DATABASE_URL=sqlite:////tmp/x.db`) y con un scraper falso, no contra `backend/data/autos.db` ni lanzando una sync real de 30 min.

## Seguridad (el repo es público)

No versionar: `backend/.env` (clave del LLM), `backend/data/autos.db` (datos y notas personales), `.venv`, `node_modules`, `dist`. Están en `.gitignore`. Antes de cada push, comprobar que no hay claves ni rutas personales.

## Pendiente

Scraper de mobile.de (anti-bot), empaquetado de escritorio (Tauri/Electron), probar el análisis LLM con una clave real, guardado incremental por marca durante la sync, decidir si se sube el tope de 4 páginas.

# Autos Alemanes · Costa del Sol

App local para buscar, puntuar y seguir coches alemanes (Mercedes-Benz, BMW, Audi, Volkswagen, Porsche) en Alemania y revenderlos en la Costa del Sol. Backend FastAPI + SQLAlchemy (SQLite), frontend React + Vite + Tailwind 4. UI y textos en español; términos de búsqueda en alemán (Marke, Modell, Erstzulassung, Kilometer, Preis, Ort oder PLZ, Kraftstoffart, Getriebe).

## Arranque

**Uso diario:** `scripts/instalar-agente.sh` instala un agente de launchd (`com.autos-alemanes.costa-del-sol`) que mantiene el backend en `127.0.0.1:8000`, y este sirve también la interfaz compilada (`frontend/dist`, hay que `npm run build` tras cambiar el frontend). `scripts/abrir.command` abre la app. Registro: `~/Library/Logs/autos-alemanes.log`. **Tras cambiar código del backend hay que reiniciarlo**: `launchctl kickstart -k gui/$(id -u)/com.autos-alemanes.costa-del-sol`. Si el agente está instalado, el puerto 8000 está ocupado: para desarrollar con otro backend, `scripts/desinstalar-agente.sh` primero. Los scripts no llevan rutas personales (el repo es público): las calculan desde su ubicación.

**Desarrollo:**

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev          # http://localhost:5173, el proxy envía /api al backend
```

No pegues comentarios `#` al final de un comando en zsh interactivo: se pasan como argumento (Vite lo tomó como directorio raíz).

## Estructura

- `backend/app/scrapers/` — un scraper por fuente (`base.py` define `Scraper`, `ScrapedCar`). Implementados: `kleinanzeigen.py` y `autoscout24.py`.
- `backend/app/services/` — `dedupe.py` (anuncios duplicados), `sync.py` (scraping → upsert → scoring → vigencia, y estado de la sync en segundo plano), `scoring.py` (determinista), `llm.py` (rentabilidad, opcional), `settings_store.py`.
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

**autoscout24.de** (verificado contra el sitio real, puede cambiar):
- Lista y detalle traen un JSON `__NEXT_DATA__` con todos los datos: no se parsea HTML.
- Filtros por URL: `/lst/<marca>[/<modelo>]?fregfrom&fregto&pricefrom&priceto&kmfrom&kmto&zip&zipr&fuel=B,D&gear=A|M`. Se usa `sort=age&desc=1` (más recientes primero) y siempre `fuel`, que además excluye eléctricos.
- `zip` acepta PLZ o ciudad, pero si no reconoce el lugar lo sustituye en silencio por otro (Marbella → Malsburg-Marzell): `location_ok` lo detecta y la sync de esa fuente falla con un mensaje claro.
- TÜV (`nextVehicleSafetyInspection`), Klimaanlage (lista de equipamiento) y fecha de publicación solo están en el detalle, que se pide únicamente para anuncios nuevos.
- **Ojo con el reposo del Mac:** si el equipo se suspende (incluido el "Maintenance Sleep" nocturno) mientras corre una sync o una prueba, el navegador se congela y las páginas dan timeout aunque el sitio funcione (un `ping` con latencias de minutos delata el caso). Para syncs largas, mantenerlo despierto: `caffeinate -i -t 7200`. Una falsa alarma de "bloqueo anti-bot" por esto ya costó tiempo de diagnóstico.
- Un anuncio retirado redirige a `/lst/<marca>` (la URL final ya no contiene `/angebote/`).

**mobile.de: bloqueado.** Devuelve 403 "Zugriff verweigert" (anti-bot) a un navegador automatizado, con y sin User-Agent propio. No se intenta evadir. No volver a probarlo sin una vía legítima (p. ej. API de socio).

**Robustez de los scrapers** (`scrapers/base.py`): `retry` reintenta una vez ante timeouts de red/navegación; un HTTP de error (403...) se trata como bloqueo y aborta la fuente. Si falla la página de detalle de un coche, ese coche se descarta (no se guarda a medias: nunca se volvería a pedir su detalle) y se reintenta en la próxima sync; si fallan más de la mitad (mínimo 10), la fuente aborta. Al comprobar vigencia, un fallo de red deja el coche como vigente. Si falla una página de lista, la marca se corta ahí (se conserva lo leído) y se anota un aviso en `scraper.warnings`, que `run_sync` añade a `fehler` como "(aviso)"; solo se aborta la fuente si no carga ninguna marca, si hay un HTTP de error (bloqueo) o si el lugar no se reconoce. Tiempo máximo de carga por página: 60 s.

**Duplicados** (`services/dedupe.py`): el mismo coche puede estar en los dos portales o repetido en uno. Las filas **no se borran** (la sync identifica anuncios por fuente + id externo y los recrearía): una es la principal y las demás tienen `duplicado_de` = id de la principal. La lista solo muestra principales, con `otros_enlaces`. Reglas conservadoras (un falso positivo esconde un coche distinto): misma marca, modelo, año, combustible y Getriebe, y (1) km idénticos + precio ±3 % + mismo sitio o km no redondo; (2) km ±0,3 % + precio ±2 % + mismo sitio o título parecido; (3) km ±0,1 % no redondos + precio ±2 %. "Redondo" = múltiplo de 100 (los vendedores redondean). Principal: la que ya tiene seguimiento (estado/notas/cita), luego la más completa, luego la más antigua. Se recalcula al arrancar el backend y tras guardar cada fuente; el índice de precios cuenta cada coche una sola vez. En la base real: 79 duplicados (59 entre portales, 20 en el mismo portal) de 963 activos.

**Migraciones:** `database.ensure_columns()` añade al arrancar las columnas nuevas a una base existente (`create_all` no altera tablas). Al añadir una columna al modelo, registrarla en `_ADDED_COLUMNS`.

**Sync y scoring:**
- Cada fuente se procesa y se guarda por separado: si una falla (bloqueo, cambio de web), las demás siguen y el error aparece en `fehler` del resultado y en la interfaz.
- Se descartan en `run_sync` los coches cuyo combustible no esté en `kraftstoffart` (p. ej. eléctricos), sea cual sea la fuente.
- `POST /api/sync` responde 202 y corre en segundo plano; el estado vive en memoria (`sync_state`) y la hora de la última sync en la tabla `settings` (`sync_meta`). Se guarda al terminar cada fuente.
- Al guardar ajustes de búsqueda o pesos se recalculan todos los scores sin llamar al LLM (`rescore_all`), reutilizando la nota LLM guardada.
- El LLM se consulta una sola vez por coche (solo si no tiene análisis guardado) y en un hilo aparte, para no bloquear el backend. Si la llamada falla, el coche queda sin análisis y se reintenta en la siguiente sync; el fallo no aborta la sync.
- El componente `precio` compara con el precio esperado del mismo modelo (`scoring.MarketIndex`): modelo hedónico en log-precio con media del modelo ± pendientes por año (≈ +6 %/año) y por km (≈ −0,3 % por 1.000 km), aprendidas de toda la base (regresión intra-grupo; límites y valores por defecto si hay pocos datos). Mínimo 5 coches del mismo modelo, sin contar el propio. 10 puntos si cuesta un 30 % menos que lo esperado, 5 si igual, 1 si un 30 % más. Sin referencia o con modelo genérico ("Andere"), 5 (neutro). Se recalcula en `rescore_all` tras cada fuente. En la base real predice el precio con ≈23 % de error típico (la mediana por año daba ≈26 %). Limitación: el filtro de precio (≤10.000 €) sesga la referencia hacia los ejemplares baratos.
- Los pesos se normalizan. Sin `ANTHROPIC_API_KEY` no hay nota LLM y su peso se reparte entre los componentes deterministas.
- `ScrapedCar` usa `None` para "sin datos": el upsert ignora `None` y `""` para no pisar datos ya enriquecidos.

## Pruebas y datos

No hay suite de tests: se verifica con scripts desechables y navegador headless (Playwright, ya instalado en el venv). Prueba contra una base temporal (`DATABASE_URL=sqlite:////tmp/x.db`) y con un scraper falso, no contra `backend/data/autos.db` ni lanzando una sync real de 30 min.

## Seguridad (el repo es público)

No versionar: `backend/.env` (clave del LLM), `backend/data/autos.db` (datos y notas personales), `.venv`, `node_modules`, `dist`. Están en `.gitignore`. Antes de cada push, comprobar que no hay claves ni rutas personales.

## Pendiente

Empaquetado de escritorio (Tauri/Electron), probar el análisis LLM con una clave real, decidir si se sube el tope de 4 páginas.

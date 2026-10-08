import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import CarCard, { STATUSES } from "./CarCard.jsx";
import Settings from "./Settings.jsx";

const MARKEN = ["Mercedes-Benz", "BMW", "Audi", "Volkswagen", "Porsche"];
const EMPTY_FILTERS = { marke: "", modell: "", getriebe: "", status: "", publicado_dias: "", inaktiv_anzeigen: false };
const sel = "rounded-lg bg-slate-900 px-3 py-1.5 text-sm ring-1 ring-slate-700";

function Filters({ filters, setFilters, count }) {
  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));
  const dirty = JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select className={sel} value={filters.marke} onChange={(e) => set("marke", e.target.value)}>
        <option value="">Marke: todas</option>
        {MARKEN.map((m) => <option key={m}>{m}</option>)}
      </select>
      <input className={`${sel} w-32`} placeholder="Modell" value={filters.modell} onChange={(e) => set("modell", e.target.value)} />
      <select className={sel} value={filters.getriebe} onChange={(e) => set("getriebe", e.target.value)}>
        <option value="">Getriebe: todos</option>
        <option>Automatik</option>
        <option>Manuell</option>
      </select>
      <select className={sel} value={filters.publicado_dias} onChange={(e) => set("publicado_dias", e.target.value)}>
        <option value="">Publicación: cualquiera</option>
        <option value="1">Últimas 24 h</option>
        <option value="7">Última semana</option>
        <option value="14">Últimas 2 semanas</option>
        <option value="30">Último mes</option>
      </select>
      <select className={sel} value={filters.status} onChange={(e) => set("status", e.target.value)}>
        <option value="">Estado: todos</option>
        {STATUSES.map((s) => <option key={s}>{s}</option>)}
      </select>
      <label className="flex items-center gap-2 text-sm text-slate-400">
        <input type="checkbox" checked={filters.inaktiv_anzeigen} onChange={(e) => set("inaktiv_anzeigen", e.target.checked)} />
        Incluir vendidos
      </label>
      {dirty && (
        <button onClick={() => setFilters(EMPTY_FILTERS)} className="text-sm text-sky-400">
          Limpiar
        </button>
      )}
      <span className="ml-auto text-sm text-slate-500">{count} coches</span>
    </div>
  );
}

const PHASE_LABELS = { listas: "Buscando anuncios", detalles: "Leyendo detalles", verificar: "Comprobando vendidos" };

function ago(iso, now) {
  if (!iso) return "nunca";
  const min = Math.max(0, Math.round((now - new Date(iso)) / 60000));
  if (min < 1) return "hace un momento";
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  return h < 48 ? `hace ${h} h` : `hace ${Math.floor(h / 24)} días`;
}

function SyncBanner({ sync }) {
  if (sync.running) {
    const p = sync.progress;
    const label = p ? `${PHASE_LABELS[p.phase]}${p.total ? ` · ${p.done} de ${p.total}` : ""}` : "Iniciando…";
    return (
      <div className="space-y-2 rounded-lg bg-sky-950 px-4 py-3 text-sm text-sky-200">
        <div className="flex justify-between">
          <span>Sincronizando — {label}</span>
          <span className="tabular-nums">{p ? `${p.percent}%` : ""}</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-sky-900">
          <div className="h-full rounded-full bg-sky-400 transition-all duration-700" style={{ width: `${p?.percent ?? 2}%` }} />
        </div>
        <p className="text-xs text-sky-400">Puedes seguir usando la app mientras tanto.</p>
      </div>
    );
  }
  if (sync.error) return <p className="rounded-lg bg-red-950 px-4 py-2 text-sm text-red-300">Error en la sincronización: {sync.error}</p>;
  if (sync.result)
    return (
      <p className="rounded-lg bg-green-950 px-4 py-2 text-sm text-green-300">
        Sincronización terminada: {sync.result.nuevos} nuevos, {sync.result.actualizados} actualizados, {sync.result.inactivos} inactivos.
      </p>
    );
  return null;
}

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [cars, setCars] = useState([]);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [sync, setSync] = useState({ running: false });
  const [now, setNow] = useState(() => Date.now());
  const wasRunning = useRef(false);

  const load = useCallback(() => api.cars(filters).then(setCars).catch(console.error), [filters]);

  // Recarga al cambiar filtros (con un pequeño retardo para no consultar en cada tecla).
  useEffect(() => {
    const id = setTimeout(load, 250);
    return () => clearTimeout(id);
  }, [load]);

  // Al abrir: el backend lanza la sync si los datos están desactualizados (según Ajustes) y devuelve el estado.
  // Después se consulta cada 3 s mientras corre.
  useEffect(() => {
    api.syncAuto().then(setSync).catch(console.error);
    const id = setInterval(() => setNow(Date.now()), 60000); // refresca el "hace X"
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!sync.running) {
      if (wasRunning.current) load(); // acaba de terminar: refrescar lista
      wasRunning.current = false;
      return;
    }
    wasRunning.current = true;
    const id = setInterval(() => api.syncStatus().then(setSync).catch(console.error), 3000);
    return () => clearInterval(id);
  }, [sync.running, load]);

  const runSync = async () => {
    setSync(await api.sync());
    setTab("dashboard");
  };

  const tabBtn = (id, label) => (
    <button
      onClick={() => setTab(id)}
      className={`rounded-lg px-3 py-1.5 text-sm ${tab === id ? "bg-slate-800 text-white" : "text-slate-400 hover:text-white"}`}
    >
      {label}
    </button>
  );

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Autos Alemanes · Costa del Sol</h1>
          <p className="text-xs text-slate-500">Última sync: {ago(sync.last_sync_at, now)}</p>
        </div>
        <nav className="flex items-center gap-2">
          {tabBtn("dashboard", "Dashboard")}
          {tabBtn("settings", "Ajustes")}
          <button
            onClick={() => runSync().catch((e) => alert(e.message))}
            disabled={sync.running}
            className="ml-2 rounded-lg bg-sky-600 px-4 py-2 text-sm disabled:opacity-50"
          >
            {sync.running ? "Sincronizando…" : "Sincronizar"}
          </button>
        </nav>
      </header>

      <SyncBanner sync={sync} />

      {tab === "dashboard" ? (
        <>
          <Filters filters={filters} setFilters={setFilters} count={cars.length} />
          {cars.length === 0 && <p className="text-slate-400">Sin resultados. Ajusta los filtros o pulsa Sincronizar.</p>}
          {cars.map((c) => (
            <CarCard key={c.id} car={c} onChange={(upd) => setCars((list) => list.map((x) => (x.id === upd.id ? upd : x)))} />
          ))}
        </>
      ) : (
        <Settings onSaved={load} onRun={runSync} syncRunning={sync.running} />
      )}
    </main>
  );
}

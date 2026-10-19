import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import CarCard, { SOURCE_LABEL, STATUSES } from "./CarCard.jsx";
import Settings from "./Settings.jsx";

const MARKEN = ["Mercedes-Benz", "BMW", "Audi", "Volkswagen", "Porsche"];
const EMPTY_FILTERS = { fuente: "", marke: "", modell: "", getriebe: "", status: "", publicado_dias: "", inaktiv_anzeigen: false, mostrar_ocultos: false };
const sel = "rounded-lg bg-slate-900 px-3 py-1.5 text-sm ring-1 ring-slate-700";

function Filters({ filters, setFilters, count }) {
  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));
  const dirty = JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select className={sel} value={filters.fuente} onChange={(e) => set("fuente", e.target.value)}>
        <option value="">Fuente: todas</option>
        {Object.entries(SOURCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
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
      <label className="flex items-center gap-2 text-sm text-slate-400">
        <input type="checkbox" checked={filters.mostrar_ocultos} onChange={(e) => set("mostrar_ocultos", e.target.checked)} />
        Mostrar ocultos
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

const SOURCE_NAMES = { kleinanzeigen: "kleinanzeigen.de", autoscout24: "AutoScout24" };
const PHASE_LABELS = { listas: "Buscando anuncios", detalles: "Leyendo detalles", verificar: "Comprobando vendidos" };

function ago(iso, now) {
  if (!iso) return "nunca";
  const min = Math.max(0, Math.round((now - new Date(iso)) / 60000));
  if (min < 1) return "hace un momento";
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  return h < 48 ? `hace ${h} h` : `hace ${Math.floor(h / 24)} días`;
}

function LastSync({ sync, now }) {
  const sources = Object.entries(sync.fuentes ?? {}); // un backend antiguo no lo envía: se usa la hora global
  if (sources.length === 0) return <p className="text-xs text-slate-500">Última sync: {ago(sync.last_sync_at, now)}</p>;
  return (
    <p className="text-xs text-slate-500">
      Última sync:{" "}
      {sources.map(([name, e], i) => (
        <span key={name}>
          {i > 0 && " · "}
          {SOURCE_NAMES[name] ?? name} {ago(e.last_sync_at, now)}
          {e.error && (
            <span className="text-amber-400" title={`El último intento falló: ${e.error}`}>
              {" "}⚠
            </span>
          )}
        </span>
      ))}
    </p>
  );
}

function SyncBanner({ sync }) {
  if (sync.running) {
    const p = sync.progress;
    const label = p
      ? `${SOURCE_NAMES[p.source] ?? ""} · ${PHASE_LABELS[p.phase]}${p.total ? ` · ${p.done} de ${p.total}` : ""}`
      : "Iniciando…";
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
  if (sync.result) {
    const fehler = sync.result.fehler ?? [];
    return (
      <div className="space-y-1">
        <p className="rounded-lg bg-green-950 px-4 py-2 text-sm text-green-300">
          Sincronización terminada: {sync.result.nuevos} nuevos, {sync.result.actualizados} actualizados, {sync.result.inactivos} inactivos.
        </p>
        {fehler.map((f) => (
          <p key={f} className="rounded-lg bg-amber-950 px-4 py-2 text-sm text-amber-300">
            Fuente con problemas: {f}
          </p>
        ))}
      </div>
    );
  }
  return null;
}

const TOP_N = 20;
const SIN_MODELO = /^(andere|sonstige|sonstiges|other)?$/;
const necesitaAnalisis = (c) =>
  !c.oculto && c.preis && c.erstzulassung && !SIN_MODELO.test(c.modell.toLowerCase().replace(/[\s_-]+/g, "")) &&
  !(c.rentabilidad && (c.rentabilidad.estado === "calculando" || (c.rentabilidad.estado === "listo" && !c.rentabilidad.desactualizado)));

function LoteBanner({ lote, fin, onClose }) {
  if (lote.running) {
    const pct = lote.total ? Math.round((lote.hechos / lote.total) * 100) : 0;
    return (
      <div className="space-y-2 rounded-lg bg-violet-950 px-4 py-3 text-sm text-violet-200">
        <div className="flex justify-between">
          <span>Analizando el Top {TOP_N} — {lote.hechos} de {lote.total}</span>
          <span className="tabular-nums">{pct}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-violet-900">
          <div className="h-full rounded-full bg-violet-400 transition-all duration-700" style={{ width: `${Math.max(pct, 2)}%` }} />
        </div>
        <p className="text-xs text-violet-400">Uno detrás de otro, unos 20 s por coche. Puedes seguir usando la app.</p>
      </div>
    );
  }
  if (!fin) return null;
  return (
    <p className="flex items-center justify-between rounded-lg bg-green-950 px-4 py-2 text-sm text-green-300">
      <span>
        Top {TOP_N} analizado: {lote.hechos - lote.errores} informes
        {lote.errores > 0 && `, ${lote.errores} con error (míralos en su ficha)`}
        {lote.omitidos > 0 && ` · ${lote.omitidos} omitidos (ya al día o sin modelo)`}.
      </span>
      <button onClick={onClose} className="ml-3 text-green-400">✕</button>
    </p>
  );
}

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [cars, setCars] = useState([]);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [sync, setSync] = useState({ running: false });
  const [now, setNow] = useState(() => Date.now());
  const wasRunning = useRef(false);
  const [lote, setLote] = useState({ running: false });
  const [loteFin, setLoteFin] = useState(false);
  const wasLote = useRef(false);
  const [deshacer, setDeshacer] = useState(null);

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

  // Análisis del Top N: el backend lo hace en segundo plano; mientras corre se consulta su avance y se refresca la lista.
  useEffect(() => {
    api.topStatus().then(setLote).catch(console.error);
  }, []);

  useEffect(() => {
    if (!lote.running) {
      if (wasLote.current) {
        load();
        setLoteFin(true);
      }
      wasLote.current = false;
      return;
    }
    wasLote.current = true;
    const id = setInterval(() => {
      api.topStatus().then(setLote).catch(console.error);
      load();
    }, 4000);
    return () => clearInterval(id);
  }, [lote.running, load]);

  const pendientes = cars.filter((c) => !c.oculto).slice(0, TOP_N).filter(necesitaAnalisis).length;

  const runTop = async () => {
    if (!confirm(`Analizar la rentabilidad de los ${TOP_N} mejores coches de la lista.\n\n${pendientes} necesitan análisis (el resto ya está al día o no tiene modelo).\nTarda unos ${Math.max(1, Math.round(pendientes / 3))} min y usa la IA (~2.000 tokens por coche, ~${(pendientes * 2).toLocaleString("de-DE")}.000 en total).`)) return;
    try {
      setLoteFin(false);
      setLote(await api.analyzeTop(filters, TOP_N));
      load();
    } catch (e) {
      alert(e.message);
    }
  };

  const onCarChange = (upd) => {
    const prev = cars.find((x) => x.id === upd.id);
    if (upd.oculto && !filters.mostrar_ocultos) {
      setCars((list) => list.filter((x) => x.id !== upd.id));
      if (prev && !prev.oculto) {
        setDeshacer({ id: upd.id, nombre: `${upd.marke} ${upd.modell}` });
        setTimeout(() => setDeshacer((d) => (d?.id === upd.id ? null : d)), 8000);
      }
    } else {
      setCars((list) => list.map((x) => (x.id === upd.id ? upd : x)));
    }
  };

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
          <LastSync sync={sync} now={now} />
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
      <LoteBanner lote={lote} fin={loteFin} onClose={() => setLoteFin(false)} />
      {deshacer && (
        <p className="flex items-center justify-between rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-200">
          <span>{deshacer.nombre} oculto de tu lista.</span>
          <button
            onClick={() => api.updateCar(deshacer.id, { oculto: false }).then(() => { setDeshacer(null); load(); }).catch((e) => alert(e.message))}
            className="ml-3 text-sky-400"
          >
            Deshacer
          </button>
        </p>
      )}

      {tab === "dashboard" ? (
        <>
          <Filters filters={filters} setFilters={setFilters} count={cars.length} />
          <div className="flex items-center gap-3">
            <button
              onClick={runTop}
              disabled={lote.running || pendientes === 0}
              title={`Calcula margen e informe de IA de los ${TOP_N} primeros de la lista que aún no lo tienen al día`}
              className="rounded-lg bg-violet-700 px-4 py-1.5 text-sm hover:bg-violet-600 disabled:opacity-50"
            >
              {lote.running ? "Analizando…" : pendientes === 0 ? `Top ${TOP_N} al día` : `Analizar Top ${TOP_N}`}
            </button>
            {!lote.running && pendientes > 0 && <span className="text-xs text-slate-500">{pendientes} por analizar</span>}
          </div>
          {cars.length === 0 && <p className="text-slate-400">Sin resultados. Ajusta los filtros o pulsa Sincronizar.</p>}
          {cars.map((c) => (
            <CarCard key={c.id} car={c} onChange={onCarChange} />
          ))}
        </>
      ) : (
        <Settings onSaved={load} onRun={runSync} syncRunning={sync.running} />
      )}
    </main>
  );
}

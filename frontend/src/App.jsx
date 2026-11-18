import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import CarCard, { SOURCE_LABEL, STATUSES } from "./CarCard.jsx";
import Settings from "./Settings.jsx";
import Revisiones from "./revisiones/Revisiones.jsx";

const MARKEN = ["Mercedes-Benz", "BMW", "Audi", "Volkswagen", "Porsche"];
const EMPTY_FILTERS = { fuente: "", marke: "", modell: "", getriebe: "", status: "", publicado_dias: "", furgonetas: "", inaktiv_anzeigen: false };
const sel = "w-full rounded-lg bg-slate-900 px-3 py-2.5 text-sm ring-1 ring-slate-700 md:w-auto md:py-1.5";
const PAGINA = 30;  // tarjetas que se pintan de una vez: con miles de coches el móvil se arrastra

function Filters({ filters, setFilters, count }) {
  const [abierto, setAbierto] = useState(false);  // en móvil los filtros se pliegan tras un botón
  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));
  const dirty = JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS);
  const activos = Object.keys(EMPTY_FILTERS).filter((k) => filters[k] !== EMPTY_FILTERS[k]).length;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 md:hidden">
        <button onClick={() => setAbierto(!abierto)} aria-expanded={abierto} className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm ring-1 ring-slate-700">
          ⚙ Filtros{activos > 0 && ` · ${activos}`} {abierto ? "▴" : "▾"}
        </button>
        {dirty && <button onClick={() => setFilters(EMPTY_FILTERS)} className="px-2 py-2.5 text-sm text-sky-400">Limpiar</button>}
        <span className="ml-auto text-sm text-slate-500">{count} coches</span>
      </div>
      <div className={`${abierto ? "grid" : "hidden"} grid-cols-2 gap-2 md:flex md:flex-wrap md:items-center`}>
      <select className={sel} value={filters.fuente} onChange={(e) => set("fuente", e.target.value)}>
        <option value="">Fuente: todas</option>
        {Object.entries(SOURCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <select className={sel} value={filters.marke} onChange={(e) => set("marke", e.target.value)}>
        <option value="">Marke: todas</option>
        {MARKEN.map((m) => <option key={m}>{m}</option>)}
      </select>
      <input className={`${sel} md:!w-32`} placeholder="Modell" value={filters.modell} onChange={(e) => set("modell", e.target.value)} />
      <select className={sel} value={filters.getriebe} onChange={(e) => set("getriebe", e.target.value)}>
        <option value="">Getriebe: todos</option>
        <option>Automatik</option>
        <option>Manuell</option>
      </select>
      <select className={sel} value={filters.furgonetas} onChange={(e) => set("furgonetas", e.target.value)}>
        <option value="">Tipo: coches y furgonetas</option>
        <option value="solo">Solo furgonetas</option>
        <option value="sin">Sin furgonetas</option>
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
      <label className="col-span-2 flex items-center gap-2 py-1 text-sm text-slate-400 md:col-auto">
        <input type="checkbox" checked={filters.inaktiv_anzeigen} onChange={(e) => set("inaktiv_anzeigen", e.target.checked)} />
        Incluir vendidos
      </label>
      {dirty && (
        <button onClick={() => setFilters(EMPTY_FILTERS)} className="hidden text-sm text-sky-400 md:inline">
          Limpiar
        </button>
      )}
      <span className="ml-auto hidden text-sm text-slate-500 md:inline">{count} coches</span>
      </div>
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

const BANNER_VISTO = "syncBannerVisto";  // + «:usuario»: cada usuario del navegador tiene el suyo

// El resultado de la última sync (y sus avisos) se queda en memoria en el backend hasta la siguiente: sin esto se
// mostraba en cada visita. Se enseña una vez (`started_at` identifica la sync), con ✕ para cerrarlo, y no vuelve.
function SyncBanner({ sync, usuario }) {
  const clave = `${BANNER_VISTO}:${usuario}`;
  const [cerrado, setCerrado] = useState(() => localStorage.getItem(clave));
  const terminada = !sync.running && sync.started_at && (sync.result || sync.error);
  useEffect(() => {
    if (terminada) localStorage.setItem(clave, sync.started_at);  // la próxima visita ya no lo muestra
  }, [terminada, sync.started_at, clave]);
  if (terminada && cerrado === sync.started_at) return null;
  const cerrar = () => setCerrado(sync.started_at);
  if (sync.running && sync.en_cola) {
    return (
      <p className="rounded-lg bg-sky-950 px-4 py-3 text-sm text-sky-200">
        Otro usuario está sincronizando ahora. Tu sincronización empezará en cuanto termine (solo corre una a la vez).
      </p>
    );
  }
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
  if (sync.error) {
    return (
      <p className="flex items-center justify-between rounded-lg bg-red-950 px-4 py-2 text-sm text-red-300">
        <span>Error en la sincronización: {sync.error}</span>
        <button onClick={cerrar} aria-label="Cerrar" className="-my-2 ml-3 p-2 text-red-400">✕</button>
      </p>
    );
  }
  if (sync.result) {
    const fehler = sync.result.fehler ?? [];
    return (
      <div className="space-y-1">
        <p className="flex items-center justify-between rounded-lg bg-green-950 px-4 py-2 text-sm text-green-300">
          <span>Sincronización terminada: {sync.result.nuevos} nuevos, {sync.result.actualizados} actualizados, {sync.result.inactivos} inactivos.</span>
          <button onClick={cerrar} aria-label="Cerrar" className="-my-2 ml-3 p-2 text-green-400">✕</button>
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
  c.preis && c.erstzulassung && !SIN_MODELO.test(c.modell.toLowerCase().replace(/[\s_-]+/g, "")) &&
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

const TABS = [["dashboard", "Dashboard", "🚗"], ["favoritos", "Favoritos", "★"], ["revisiones", "Revisiones", "📋"], ["settings", "Ajustes", "⚙️"]];

export default function App({ user, onSalir }) {
  const [tab, setTab] = useState("dashboard");
  const [cars, setCars] = useState([]);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [sync, setSync] = useState({ running: false });
  const [now, setNow] = useState(() => Date.now());
  const wasRunning = useRef(false);
  const [lote, setLote] = useState({ running: false });
  const [loteFin, setLoteFin] = useState(false);
  const wasLote = useRef(false);
  const [limite, setLimite] = useState(PAGINA);  // cuántas tarjetas se pintan
  const [seleccion, setSeleccion] = useState(() => new Set());  // ids marcados con la casilla
  const [porEliminar, setPorEliminar] = useState(null);  // coches pendientes de confirmar en la ventana
  const [eliminando, setEliminando] = useState(false);
  const [revisionAbierta, setRevisionAbierta] = useState(null);  // id de la revisión técnica que se está rellenando
  const [revisiones, setRevisiones] = useState({});  // car_id → {id, estado, progreso} (botón de Favoritos)

  const enFavoritos = tab === "favoritos";
  const load = useCallback(
    () => (enFavoritos ? api.cars({ favoritos: true, inaktiv_anzeigen: true }) : api.cars(filters)).then(setCars).catch(console.error),
    [filters, enFavoritos],
  );

  useEffect(() => {
    if (enFavoritos) {
      api.inspections().then((d) => setRevisiones(Object.fromEntries(d.revisiones.map((r) => [r.car_id, { id: r.id, estado: r.estado, progreso: r.resumen.progreso }])))).catch(console.error);
    }
  }, [enFavoritos]);

  const abrirRevision = async (car, vista = "checklist") => {
    try {
      const r = await api.startInspection(car.id);
      setRevisionAbierta({ id: r.id, vista });
      setCars([]);
      setTab("revisiones");
    } catch (e) {
      alert(e.message);
    }
  };

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

  const pendientes = cars.slice(0, TOP_N).filter(necesitaAnalisis).length;

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
    if (enFavoritos && !upd.favorito) setCars((list) => list.filter((x) => x.id !== upd.id));
    else setCars((list) => list.map((x) => (x.id === upd.id ? upd : x)));
  };

  const marcarFavoritos = async (favorito) => {
    const ids = [...seleccion];
    try {
      await api.favoritos(ids, favorito);
      setCars((list) => (enFavoritos && !favorito ? list.filter((x) => !seleccion.has(x.id)) : list.map((x) => (seleccion.has(x.id) ? { ...x, favorito } : x))));
      setSeleccion(new Set());
    } catch (e) {
      alert(e.message);
    }
  };

  // En Favoritos, primero los que tienen cita (la más próxima arriba) y luego por puntuación.
  const visibles = enFavoritos
    ? [...cars].sort((a, b) => (a.termin_am ? 0 : 1) - (b.termin_am ? 0 : 1) || (a.termin_am ?? "").localeCompare(b.termin_am ?? "") || (b.score ?? 0) - (a.score ?? 0))
    : cars;

  const toggleSel = (id) =>
    setSeleccion((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  const confirmarEliminar = async () => {
    const ids = porEliminar.map((c) => c.id);
    setEliminando(true);
    try {
      await api.eliminar(ids);
      setCars((list) => list.filter((x) => !ids.includes(x.id)));
      setSeleccion((s) => new Set([...s].filter((id) => !ids.includes(id))));
      setPorEliminar(null);
    } catch (e) {
      alert(e.message);
    } finally {
      setEliminando(false);
    }
  };

  const runSync = async () => {
    setSync(await api.sync());
    setTab("dashboard");
  };

  useEffect(() => setLimite(PAGINA), [filters, tab]);  // otra consulta: se vuelve a empezar por arriba

  const enFormulario = tab === "revisiones" && revisionAbierta != null;  // checklist o informe: en móvil, pantalla completa

  const irA = (id) => { setSeleccion(new Set()); setCars([]); setRevisionAbierta(null); setTab(id); window.scrollTo({ top: 0 }); };
  const syncBtn = (clase) => (
    <button onClick={() => runSync().catch((e) => alert(e.message))} disabled={sync.running} className={`rounded-lg bg-sky-600 text-sm disabled:opacity-50 ${clase}`}>
      {sync.running ? "Sincronizando…" : "Sincronizar"}
    </button>
  );

  return (
    <main className="mx-auto max-w-4xl space-y-4 p-4 pb-24 md:p-6 md:pb-6">
      <header className={`items-start justify-between gap-3 md:flex md:items-center ${enFormulario ? "hidden" : "flex"}`}>
        <div className="min-w-0">
          <h1 className="text-lg font-bold md:text-xl">Autos Alemanes · Costa del Sol</h1>
          <LastSync sync={sync} now={now} />
          <p className="text-xs text-slate-500">
            {user.usuario} · <button onClick={onSalir} className="px-1 py-2 text-sky-400 hover:underline md:py-1">Salir</button>
          </p>
        </div>
        {/* Escritorio: pestañas arriba. Móvil: botón de sincronizar aquí y pestañas en la barra inferior. */}
        <nav className="hidden shrink-0 items-center gap-2 md:flex">
          {TABS.map(([id, label, icono]) => (
            <button key={id} onClick={() => irA(id)} className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${tab === id ? "bg-slate-800 text-white" : "text-slate-400 hover:text-white"}`}>
              {id === "favoritos" ? `${icono} ${label}` : label}
            </button>
          ))}
          {syncBtn("ml-2 px-4 py-2")}
        </nav>
        {syncBtn("shrink-0 px-3 py-2.5 md:hidden")}
      </header>

      <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-slate-800 bg-slate-950/95 backdrop-blur md:hidden" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
        {TABS.map(([id, label, icono]) => (
          <button key={id} onClick={() => irA(id)} aria-current={tab === id ? "page" : undefined}
            className={`flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-[11px] ${tab === id ? "text-sky-400" : "text-slate-400"}`}>
            <span className="text-lg leading-none">{icono}</span>
            {label}
          </button>
        ))}
      </nav>

      <div className={`space-y-4 empty:hidden md:block ${enFormulario ? "hidden" : ""}`}>
        <SyncBanner sync={sync} usuario={user.usuario} />
        <LoteBanner lote={lote} fin={loteFin} onClose={() => setLoteFin(false)} />
      </div>
      {porEliminar && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-4 md:items-center" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-xl bg-slate-900 p-5 ring-1 ring-slate-700 md:p-6">
            <h2 className="text-lg font-semibold">¿Está seguro de eliminar {porEliminar.length === 1 ? "este auto" : "estos autos"}?</h2>
            <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto text-sm text-slate-300">
              {porEliminar.map((c) => (
                <li key={c.id}>
                  {c.marke} {c.modell} · {c.erstzulassung} · {c.preis?.toLocaleString("de-DE")} €
                </li>
              ))}
            </ul>
            {porEliminar.some((c) => c.favorito) && (
              <p className="mt-3 text-sm text-amber-400">Incluye {porEliminar.filter((c) => c.favorito).length} favorito(s), con su seguimiento.</p>
            )}
            <p className="mt-3 text-xs text-slate-500">Desaparecerán de la lista y no volverán a aparecer en las próximas actualizaciones.</p>
            <div className="mt-5 flex justify-end gap-3">
              <button onClick={() => setPorEliminar(null)} disabled={eliminando} className="rounded-lg px-4 py-2.5 text-sm text-slate-300 hover:text-white">
                Cancelar
              </button>
              <button onClick={confirmarEliminar} disabled={eliminando} className="rounded-lg bg-red-600 px-4 py-2.5 text-sm hover:bg-red-500 disabled:opacity-50">
                {eliminando ? "Eliminando…" : "Aceptar"}
              </button>
            </div>
          </div>
        </div>
      )}

      {tab === "revisiones" ? (
        <Revisiones abierta={revisionAbierta} setAbierta={setRevisionAbierta} />
      ) : tab !== "settings" ? (
        <>
          {enFavoritos ? (
            <p className="text-sm text-slate-400">
              {cars.length} favoritos · aquí haces el seguimiento (estado, notas y cita) de los coches que te interesan.
            </p>
          ) : (
            <Filters filters={filters} setFilters={setFilters} count={cars.length} />
          )}
          {!enFavoritos && <div className="flex items-center gap-3">
            <button
              onClick={runTop}
              disabled={lote.running || pendientes === 0}
              title={`Calcula margen e informe de IA de los ${TOP_N} primeros de la lista que aún no lo tienen al día`}
              className="rounded-lg bg-violet-700 px-4 py-2.5 text-sm hover:bg-violet-600 disabled:opacity-50 md:py-1.5"
            >
              {lote.running ? "Analizando…" : pendientes === 0 ? `Top ${TOP_N} al día` : `Analizar Top ${TOP_N}`}
            </button>
            {!lote.running && pendientes > 0 && <span className="text-xs text-slate-500">{pendientes} por analizar</span>}
          </div>}
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2 py-1 text-slate-400">
              <input
                type="checkbox"
                className="accent-red-500"
                checked={cars.length > 0 && cars.every((c) => seleccion.has(c.id))}
                onChange={(e) => setSeleccion(e.target.checked ? new Set(cars.map((c) => c.id)) : new Set())}
              />
              Seleccionar todos ({cars.length})
            </label>
            {seleccion.size > 0 && (
              <>
                <span className="text-slate-400">{seleccion.size} seleccionados</span>
                <button onClick={() => marcarFavoritos(!enFavoritos)} className="rounded-lg bg-amber-700 px-3 py-2 hover:bg-amber-600 md:py-1">
                  {enFavoritos ? "Quitar de favoritos" : "★ Añadir a favoritos"}
                </button>
                <button
                  onClick={() => setPorEliminar(cars.filter((c) => seleccion.has(c.id)))}
                  className="rounded-lg bg-red-700 px-3 py-2 hover:bg-red-600 md:py-1"
                >
                  Eliminar seleccionados
                </button>
              </>
            )}
          </div>
          {cars.length === 0 && (
            <p className="text-slate-400">
              {enFavoritos ? "Aún no tienes favoritos. Márcalos con «☆ Favorito» en la lista." : "Sin resultados. Ajusta los filtros o pulsa Sincronizar."}
            </p>
          )}
          {visibles.slice(0, limite).map((c) => (
            <CarCard key={c.id} car={c} onChange={onCarChange} selected={seleccion.has(c.id)} onSelect={toggleSel} onDelete={setPorEliminar} enFavoritos={enFavoritos} revision={revisiones[c.id]} onRevision={abrirRevision} />
          ))}
          {visibles.length > limite && (
            <button onClick={() => setLimite((n) => n + PAGINA)} className="w-full rounded-xl bg-slate-900 py-3 text-sm text-sky-400 ring-1 ring-slate-700">
              Mostrar más ({visibles.length - limite} restantes)
            </button>
          )}
        </>
      ) : (
        <Settings onSaved={load} onRun={runSync} syncRunning={sync.running} />
      )}
    </main>
  );
}

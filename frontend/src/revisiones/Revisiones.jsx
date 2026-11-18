import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import Checklist from "./Checklist.jsx";
import InformeTecnico from "./InformeTecnico.jsx";
import { Barra, Foto, Insignia, nombreCoche } from "./comun.jsx";

const PILLS = [
  ["en_curso", "Pendientes"],
  ["en_qc", "En QC"],
  ["finalizada", "Completadas"],
];

function Kpi({ valor, label, color = "text-white", className = "" }) {
  return (
    <div className={`rounded-xl bg-navy-900 p-3 ring-1 ring-white/10 ${className}`}>
      <p className={`text-2xl font-bold tabular-nums ${color}`}>{valor}</p>
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p>
    </div>
  );
}

function TarjetaRevision({ r, onOpen }) {
  const c = r.coche;
  return (
    <div role="button" tabIndex={0} onClick={() => onOpen(r.id)} onKeyDown={(e) => e.key === "Enter" && onOpen(r.id)} className="flex w-full cursor-pointer gap-3 rounded-xl bg-navy-900 p-3 text-left ring-1 ring-white/10 hover:ring-accent/60">
      <Foto src={c?.image_url} className="h-20 w-28 shrink-0 rounded-lg" />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Insignia estado={r.estado} />
          <span className="text-xs tabular-nums text-slate-400">{r.resumen.revisados}/{r.resumen.total} puntos</span>
        </div>
        <h3 className="truncate font-semibold">{nombreCoche(c)}</h3>
        <p className="text-sm text-slate-400">
          {c?.erstzulassung ?? "–"} · {c?.kilometer?.toLocaleString("de-DE") ?? "–"} km
          {r.cliente && ` · ${r.cliente}`}
        </p>
        <Barra pct={r.resumen.progreso} />
        {r.resumen.revisados > 0 && (
          <button onClick={(e) => { e.stopPropagation(); onOpen(r.id, "informe"); }} className="py-2 text-sm text-blue-300 hover:underline">Ver informe →</button>
        )}
      </div>
    </div>
  );
}

function Informe({ id, onBack, onEditar }) {
  const [det, setDet] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.inspection(id).then(setDet).catch((e) => setError(e.message)); }, [id]);
  if (error) return <p className="rounded-lg bg-red-950 px-4 py-2 text-sm text-red-300">{error}</p>;
  if (!det) return <p className="text-slate-400">Cargando…</p>;
  return <InformeTecnico det={det} onChange={setDet} onBack={onBack} onEditar={onEditar} />;
}

export default function Revisiones({ abierta, setAbierta }) {
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [pill, setPill] = useState("");
  const [error, setError] = useState(null);

  const load = useCallback(() => api.inspections().then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => {
    if (abierta == null) load();
  }, [abierta, load]);

  const abrir = (id, vista = "checklist") => setAbierta({ id, vista });
  if (abierta != null) {
    return abierta.vista === "informe"
      ? <Informe id={abierta.id} onBack={() => setAbierta(null)} onEditar={() => abrir(abierta.id)} />
      : <Checklist id={abierta.id} onBack={() => setAbierta(null)} onInforme={() => abrir(abierta.id, "informe")} />;
  }
  if (error) return <p className="rounded-lg bg-red-950 px-4 py-2 text-sm text-red-300">{error}</p>;
  if (!data) return <p className="text-slate-400">Cargando…</p>;

  const { kpis, continuar, revisiones } = data;
  const cuenta = (e) => revisiones.filter((r) => r.estado === e).length;
  const t = q.trim().toLowerCase();
  const visibles = revisiones.filter(
    (r) => (!pill || r.estado === pill) && (!t || [r.coche?.marke, r.coche?.modell, r.vin, r.cliente].some((x) => x?.toLowerCase().includes(t))),
  );

  return (
    <div className="space-y-4">
      {continuar && (
        <section className="rounded-2xl bg-gradient-to-br from-accent to-navy-900 p-4 ring-1 ring-white/10">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-200">Continuar trabajo</p>
          <div className="mt-2 flex items-center gap-3">
            <Foto src={continuar.coche?.image_url} className="h-16 w-24 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-lg font-semibold">{nombreCoche(continuar.coche)}</h3>
              <p className="text-sm text-blue-100">Progreso: {continuar.resumen.progreso}%</p>
            </div>
            <button onClick={() => abrir(continuar.id)} className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-navy-950">
              Continuar
            </button>
          </div>
          <Barra pct={continuar.resumen.progreso} className="mt-3 !bg-black/30" />
        </section>
      )}

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Kpi valor={kpis.pendientes} label="Pendientes" color="text-blue-300" />
        <Kpi valor={kpis.completadas_hoy} label="Completadas hoy" color="text-ok" />
        <Kpi valor={kpis.total_mes} label="Total este mes" />
        <Kpi valor={kpis.en_qc} label="En control (QC)" color="text-warn" />
        <Kpi valor={`${kpis.avance_medio}%`} label="Avance medio activo" className="col-span-2 sm:col-span-1" />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Mis revisiones</h2>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar por marca, modelo, VIN o cliente…"
          className="w-full rounded-lg bg-navy-900 px-3 py-2 text-sm ring-1 ring-white/10 placeholder:text-slate-500"
        />
        <div className="flex flex-wrap gap-2">
          {PILLS.map(([e, label]) => (
            <button
              key={e}
              onClick={() => setPill(pill === e ? "" : e)}
              className={`rounded-full px-3 py-2 text-sm ring-1 md:py-1 ${pill === e ? "bg-accent text-white ring-accent" : "text-slate-300 ring-white/15 hover:text-white"}`}
            >
              {label} <span className="tabular-nums opacity-80">({cuenta(e)})</span>
            </button>
          ))}
        </div>
        {visibles.length === 0 && (
          <p className="text-sm text-slate-400">
            {revisiones.length === 0
              ? "Aún no hay revisiones. Inicia una desde «★ Favoritos» con «Iniciar revisión técnica»."
              : "Ninguna revisión coincide con la búsqueda."}
          </p>
        )}
        {visibles.map((r) => <TarjetaRevision key={r.id} r={r} onOpen={abrir} />)}
      </section>
    </div>
  );
}

import { useState } from "react";
import { api } from "../api.js";
import { BarrasApiladas, COLORES, Donut } from "./charts.jsx";
import { Foto, nombreCoche } from "./comun.jsx";

const GLOBAL = {
  aprobado: { label: "APROBADO", estilo: "bg-ok/15 text-ok ring-ok/40" },
  atencion: { label: "ATENCIÓN REQUERIDA", estilo: "bg-warn/15 text-warn ring-warn/40" },
  no_recomendado: { label: "NO RECOMENDADO", estilo: "bg-bad/15 text-bad ring-bad/40" },
};
const ETIQUETA_ESTADO = { ok: "Correcto", aviso: "Advertencia", incidencia: "Incidencia" };
const fecha = (iso) => (iso ? new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleDateString("es-ES", { day: "2-digit", month: "short", year: "numeric" }) : "–");

const valorTxt = (p) => (p.valor == null ? null : p.tipo === "numero" ? `${p.valor} ${p.unidad}` : p.valor === "si" ? "Sí" : p.valor === "no" ? "No" : p.valor);

function IconoChip() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="2" /><rect x="9.5" y="9.5" width="5" height="5" rx="1" />
      <path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" />
    </svg>
  );
}

function Caja({ label, valor }) {
  return (
    <div className="rounded-xl bg-navy-950/70 p-3 text-center ring-1 ring-white/10">
      <p className="text-[10px] uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums sm:text-base">{valor}</p>
    </div>
  );
}

function TarjetaAtencion({ p }) {
  const color = p.estado === "incidencia" ? "bad" : "warn";
  const [grande, ...resto] = p.fotos;
  return (
    <article className={`overflow-hidden rounded-xl bg-navy-900 ring-1 ${color === "bad" ? "ring-bad/60" : "ring-warn/50"}`}>
      {grande && (
        <a href={grande.url} target="_blank" rel="noreferrer"><Foto src={grande.url} className="h-56 w-full sm:h-72" /></a>
      )}
      <div className="space-y-2 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ${color === "bad" ? "bg-bad/15 text-bad ring-bad/40" : "bg-warn/15 text-warn ring-warn/40"}`}>
            {ETIQUETA_ESTADO[p.estado].toUpperCase()}
          </span>
          <span className="font-mono text-[11px] text-slate-500">REF: {p.codigo}</span>
        </div>
        <h3 className="font-semibold">{p.etiqueta}</h3>
        {valorTxt(p) && <p className="text-sm text-slate-300">Resultado: <span className="font-medium text-white">{valorTxt(p)}</span></p>}
        <p className={`text-sm ${p.observaciones ? "text-slate-300" : "text-slate-500"}`}>{p.observaciones || "Sin observaciones del revisor."}</p>
        {resto.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-1">
            {resto.map((f) => <a key={f.id} href={f.url} target="_blank" rel="noreferrer"><Foto src={f.miniatura} className="h-16 w-16 rounded-lg" /></a>)}
          </div>
        )}
      </div>
    </article>
  );
}

export default function InformeTecnico({ det, onChange, onBack, onEditar }) {
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);
  const { resumen: r, puntos, coche: c, ia } = det;
  const informe = det.informe_ia;
  const texto = informe ?? det.diagnostico_basico;
  const global = GLOBAL[r.resultado];
  const atencion = [...puntos.filter((p) => p.estado === "incidencia"), ...puntos.filter((p) => p.estado === "aviso")];
  const correctos = puntos.filter((p) => p.estado === "ok");
  const portada = puntos.find((p) => p.codigo === "DOCUMENTACION-01")?.fotos[0]?.url ?? c?.image_url;

  const generar = async () => {
    setCargando(true);
    setError(null);
    try {
      onChange(await api.generateInspectionAI(det.id));
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="rounded-lg px-3 py-1 text-slate-300 ring-1 ring-white/15">← Volver</button>
        <button onClick={onEditar} className="text-sm text-blue-300">Editar checklist</button>
      </div>

      <section className="overflow-hidden rounded-2xl bg-navy-900 ring-1 ring-white/10">
        <Foto src={portada} className="h-52 w-full sm:h-72" />
        <div className="space-y-3 p-4">
          {global ? <span className={`inline-block rounded-full px-3 py-1 text-xs font-bold ring-1 ${global.estilo}`}>{global.label}</span>
                  : <span className="inline-block rounded-full px-3 py-1 text-xs font-bold text-slate-400 ring-1 ring-white/20">SIN REVISAR</span>}
          <div>
            <h1 className="text-2xl font-bold">{nombreCoche(c)}</h1>
            <p className="text-sm text-slate-400">Informe Ejecutivo de Inspección Técnica</p>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Caja label="Año" valor={c?.erstzulassung ?? "–"} />
            <Caja label="Kilómetros" valor={c?.kilometer?.toLocaleString("de-DE") ?? "–"} />
            <Caja label="Fecha" valor={fecha(det.finalizada_en ?? det.actualizado_en)} />
          </div>
        </div>
      </section>

      <section className="rounded-2xl bg-navy-900 p-4 ring-1 ring-white/10">
        <h2 className="mb-2 text-center font-semibold">Estado de la revisión</h2>
        <Donut ok={r.ok} aviso={r.aviso} incidencia={r.incidencia} />
        <div className="mt-3 grid grid-cols-3 text-center">
          {[["ok", "Correctos"], ["aviso", "Advertencias"], ["incidencia", "Incidencias"]].map(([k, label]) => (
            <div key={k}>
              <p className="text-3xl font-bold tabular-nums" style={{ color: COLORES[k] }}>{r[k]}</p>
              <p className="text-[10px] uppercase tracking-wider text-slate-400">{label}</p>
            </div>
          ))}
        </div>
        {r.revisados < r.total && <p className="mt-3 text-center text-xs text-slate-500">Faltan {r.total - r.revisados} de {r.total} puntos por revisar.</p>}
      </section>

      <section className="space-y-3 rounded-2xl bg-gradient-to-br from-accent to-blue-800 p-4 ring-1 ring-white/15">
        <div className="flex items-center gap-2">
          <IconoChip />
          <h2 className="flex-1 font-semibold">Análisis de Inteligencia Artificial</h2>
          <span className="rounded-full bg-black/25 px-2 py-0.5 text-[10px] font-semibold uppercase">
            {informe ? `${informe.uso?.proveedor ?? "IA"}` : "Análisis básico"}
          </span>
        </div>
        <div className="rounded-xl bg-black/25 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-200">Diagnóstico profesional</p>
          <p className="mt-1 text-sm leading-relaxed">{texto.diagnostico}</p>
        </div>
        {texto.insight && (
          <div className="rounded-xl bg-black/25 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-200">Insight exclusivo</p>
            <p className="mt-1 text-sm leading-relaxed">{texto.insight}</p>
          </div>
        )}
        {informe?.desactualizado && <p className="text-xs text-amber-200">Cambiaste puntos después de generar este análisis: pulsa «Actualizar análisis IA».</p>}
        {error && <p className="rounded-lg bg-red-950/80 px-3 py-2 text-sm text-red-200">{error}</p>}
        {!ia.activa && <p className="text-xs text-blue-100">Sin clave de IA en backend/.env: se muestra el análisis básico.</p>}
        <div className="flex items-center gap-3">
          <button onClick={generar} disabled={cargando || !ia.activa || r.revisados === 0} className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-navy-950 disabled:opacity-50">
            {cargando ? "Generando…" : informe ? "Actualizar análisis IA" : "Generar análisis IA"}
          </button>
          {informe?.uso && <span className="text-[11px] text-blue-100">{informe.uso.modelo} · ~{(informe.uso.tokens_entrada ?? 0) + (informe.uso.tokens_salida ?? 0) + (informe.uso.tokens_pensamiento ?? 0)} tokens</span>}
        </div>
      </section>

      <section className="rounded-2xl bg-navy-900 p-4 ring-1 ring-white/10">
        <h2 className="mb-4 font-semibold">Desglose de calidad por categoría</h2>
        <BarrasApiladas categorias={r.categorias} />
        <div className="mt-4 flex flex-wrap gap-4 text-xs text-slate-400">
          {Object.entries(COLORES).map(([k, col]) => <span key={k} className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm" style={{ background: col }} />{ETIQUETA_ESTADO[k]}</span>)}
        </div>
      </section>

      {atencion.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-semibold">Puntos de atención técnica <span className="text-sm font-normal text-slate-400">· {atencion.length} prioritarios</span></h2>
          <div className="grid gap-3 md:grid-cols-2">{atencion.map((p) => <TarjetaAtencion key={p.codigo} p={p} />)}</div>
        </section>
      )}

      {correctos.length > 0 && (
        <details className="group rounded-2xl bg-accent/15 ring-1 ring-accent/40">
          <summary className="flex cursor-pointer items-center justify-between p-4 font-semibold text-blue-200">
            {correctos.length} puntos perfectos verificados
            <span className="transition group-open:rotate-180">⌄</span>
          </summary>
          <ul className="divide-y divide-white/10 px-4 pb-2">
            {correctos.map((p) => (
              <li key={p.codigo} className="flex items-center gap-3 py-2.5">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-ok" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm">{p.etiqueta}{valorTxt(p) && <span className="text-slate-400"> · {valorTxt(p)}</span>}</p>
                  <p className="font-mono text-[10px] text-slate-500">REF: {p.codigo}{p.observaciones && ` · ${p.observaciones}`}</p>
                </div>
                <div className="flex gap-1">{p.fotos.slice(0, 3).map((f) => <a key={f.id} href={f.url} target="_blank" rel="noreferrer"><Foto src={f.miniatura} className="h-10 w-10 rounded" /></a>)}</div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

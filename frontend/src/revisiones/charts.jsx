import { useState } from "react";

export const COLORES = { ok: "#10b981", aviso: "#f59e0b", incidencia: "#ef4444" };
const NOMBRES = { ok: "Correctos", aviso: "Advertencias", incidencia: "Incidencias" };

/** Anillo con el desglose; en el centro, el total de puntos revisados. */
export function Donut({ ok, aviso, incidencia }) {
  const total = ok + aviso + incidencia;
  const R = 42, C = 2 * Math.PI * R;
  let acumulado = 0;
  const trozos = [["ok", ok], ["aviso", aviso], ["incidencia", incidencia]].filter(([, n]) => n > 0);
  return (
    <svg viewBox="0 0 120 120" className="mx-auto h-48 w-48" role="img" aria-label={`${ok} correctos, ${aviso} advertencias, ${incidencia} incidencias`}>
      <circle cx="60" cy="60" r={R} fill="none" stroke="#2a3558" strokeWidth="14" />
      {trozos.map(([k, n]) => {
        const largo = (n / total) * C;
        const el = (
          <circle key={k} cx="60" cy="60" r={R} fill="none" stroke={COLORES[k]} strokeWidth="14" strokeDasharray={`${Math.max(largo - (trozos.length > 1 ? 1.5 : 0), 0)} ${C}`}
                  strokeDashoffset={-acumulado} transform="rotate(-90 60 60)" />
        );
        acumulado += largo;
        return el;
      })}
      <text x="60" y="58" textAnchor="middle" className="fill-white text-[22px] font-bold">{total}</text>
      <text x="60" y="74" textAnchor="middle" className="fill-slate-400 text-[8px] uppercase tracking-wider">revisados</text>
    </svg>
  );
}

/** Una barra apilada por categoría, con tooltip al pasar el cursor o tocar un tramo. */
export function BarrasApiladas({ categorias }) {
  const [tip, setTip] = useState(null);  // {clave, tipo}
  return (
    <div className="space-y-4">
      {categorias.map((c) => {
        const revisados = c.ok + c.aviso + c.incidencia;
        let izq = 0;
        return (
          <div key={c.clave}>
            <div className="mb-1 flex justify-between text-sm">
              <span>{c.nombre}</span>
              <span className="tabular-nums text-slate-400">{revisados}/{c.total}</span>
            </div>
            <div className="relative">
              <div className="flex h-6 overflow-hidden rounded-md bg-navy-950">
                {["ok", "aviso", "incidencia"].map((k) => {
                  const ancho = c.total ? (c[k] / c.total) * 100 : 0;
                  if (!c[k]) return null;
                  const inicio = izq;
                  izq += ancho;
                  const activo = tip?.clave === c.clave && tip.tipo === k;
                  return (
                    <button
                      key={k}
                      style={{ width: `${ancho}%`, backgroundColor: COLORES[k] }}
                      className={`h-full text-xs font-semibold text-navy-950 ${activo ? "brightness-125" : ""}`}
                      onMouseEnter={() => setTip({ clave: c.clave, tipo: k, centro: inicio + ancho / 2 })}
                      onMouseLeave={() => setTip(null)}
                      onClick={() => setTip(activo ? null : { clave: c.clave, tipo: k, centro: inicio + ancho / 2 })}
                      aria-label={`${c.nombre}: ${c[k]} ${NOMBRES[k].toLowerCase()}`}
                    >
                      {ancho > 8 ? c[k] : ""}
                    </button>
                  );
                })}
              </div>
              {tip?.clave === c.clave && (
                <div style={{ left: `${Math.min(Math.max(tip.centro, 15), 85)}%` }} className="pointer-events-none absolute -top-9 z-10 -translate-x-1/2 whitespace-nowrap rounded-md bg-white px-2 py-1 text-xs font-medium text-navy-950 shadow-lg">
                  {c.nombre} · {NOMBRES[tip.tipo]}: {c[tip.tipo]}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

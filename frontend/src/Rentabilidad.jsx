import { useEffect, useRef } from "react";
import { api } from "./api.js";

const VEREDICTO_STYLE = {
  Comprar: "bg-green-600 text-white",
  Dudoso: "bg-amber-500 text-slate-950",
  Descartar: "bg-red-600 text-white",
};

const CONFIANZA_STYLE = {
  alta: "text-green-400",
  media: "text-amber-400",
  baja: "text-red-400",
};

const eur = (n) => (n == null ? "?" : `${Math.round(n).toLocaleString("de-DE")} €`);
const eurSigned = (n) => (n == null ? "?" : `${n > 0 ? "+" : ""}${eur(n)}`);

/** Insignia de la tarjeta: veredicto y margen estimado. */
export function RentabilidadBadge({ r }) {
  if (!r) return null;
  if (r.estado === "calculando") return <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-300">Analizando…</span>;
  if (r.estado === "error") return <span className="rounded-full bg-red-950 px-2 py-0.5 text-xs text-red-300" title={r.error}>Análisis con error</span>;
  if (r.estado !== "listo") return null;
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${VEREDICTO_STYLE[r.veredicto] ?? "bg-slate-700"}`}
      title={r.veredicto_origen === "ia" ? "Veredicto del informe de IA" : "Veredicto calculado solo con los números (sin IA)"}
    >
      {r.veredicto} · margen {eurSigned(r.calculo.margen_neto)}
      {r.desactualizado && " ⚠"}
    </span>
  );
}

/** Botón "Analizar rentabilidad". Mientras calcula, consulta el coche cada 3 s hasta que termina. */
export function RentabilidadButton({ car, onChange, onFinished }) {
  const r = car.rentabilidad;
  const calculando = r?.estado === "calculando";
  const estabaCalculando = useRef(false);

  useEffect(() => {
    if (!calculando) {
      if (estabaCalculando.current) onFinished?.(); // acaba de terminar: abre el informe
      estabaCalculando.current = false;
      return;
    }
    estabaCalculando.current = true;
    const id = setInterval(() => api.car(car.id).then(onChange).catch(console.error), 3000);
    return () => clearInterval(id);
  }, [calculando, car.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const lanzar = async () => {
    try {
      onChange(await api.analyzeProfitability(car.id));
    } catch (e) {
      alert(e.message);
    }
  };

  return (
    <button
      onClick={lanzar}
      disabled={calculando}
      className="rounded-md bg-sky-900/60 px-2.5 py-1 text-sky-200 ring-1 ring-sky-800 hover:bg-sky-800/60 disabled:opacity-60"
      title="Compara con precios reales en España (AutoScout24.es), calcula el margen con tus costes y pide un informe a la IA. Tarda 20-40 s."
    >
      {calculando ? "Analizando… (20-40 s)" : r?.estado === "listo" ? "Actualizar análisis" : "Analizar rentabilidad"}
    </button>
  );
}

function Lista({ titulo, items, color }) {
  if (!items?.length) return null;
  return (
    <div>
      <h4 className={`mb-1 text-xs font-semibold uppercase tracking-wide ${color}`}>{titulo}</h4>
      <ul className="list-disc space-y-1 pl-4 text-slate-300">
        {items.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

/** Informe desplegable de rentabilidad. */
export function Informe({ r }) {
  if (!r) return null;
  if (r.estado === "calculando") return <p className="mt-3 border-t border-slate-800 pt-3 text-sm text-slate-400">Analizando: consultando precios en España y calculando el margen…</p>;
  if (r.estado === "error")
    return <p className="mt-3 rounded-lg bg-red-950 px-3 py-2 text-sm text-red-300">No se pudo analizar: {r.error}</p>;

  const { calculo: c, mercado: m, informe: ia } = r;
  const fecha = new Date(r.calculado_el).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
  return (
    <div className="mt-3 space-y-4 border-t border-slate-800 pt-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${VEREDICTO_STYLE[r.veredicto]}`}>{r.veredicto}</span>
        <span className="text-xs text-slate-400">
          {r.veredicto_origen === "ia" ? `Informe de IA · puntuación ${ia.puntuacion}/10` : "Solo cálculo (sin informe de IA)"}
        </span>
        {r.veredicto_origen === "ia" && c.veredicto_numerico !== r.veredicto && (
          <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300" title="La IA puede valorar riesgos y estado que los números no ven, pero conviene contrastarlo">
            Solo por los números: {c.veredicto_numerico}
          </span>
        )}
        {r.desactualizado && (
          <span className="rounded bg-amber-950 px-2 py-0.5 text-xs text-amber-300">
            Cambiaste los costes de Ajustes después de este cálculo: pulsa "Actualizar análisis"
          </span>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg bg-slate-950 p-3">
          <div className="text-xs text-slate-500">Margen neto estimado</div>
          <div className={`text-2xl font-bold tabular-nums ${c.margen_neto >= 0 ? "text-green-400" : "text-red-400"}`}>{eurSigned(c.margen_neto)}</div>
          <div className="text-xs text-slate-500">
            rango {eurSigned(c.margen_pesimista)} a {eurSigned(c.margen_optimista)}
          </div>
        </div>
        <div className="rounded-lg bg-slate-950 p-3">
          <div className="text-xs text-slate-500">Rentabilidad sobre lo invertido</div>
          <div className="text-2xl font-bold tabular-nums">{c.roi_pct != null ? `${c.roi_pct} %` : "?"}</div>
          <div className="text-xs text-slate-500">invertido {eur(c.inversion)} (compra + costes)</div>
        </div>
        <div className="rounded-lg bg-slate-950 p-3">
          <div className="text-xs text-slate-500">Reventa esperada en España</div>
          <div className="text-2xl font-bold tabular-nums">{eur(c.venta_esperada)}</div>
          <div className="text-xs text-slate-500">
            anuncios ≈ {eur(c.referencia_es)} ({c.referencia_fuente})
          </div>
        </div>
      </div>

      {ia && (
        <div className="space-y-3 rounded-lg bg-slate-950 p-3">
          <p className="text-slate-200">{ia.resumen}</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Lista titulo="Puntos fuertes" items={ia.puntos_fuertes} color="text-green-400" />
            <Lista titulo="Riesgos" items={ia.riesgos} color="text-red-400" />
            <Lista titulo="Revisar antes de comprar" items={ia.revisar_antes_de_comprar} color="text-sky-400" />
          </div>
        </div>
      )}
      {r.aviso_ia && !ia && <p className="rounded bg-slate-800 px-3 py-2 text-xs text-slate-400">{r.aviso_ia}</p>}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Desglose ({r.perfil})</h4>
          <table className="w-full tabular-nums">
            <tbody>
              {c.lineas.map((l) => (
                <tr key={l.concepto} className="border-b border-slate-800/60">
                  <td className="py-1 pr-2 text-slate-300">{l.concepto}</td>
                  <td className={`py-1 text-right ${l.importe < 0 ? "text-slate-400" : "text-slate-100"}`}>{eurSigned(l.importe)}</td>
                </tr>
              ))}
              <tr>
                <td className="pt-1 pr-2 font-semibold">Margen neto</td>
                <td className="pt-1 text-right font-semibold">{eurSigned(c.margen_neto)}</td>
              </tr>
            </tbody>
          </table>
          {c.avisos?.map((a) => (
            <p key={a} className="mt-1 text-xs text-amber-400">{a}</p>
          ))}
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Comparables en España · confianza <span className={CONFIANZA_STYLE[m.confianza]}>{m.confianza}</span>
          </h4>
          <p className="text-slate-300">
            {m.n} anuncios · mediana {eur(m.mediana)} (rango {eur(m.p25)}–{eur(m.p75)})
            {m.mediana_particulares ? ` · particulares ${eur(m.mediana_particulares)}` : ""}
          </p>
          <p className="text-xs text-slate-500">Criterio: {m.criterio}. Precios de anuncio ajustados a los km y año de este coche.</p>
          <ul className="mt-2 space-y-1 text-xs">
            {m.muestra.map((s) => (
              <li key={s.url}>
                <a href={s.url} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">
                  {s.modell} {s.anio} · {s.km.toLocaleString("de-DE")} km · {eur(s.precio)}
                </a>
                <span className="text-slate-500">
                  {" "}
                  · {s.ort} · {s.vendedor === "Dealer" ? "profesional" : "particular"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="text-xs text-slate-500">
        Calculado el {fecha}{r.mercado_de_cache ? " con precios de España de los últimos 3 días" : ""}. Estimación orientativa con las cifras de Ajustes: no
        incluye IRPF / Impuesto de Sociedades ni imprevistos, y no es asesoramiento fiscal; confirma el IVA y la matriculación con tu gestor.
      </p>
    </div>
  );
}

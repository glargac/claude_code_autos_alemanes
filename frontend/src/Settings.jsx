import { useEffect, useState } from "react";
import { api } from "./api.js";

const MARKEN = ["Mercedes-Benz", "BMW", "Audi", "Volkswagen", "Porsche"];
const KRAFTSTOFF = ["Benzin", "Diesel"];

const WEIGHT_FIELDS = [
  ["kilometer", "Kilometer", "A menor km, más puntos"],
  ["klimaanlage", "Klimaanlage", "Aire acondicionado / Klimaautomatik"],
  ["tuev", "TÜV", "Vigencia de la ITV alemana"],
  ["precio", "Precio", "Más barato de lo esperado para su modelo, año y km = más puntos"],
  ["cabrio_saison", "Cabrio / estación", "Descapotables puntúan más en primavera-verano"],
  ["getriebe", "Cambio automático", "El automático se vende más en la Costa del Sol"],
];

const input =
  "w-full rounded-lg bg-slate-950 px-3 py-2 text-sm ring-1 ring-slate-700 focus:outline-none focus:ring-sky-500";

function Field({ label, children }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-slate-400">{label}</span>
      {children}
    </label>
  );
}

function Range({ label, lo, hi, value, onChange, step = 1 }) {
  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <input type="number" step={step} className={input} value={value[lo]} onChange={(e) => onChange(lo, e.target.value)} />
        <span className="text-slate-500">–</span>
        <input type="number" step={step} className={input} value={value[hi]} onChange={(e) => onChange(hi, e.target.value)} />
      </div>
    </Field>
  );
}

function Card({ title, hint, children }) {
  return (
    <section className="space-y-4 rounded-xl bg-slate-900 p-5 ring-1 ring-slate-800">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {hint && <p className="text-sm text-slate-400">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

export default function Settings({ onSaved, onRun, syncRunning }) {
  const [search, setSearch] = useState(null);
  const [weights, setWeights] = useState(null);
  const [app, setApp] = useState(null);
  const [rent, setRent] = useState(null);
  const [ia, setIa] = useState(null);
  const [msg, setMsg] = useState(null); // {ok, text}
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.getSetting("ia").then(setIa).catch(() => {}); // solo informativo
    Promise.all([api.getSetting("search"), api.getSetting("weights"), api.getSetting("app"), api.getSetting("rentabilidad")])
      .then(([s, w, a, r]) => {
        setRent(r);
        setSearch(s);
        setWeights(w);
        setApp(a);
      })
      .catch((e) => setMsg({ ok: false, text: e.message }));
  }, []);

  if (!search || !weights || !app || !rent) return <p className="text-slate-400">{msg ? msg.text : "Cargando…"}</p>;

  const setS = (k, v) => setSearch((s) => ({ ...s, [k]: v }));
  const setNum = (k, v) => setS(k, v === "" ? "" : Number(v));
  const toggle = (k, item) =>
    setS(k, search[k].includes(item) ? search[k].filter((x) => x !== item) : [...search[k], item]);
  const setR = (k, v) => setRent((r) => ({ ...r, [k]: v }));
  const setRNum = (k, v) => setR(k, v === "" ? "" : Number(v));
  const setA = (k, v) => setApp((a) => ({ ...a, [k]: v }));
  const setW = (k, v) => setWeights((w) => ({ ...w, [k]: v === "" ? "" : Number(v) }));

  const totalW = WEIGHT_FIELDS.reduce((a, [k]) => a + (Number(weights[k]) || 0), 0);

  const save = async (run) => {
    setBusy(true);
    setMsg(null);
    try {
      setSearch(await api.saveSetting("search", search));
      setWeights(await api.saveSetting("weights", weights));
      setApp(await api.saveSetting("app", app));
      setRent(await api.saveSetting("rentabilidad", rent));
      if (run) {
        await onRun();
      } else {
        setMsg({ ok: true, text: "Ajustes guardados y scores recalculados." });
        onSaved();
      }
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <Card title="Búsqueda" hint="Se aplica en kleinanzeigen.de y AutoScout24.">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Ort oder PLZ">
            <input className={input} value={search.ort_oder_plz} onChange={(e) => setS("ort_oder_plz", e.target.value)} />
          </Field>
          <Field label="Umkreis (km)">
            <input type="number" className={input} value={search.umkreis_km} onChange={(e) => setNum("umkreis_km", e.target.value)} />
          </Field>
          <Field label="Modell (opcional)">
            <input className={input} placeholder="p. ej. 320d" value={search.modell} onChange={(e) => setS("modell", e.target.value)} />
          </Field>
          <Range label="Preis ab / bis (€)" lo="preis_ab" hi="preis_bis" value={search} onChange={setNum} step={500} />
          <Range label="Erstzulassung ab / bis" lo="erstzulassung_ab" hi="erstzulassung_bis" value={search} onChange={setNum} />
          <Range label="Kilometer ab / bis" lo="kilometer_ab" hi="kilometer_bis" value={search} onChange={setNum} step={5000} />
          <Field label="Getriebe">
            <select className={input} value={search.getriebe} onChange={(e) => setS("getriebe", e.target.value)}>
              <option value="">Alle</option>
              <option>Automatik</option>
              <option>Manuell</option>
            </select>
          </Field>
          <Field label="Kraftstoffart">
            <div className="flex gap-4 py-2">
              {KRAFTSTOFF.map((f) => (
                <label key={f} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={search.kraftstoffart.includes(f)} onChange={() => toggle("kraftstoffart", f)} />
                  {f}
                </label>
              ))}
            </div>
          </Field>
          <Field label="Marke">
            <div className="flex flex-wrap gap-x-4 gap-y-1 py-2">
              {MARKEN.map((m) => (
                <label key={m} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={search.marken.includes(m)} onChange={() => toggle("marken", m)} />
                  {m}
                </label>
              ))}
            </div>
          </Field>
        </div>
      </Card>

      <Card title="Scoring" hint="Pesos relativos: se normalizan, así que no tienen que sumar 100.">
        <div className="space-y-4">
          {WEIGHT_FIELDS.map(([k, label, help]) => (
            <div key={k} className="grid items-center gap-3 sm:grid-cols-[12rem_1fr_4rem]">
              <div>
                <div className="text-sm">{label}</div>
                <div className="text-xs text-slate-500">{help}</div>
              </div>
              <input type="range" min="0" max="1" step="0.05" value={weights[k]} onChange={(e) => setW(k, e.target.value)} className="accent-sky-500" />
              <span className="text-right text-sm tabular-nums text-slate-300">
                {totalW > 0 ? Math.round(((Number(weights[k]) || 0) / totalW) * 100) : 0}%
              </span>
            </div>
          ))}
        </div>
        <div className="grid gap-4 border-t border-slate-800 pt-4 sm:grid-cols-2">
          <Field label="Umbral verde (score ≥)">
            <input type="number" step="0.1" min="0" max="10" className={input} value={weights.umbral_verde} onChange={(e) => setW("umbral_verde", e.target.value)} />
          </Field>
          <Field label="Umbral amarillo (score ≥; por debajo = rojo)">
            <input type="number" step="0.1" min="0" max="10" className={input} value={weights.umbral_amarillo} onChange={(e) => setW("umbral_amarillo", e.target.value)} />
          </Field>
        </div>
      </Card>

      <Card
        title="Rentabilidad: costes de importación"
        hint="Para el botón «Analizar rentabilidad». Cifras aproximadas y editables; el margen = venta esperada en España − compra − todos estos costes."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Importas como">
            <select className={input} value={rent.perfil} onChange={(e) => setR("perfil", e.target.value)}>
              <option value="particular">Particular</option>
              <option value="empresa">Empresa</option>
            </select>
          </Field>
          <Field label="Descuento sobre el anuncio al vender en España (%)">
            <input type="number" step="0.5" min="0" className={input} value={rent.descuento_venta_pct} onChange={(e) => setRNum("descuento_venta_pct", e.target.value)} />
          </Field>
          <Field label="Negociación a la baja en la compra (%)">
            <input type="number" step="0.5" min="0" className={input} value={rent.descuento_compra_pct} onChange={(e) => setRNum("descuento_compra_pct", e.target.value)} />
          </Field>
          <Field label="Transporte a la Costa del Sol (€)">
            <input type="number" step="50" min="0" className={input} value={rent.transporte} onChange={(e) => setRNum("transporte", e.target.value)} />
          </Field>
          <Field label="Gestoría, tasa DGT, ITV de importación, placas (€)">
            <input type="number" step="50" min="0" className={input} value={rent.gestoria_matriculacion} onChange={(e) => setRNum("gestoria_matriculacion", e.target.value)} />
          </Field>
          <Field label="Impuesto de matriculación (% de la compra)">
            <input type="number" step="0.25" min="0" className={input} value={rent.impuesto_matriculacion_pct} onChange={(e) => setRNum("impuesto_matriculacion_pct", e.target.value)} />
          </Field>
          <Field label="Preparación y pequeñas reparaciones (€)">
            <input type="number" step="50" min="0" className={input} value={rent.preparacion} onChange={(e) => setRNum("preparacion", e.target.value)} />
          </Field>
          <Field label="Seguro y placas de tránsito (€)">
            <input type="number" step="50" min="0" className={input} value={rent.seguro_y_placas_transito} onChange={(e) => setRNum("seguro_y_placas_transito", e.target.value)} />
          </Field>
          <Field label="Gastos de venta: anuncios (€)">
            <input type="number" step="50" min="0" className={input} value={rent.gastos_venta} onChange={(e) => setRNum("gastos_venta", e.target.value)} />
          </Field>
          <Field label="Otros costes (€)">
            <input type="number" step="50" min="0" className={input} value={rent.otros_costes} onChange={(e) => setRNum("otros_costes", e.target.value)} />
          </Field>
        </div>
        <p className={`rounded-lg px-3 py-2 text-xs ${ia?.activa ? "bg-green-950 text-green-300" : "bg-slate-800 text-slate-400"}`}>
          {ia?.activa
            ? `Informe de IA activado: ${ia.proveedor} · ${ia.modelo}.`
            : "Informe de IA desactivado: pon GEMINI_API_KEY (o ANTHROPIC_API_KEY) en backend/.env y reinicia el backend. Sin clave, «Analizar rentabilidad» muestra el cálculo sin informe de texto."}
        </p>
        <p className="text-xs text-slate-500">
          Matriculación según emisiones de CO₂ (orientativo): menos de 120 g/km → 0 %; 120-159 → 4,75 %; 160-199 → 9,75 %; 200 o más → 14,75 %.
        </p>

        {rent.perfil === "empresa" && (
          <div className="grid gap-4 border-t border-slate-800 pt-4 sm:grid-cols-3">
            <Field label="IVA en la reventa">
              <select className={input} value={rent.iva_reventa} onChange={(e) => setR("iva_reventa", e.target.value)}>
                <option value="rebu">REBU: IVA solo sobre el margen</option>
                <option value="general">Régimen general: IVA sobre el precio</option>
              </select>
            </Field>
            <Field label="Compra en Alemania">
              <label className="flex items-center gap-2 py-2 text-sm">
                <input type="checkbox" checked={rent.compra_con_iva_deducible} onChange={(e) => setR("compra_con_iva_deducible", e.target.checked)} />
                A un profesional, con IVA deducible
              </label>
            </Field>
            <Field label="IVA España / Alemania (%)">
              <div className="flex items-center gap-2">
                <input type="number" step="1" min="0" className={input} value={rent.iva_es_pct} onChange={(e) => setRNum("iva_es_pct", e.target.value)} />
                <input type="number" step="1" min="0" className={input} value={rent.iva_de_pct} onChange={(e) => setRNum("iva_de_pct", e.target.value)} />
              </div>
            </Field>
          </div>
        )}

        <div className="grid gap-4 border-t border-slate-800 pt-4 sm:grid-cols-3">
          <Field label="«Comprar» si el margen neto es al menos (€)">
            <input type="number" step="100" className={input} value={rent.margen_comprar_eur} onChange={(e) => setRNum("margen_comprar_eur", e.target.value)} />
          </Field>
          <Field label="…y la rentabilidad sobre lo invertido (%)">
            <input type="number" step="1" className={input} value={rent.roi_comprar_pct} onChange={(e) => setRNum("roi_comprar_pct", e.target.value)} />
          </Field>
          <Field label="«Descartar» si el margen es menor que (€)">
            <input type="number" step="100" className={input} value={rent.margen_dudoso_eur} onChange={(e) => setRNum("margen_dudoso_eur", e.target.value)} />
          </Field>
        </div>
        <p className="text-xs text-slate-500">
          Estimación orientativa, no es asesoramiento fiscal. No incluye IRPF / Impuesto de Sociedades, ITP del comprador ni imprevistos.
        </p>
      </Card>

      <Card title="Sincronización" hint="La lista se actualiza al abrir la app (si los datos están desactualizados) o con el botón Sincronizar.">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Al abrir la app">
            <label className="flex items-center gap-2 py-2 text-sm">
              <input type="checkbox" checked={app.auto_sync_on_open} onChange={(e) => setA("auto_sync_on_open", e.target.checked)} />
              Sincronizar si los datos están desactualizados
            </label>
          </Field>
          <Field label="Desactualizados tras (horas)">
            <input type="number" min="1" max="168" disabled={!app.auto_sync_on_open} className={`${input} disabled:opacity-40`} value={app.max_age_hours} onChange={(e) => setA("max_age_hours", e.target.value === "" ? "" : Number(e.target.value))} />
          </Field>
        </div>
        <div className="grid gap-4 border-t border-slate-800 pt-4 sm:grid-cols-2">
          <Field label="Sync diaria programada">
            <label className="flex items-center gap-2 py-2 text-sm">
              <input type="checkbox" checked={app.daily_sync} onChange={(e) => setA("daily_sync", e.target.checked)} />
              Activar (para cuando la app esté en un servidor)
            </label>
          </Field>
          <Field label="Hora de la sync diaria (0-23)">
            <input type="number" min="0" max="23" disabled={!app.daily_sync} className={`${input} disabled:opacity-40`} value={app.sync_hour} onChange={(e) => setA("sync_hour", e.target.value === "" ? "" : Number(e.target.value))} />
          </Field>
        </div>
        <p className="text-xs text-slate-500">En un Mac que se duerme, la sync programada no se ejecuta; por eso viene desactivada.</p>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <button onClick={() => save(false)} disabled={busy} className="rounded-lg bg-slate-700 px-4 py-2 text-sm hover:bg-slate-600 disabled:opacity-50">
          Guardar
        </button>
        <button onClick={() => save(true)} disabled={busy || syncRunning} className="rounded-lg bg-sky-600 px-4 py-2 text-sm hover:bg-sky-500 disabled:opacity-50">
          {syncRunning ? "Sincronización en curso…" : "Guardar y Ejecutar"}
        </button>
        {msg && <span className={`text-sm ${msg.ok ? "text-green-400" : "text-red-400"}`}>{msg.text}</span>}
      </div>
    </div>
  );
}

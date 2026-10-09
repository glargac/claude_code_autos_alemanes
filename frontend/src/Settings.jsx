import { useEffect, useState } from "react";
import { api } from "./api.js";

const MARKEN = ["Mercedes-Benz", "BMW", "Audi", "Volkswagen", "Porsche"];
const KRAFTSTOFF = ["Benzin", "Diesel"];

const WEIGHT_FIELDS = [
  ["kilometer", "Kilometer", "A menor km, más puntos"],
  ["klimaanlage", "Klimaanlage", "Aire acondicionado / Klimaautomatik"],
  ["tuev", "TÜV", "Vigencia de la ITV alemana"],
  ["precio", "Precio", "Más barato que coches comparables (mismo modelo y año ±2) = más puntos"],
  ["cabrio_saison", "Cabrio / estación", "Descapotables puntúan más en primavera-verano"],
  ["llm_rentabilidad", "Rentabilidad (LLM)", "Margen y demanda en la Costa del Sol"],
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
  const [msg, setMsg] = useState(null); // {ok, text}
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([api.getSetting("search"), api.getSetting("weights"), api.getSetting("app")])
      .then(([s, w, a]) => {
        setSearch(s);
        setWeights(w);
        setApp(a);
      })
      .catch((e) => setMsg({ ok: false, text: e.message }));
  }, []);

  if (!search || !weights || !app) return <p className="text-slate-400">{msg ? msg.text : "Cargando…"}</p>;

  const setS = (k, v) => setSearch((s) => ({ ...s, [k]: v }));
  const setNum = (k, v) => setS(k, v === "" ? "" : Number(v));
  const toggle = (k, item) =>
    setS(k, search[k].includes(item) ? search[k].filter((x) => x !== item) : [...search[k], item]);
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

      <Card title="Sincronización" hint="Cuándo se actualiza la lista de anuncios desde la fuente.">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Sync diaria a las (hora, 0-23)">
            <input type="number" min="0" max="23" className={input} value={app.sync_hour} onChange={(e) => setA("sync_hour", e.target.value === "" ? "" : Number(e.target.value))} />
          </Field>
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
        <p className="text-xs text-slate-500">La sync diaria solo se ejecuta si la aplicación está abierta a esa hora.</p>
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

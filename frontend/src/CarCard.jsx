import { useState } from "react";
import { api } from "./api.js";

const SCORE_COLORS = {
  verde: "bg-green-500",
  amarillo: "bg-amber-500",
  rojo: "bg-red-500",
  gris: "bg-slate-500",
};

export const STATUSES = ["Neu", "Kontaktiert", "Termin vereinbart", "Kaufoption", "Abgelehnt"];

const STATUS_STYLE = {
  Neu: "bg-slate-700 text-slate-200",
  Kontaktiert: "bg-sky-900 text-sky-200",
  "Termin vereinbart": "bg-violet-900 text-violet-200",
  Kaufoption: "bg-green-600 text-white",
  Abgelehnt: "bg-red-600 text-white",
};

const DETAIL_LABELS = {
  kilometer: "Kilometer",
  klimaanlage: "Klima",
  tuev: "TÜV",
  cabrio_saison: "Cabrio",
  llm_rentabilidad: "Rentabilidad",
};

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) : null);
const toLocalInput = (iso) => (iso ? iso.slice(0, 16) : "");

function Crm({ car, onChange }) {
  const [status, setStatus] = useState(car.status);
  const [termin, setTermin] = useState(toLocalInput(car.termin_am));
  const [notes, setNotes] = useState(car.notizen);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const save = async (body, okText) => {
    setBusy(true);
    setMsg(null);
    try {
      onChange(await api.updateCar(car.id, body));
      setMsg({ ok: true, text: okText });
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const applyStatus = (s) => {
    setStatus(s);
    if (s !== "Termin vereinbart") save({ status: s }, `Estado: ${s}`);
  };

  return (
    <div className="mt-3 space-y-3 border-t border-slate-800 pt-3">
      <div className="flex flex-wrap items-center gap-2">
        {STATUSES.map((s, i) => (
          <button
            key={s}
            disabled={busy}
            onClick={() => applyStatus(s)}
            className={`rounded-full px-3 py-1 text-xs ring-1 ${
              status === s ? `${STATUS_STYLE[s]} ring-transparent` : "text-slate-400 ring-slate-700 hover:text-white"
            }`}
          >
            {i < 3 && `${i + 1}. `}
            {s}
          </button>
        ))}
      </div>

      {status === "Termin vereinbart" && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="datetime-local"
            value={termin}
            onChange={(e) => setTermin(e.target.value)}
            className="rounded-lg bg-slate-950 px-3 py-1.5 text-sm ring-1 ring-slate-700"
          />
          <button
            disabled={busy || !termin}
            onClick={() => save({ status, termin_am: termin }, "Cita guardada")}
            className="rounded-lg bg-violet-700 px-3 py-1.5 text-sm hover:bg-violet-600 disabled:opacity-50"
          >
            Guardar cita
          </button>
        </div>
      )}

      <div>
        <textarea
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notas internas: contacto con el vendedor, resultado de la visita, defectos…"
          className="w-full rounded-lg bg-slate-950 px-3 py-2 text-sm ring-1 ring-slate-700 focus:outline-none focus:ring-sky-500"
        />
        <div className="mt-1 flex items-center gap-3">
          <button
            disabled={busy || notes === car.notizen}
            onClick={() => save({ notizen: notes }, "Notas guardadas")}
            className="rounded-lg bg-slate-700 px-3 py-1.5 text-sm hover:bg-slate-600 disabled:opacity-40"
          >
            Guardar notas
          </button>
          {msg && <span className={`text-xs ${msg.ok ? "text-green-400" : "text-red-400"}`}>{msg.text}</span>}
        </div>
      </div>
    </div>
  );
}

export default function CarCard({ car, onChange }) {
  const [open, setOpen] = useState(false);
  const ring =
    car.status === "Kaufoption"
      ? "ring-2 ring-green-500"
      : car.status === "Abgelehnt"
        ? "ring-2 ring-red-500 opacity-70"
        : "ring-1 ring-slate-800";
  const published = fmtDate(car.veroeffentlicht_am);

  return (
    <article className={`rounded-xl bg-slate-900 p-4 ${ring}`}>
      <div className="flex gap-4">
        {car.image_url && <img src={car.image_url} alt="" className="h-28 w-40 shrink-0 rounded-lg object-cover" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-semibold">
              {car.marke} {car.modell}
            </h2>
            <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLE[car.status]}`}>
              {car.status}
              {car.status === "Termin vereinbart" && car.termin_am && ` · ${new Date(car.termin_am).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" })}`}
            </span>
            {!car.aktiv && <span className="rounded-full bg-slate-600 px-2 py-0.5 text-xs">Verkauft / Inaktiv</span>}
          </div>
          <p className="text-sm text-slate-400">
            {car.erstzulassung} · {car.kilometer?.toLocaleString("de-DE")} km · {car.preis?.toLocaleString("de-DE")} € · TÜV {car.tuev_bis ?? "?"}
            {car.getriebe && ` · ${car.getriebe}`}
            {published && ` · publicado ${published}`}
          </p>
          {car.llm_analyse && <p className="mt-1 text-sm">{car.llm_analyse}</p>}
          <div className="mt-2 flex items-center gap-4 text-sm">
            <a href={car.url} target="_blank" rel="noreferrer" className="text-sky-400">
              Ver anuncio original ↗
            </a>
            <button onClick={() => setOpen(!open)} className="text-slate-400 hover:text-white">
              {open ? "Cerrar seguimiento" : car.notizen ? "Seguimiento · con notas" : "Seguimiento"}
            </button>
          </div>
        </div>
        <div className="shrink-0 text-center">
          <div className={`h-12 w-12 rounded-full text-lg font-bold leading-[3rem] text-slate-950 ${SCORE_COLORS[car.farbe]}`}>
            {car.score ?? "–"}
          </div>
        </div>
      </div>

      {open && (
        <>
          {car.score_detail && (
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
              {Object.entries(car.score_detail).map(([k, v]) => (
                <span key={k} className="rounded bg-slate-800 px-2 py-0.5">
                  {DETAIL_LABELS[k] ?? k} {v}
                </span>
              ))}
            </div>
          )}
          <Crm car={car} onChange={onChange} />
        </>
      )}
    </article>
  );
}

import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Barra, ESTADOS_PUNTO, Foto, Insignia, nombreCoche } from "./comun.jsx";

const campo = "rounded-lg bg-navy-950 px-3 py-2 text-sm ring-1 ring-white/10 placeholder:text-slate-500";

function Valor({ punto, onChange }) {
  const [txt, setTxt] = useState(punto.valor ?? "");
  useEffect(() => setTxt(punto.valor ?? ""), [punto.valor]);
  if (punto.tipo === "numero") {
    const guardar = () => {
      const n = txt === "" ? null : Number(String(txt).replace(",", "."));
      if (n !== punto.valor && (n === null || !Number.isNaN(n))) onChange({ valor: n });
    };
    return (
      <label className="flex items-center gap-2 text-sm text-slate-300">
        <input
          inputMode="decimal"
          value={txt}
          onChange={(e) => setTxt(e.target.value)}
          onBlur={guardar}
          placeholder="0"
          className={`${campo} w-28 text-base`}
        />
        {punto.unidad}
      </label>
    );
  }
  const opciones = punto.tipo === "sino" ? [["si", "Sí"], ["no", "No"]] : punto.opciones.map((o) => [o, o]);
  return (
    <div className="flex flex-wrap gap-2">
      {opciones.map(([v, label]) => (
        <button
          key={v}
          onClick={() => onChange({ valor: punto.valor === v ? null : v })}
          className={`rounded-lg px-4 py-2 text-sm ring-1 ${punto.valor === v ? "bg-accent text-white ring-accent" : "text-slate-300 ring-white/15"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Punto({ punto, onSave, onPhotos, onDeletePhoto }) {
  const [abierto, setAbierto] = useState(false);
  const [obs, setObs] = useState(punto.observaciones);
  const input = useRef(null);
  const e = ESTADOS_PUNTO[punto.estado];
  const detalle = abierto || punto.fotos.length > 0 || punto.observaciones || punto.estado === "aviso" || punto.estado === "incidencia";

  return (
    <div className={`space-y-3 rounded-xl bg-navy-900 p-3 ring-1 ${punto.estado === "incidencia" ? "ring-bad/60" : punto.estado === "aviso" ? "ring-warn/50" : "ring-white/10"}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-wider text-slate-500">REF: {punto.codigo}</p>
          <h3 className="text-[15px] font-medium leading-snug">{punto.etiqueta}</h3>
        </div>
        <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${e ? e.punto : "bg-slate-600"}`} />
      </div>

      <div className="grid grid-cols-3 gap-2">
        {Object.entries(ESTADOS_PUNTO).map(([k, v]) => (
          <button
            key={k}
            onClick={() => onSave({ estado: punto.estado === k ? null : k })}
            className={`rounded-lg py-2.5 text-xs font-semibold ${punto.estado === k ? v.activo : "bg-navy-950 text-slate-300 ring-1 ring-white/10"}`}
          >
            {v.label}
          </button>
        ))}
      </div>

      {punto.tipo !== "estado" && <Valor punto={punto} onChange={onSave} />}

      {detalle ? (
        <div className="space-y-2">
          <textarea
            rows={2}
            value={obs}
            onChange={(ev) => setObs(ev.target.value)}
            onBlur={() => obs !== punto.observaciones && onSave({ observaciones: obs })}
            placeholder="Observaciones del revisor…"
            className={`${campo} w-full`}
          />
          <div className="flex flex-wrap gap-2">
            {punto.fotos.map((f) => (
              <div key={f.id} className="relative">
                <a href={f.url} target="_blank" rel="noreferrer">
                  <Foto src={f.miniatura} className="h-20 w-20 rounded-lg" />
                </a>
                <button
                  onClick={() => confirm("¿Borrar esta foto?") && onDeletePhoto(f.id)}
                  aria-label="Borrar foto"
                  className="absolute -right-1.5 -top-1.5 h-6 w-6 rounded-full bg-bad text-xs text-white"
                >
                  ✕
                </button>
              </div>
            ))}
            <button onClick={() => input.current.click()} className="flex h-20 w-20 flex-col items-center justify-center rounded-lg text-xs text-slate-300 ring-1 ring-dashed ring-white/25">
              <span className="text-xl">📷</span>Foto
            </button>
            <input ref={input} type="file" accept="image/*" multiple hidden onChange={(ev) => { onPhotos([...ev.target.files]); ev.target.value = ""; }} />
          </div>
        </div>
      ) : (
        <button onClick={() => setAbierto(true)} className="text-xs text-blue-300">+ Foto u observación</button>
      )}
    </div>
  );
}

export default function Checklist({ id, onBack, onInforme }) {
  const [det, setDet] = useState(null);
  const [cat, setCat] = useState("documentacion");
  const [soloPend, setSoloPend] = useState(false);
  const [guardado, setGuardado] = useState({ pendientes: 0, error: null });
  const [error, setError] = useState(null);

  useEffect(() => { api.inspection(id).then(setDet).catch((e) => setError(e.message)); }, [id]);

  const trabajo = async (fn) => {
    setGuardado((g) => ({ ...g, pendientes: g.pendientes + 1 }));
    try {
      const r = await fn();
      setGuardado((g) => ({ pendientes: g.pendientes - 1, error: null }));
      return r;
    } catch (e) {
      setGuardado((g) => ({ pendientes: g.pendientes - 1, error: e.message }));
      throw e;
    }
  };
  const mapPunto = (codigo, f) => setDet((d) => ({ ...d, puntos: d.puntos.map((p) => (p.codigo === codigo ? f(p) : p)) }));

  const guardarPunto = (codigo) => (cambio) => {
    mapPunto(codigo, (p) => ({ ...p, ...cambio }));  // optimista: el toque se ve al instante
    trabajo(() => api.saveItem(id, codigo, cambio)).catch(() => api.inspection(id).then(setDet));  // si falla, vuelve a lo guardado
  };
  const subirFotos = (codigo) => (files) =>
    trabajo(() => api.uploadPhotos(id, codigo, files)).then((nuevas) => mapPunto(codigo, (p) => ({ ...p, fotos: [...p.fotos, ...nuevas] }))).catch(() => {});
  const borrarFoto = (codigo) => (mid) =>
    trabajo(() => api.deletePhoto(mid)).then(() => mapPunto(codigo, (p) => ({ ...p, fotos: p.fotos.filter((f) => f.id !== mid) }))).catch(() => {});
  const guardarCabecera = (cambio) => trabajo(() => api.updateInspection(id, cambio)).then((r) => setDet((d) => ({ ...d, ...cambio, estado: r.estado, finalizada_en: r.finalizada_en }))).catch(() => {});

  if (error) return <p className="rounded-lg bg-red-950 px-4 py-2 text-sm text-red-300">{error} <button className="underline" onClick={onBack}>Volver</button></p>;
  if (!det) return <p className="text-slate-400">Cargando…</p>;

  const cuenta = (ps) => ps.filter((p) => p.estado).length;
  const total = det.puntos.length;
  const hechos = cuenta(det.puntos);
  const pct = Math.round((100 * hechos) / total);
  const porCat = {};
  det.puntos.forEach((p) => (porCat[p.categoria] ??= { nombre: p.categoria_nombre, puntos: [] }).puntos.push(p));
  const claves = Object.keys(porCat);
  const actual = porCat[cat] ?? porCat[claves[0]];
  const lista = soloPend ? actual.puntos.filter((p) => !p.estado) : actual.puntos;
  const siguiente = claves[claves.indexOf(cat) + 1];
  const c = det.coche;

  const cambiarEstado = (estado, aviso) => {
    if (aviso && hechos < total && !confirm(`Faltan ${total - hechos} puntos por revisar. ¿Continuar igualmente?`)) return;
    guardarCabecera({ estado });
  };
  const eliminar = async () => {
    if (!confirm("¿Eliminar esta revisión con todos sus puntos y fotos? No se puede deshacer.")) return;
    await api.deleteInspection(id).then(onBack).catch((e) => alert(e.message));
  };

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 -mx-4 space-y-2 bg-navy-950/95 px-4 py-3 backdrop-blur md:-mx-6 md:px-6">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="rounded-lg px-3 py-2 text-slate-300 ring-1 ring-white/15" aria-label="Volver">←</button>
          <div className="min-w-0 flex-1">
            <h2 className="truncate font-semibold">{nombreCoche(c)}</h2>
            <p className="text-xs text-slate-400">{c?.erstzulassung} · {c?.kilometer?.toLocaleString("de-DE")} km</p>
          </div>
          <Insignia estado={det.estado} />
        </div>
        <div className="flex items-center gap-3">
          <Barra pct={pct} className="flex-1" />
          <span className="text-xs tabular-nums text-slate-300">{hechos}/{total} · {pct}%</span>
          <span className={`text-xs ${guardado.error ? "text-bad" : "text-slate-500"}`} title={guardado.error ?? ""}>
            {guardado.error ? "⚠ No guardado" : guardado.pendientes ? "Guardando…" : "✓ Guardado"}
          </span>
        </div>
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
          {claves.map((k) => (
            <button
              key={k}
              onClick={() => setCat(k)}
              className={`shrink-0 rounded-full px-3 py-2 text-sm ring-1 ${k === actual.puntos[0].categoria ? "bg-accent text-white ring-accent" : "text-slate-300 ring-white/15"}`}
            >
              {porCat[k].nombre} <span className="tabular-nums opacity-75">{cuenta(porCat[k].puntos)}/{porCat[k].puntos.length}</span>
            </button>
          ))}
        </div>
      </div>

      <details className="rounded-xl bg-navy-900 p-3 ring-1 ring-white/10" open={!det.cliente && !det.vin}>
        <summary className="cursor-pointer text-sm text-slate-300">Datos de la revisión {det.cliente && `· ${det.cliente}`}</summary>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <input defaultValue={det.cliente} onBlur={(e) => e.target.value !== det.cliente && guardarCabecera({ cliente: e.target.value })} placeholder="Cliente / comprador" className={campo} />
          <input defaultValue={det.vin} onBlur={(e) => e.target.value.toUpperCase() !== det.vin && guardarCabecera({ vin: e.target.value })} placeholder="VIN (bastidor)" className={`${campo} uppercase`} />
        </div>
      </details>

      <label className="flex items-center gap-2 text-sm text-slate-400">
        <input type="checkbox" checked={soloPend} onChange={(e) => setSoloPend(e.target.checked)} /> Solo puntos sin revisar
      </label>

      <div className="space-y-3">
        {lista.length === 0 && <p className="text-sm text-ok">✓ Todo revisado en {actual.nombre}.</p>}
        {lista.map((p) => <Punto key={p.codigo} punto={p} onSave={guardarPunto(p.codigo)} onPhotos={subirFotos(p.codigo)} onDeletePhoto={borrarFoto(p.codigo)} />)}
      </div>

      <div className="space-y-2 pt-2">
        {siguiente && (
          <button onClick={() => { setCat(siguiente); window.scrollTo({ top: 0 }); }} className="w-full rounded-xl bg-accent py-3 font-semibold">
            Siguiente: {porCat[siguiente].nombre} →
          </button>
        )}
        {hechos > 0 && <button onClick={onInforme} className="w-full rounded-xl py-3 text-blue-300 ring-1 ring-accent/40">Ver informe</button>}
        {det.estado === "en_curso" && <button onClick={() => cambiarEstado("en_qc", true)} className="w-full rounded-xl bg-warn/20 py-3 text-warn ring-1 ring-warn/40">Enviar a QC (autorrevisión)</button>}
        {det.estado === "en_qc" && (
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => cambiarEstado("en_curso")} className="rounded-xl py-3 text-slate-300 ring-1 ring-white/15">Volver a en curso</button>
            <button onClick={() => cambiarEstado("finalizada", true)} className="rounded-xl bg-ok py-3 font-semibold text-navy-950">Finalizar revisión</button>
          </div>
        )}
        {det.estado === "finalizada" && <button onClick={() => cambiarEstado("en_curso")} className="w-full rounded-xl py-3 text-slate-300 ring-1 ring-white/15">Reabrir revisión</button>}
        <button onClick={eliminar} className="w-full py-2 text-sm text-slate-500 hover:text-bad">Eliminar revisión</button>
      </div>
    </div>
  );
}

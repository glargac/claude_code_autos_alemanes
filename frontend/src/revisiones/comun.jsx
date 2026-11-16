export const ESTADOS_PUNTO = {
  ok: { label: "Correcto", activo: "bg-ok text-navy-950", punto: "bg-ok" },
  aviso: { label: "Advertencia", activo: "bg-warn text-navy-950", punto: "bg-warn" },
  incidencia: { label: "Incidencia", activo: "bg-bad text-white", punto: "bg-bad" },
};

export const ESTADOS_REVISION = {
  en_curso: { label: "EN CURSO", estilo: "bg-accent/20 text-blue-300 ring-accent/40" },
  en_qc: { label: "EN QC", estilo: "bg-warn/15 text-warn ring-warn/40" },
  finalizada: { label: "FINALIZADA", estilo: "bg-ok/15 text-ok ring-ok/40" },
};

export const nombreCoche = (c) => (c ? `${c.marke} ${c.modell}` : "Coche eliminado");

export function Barra({ pct, className = "" }) {
  return (
    <div className={`h-2 overflow-hidden rounded-full bg-navy-950 ${className}`}>
      <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%` }} />
    </div>
  );
}

export function Foto({ src, className = "" }) {
  return src ? (
    <img src={src} alt="" loading="lazy" className={`object-cover ${className}`} />
  ) : (
    <div className={`flex items-center justify-center bg-navy-950 text-2xl text-slate-600 ${className}`}>🚗</div>
  );
}

export const Insignia = ({ estado }) => (
  <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1 ${ESTADOS_REVISION[estado].estilo}`}>{ESTADOS_REVISION[estado].label}</span>
);

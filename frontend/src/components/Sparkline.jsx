import { useId, useState } from 'react'
import { useResortes, useResorte, useCuenta, decimalesDe, curva } from '../efectos/graficos.js'
import '../efectos/graficos.css'

export function Sparkline({ data, color = "var(--traffic)", height = 32, width = 100, fill = true }) {
  const gid = "sg-" + useId().replace(/:/g, "");   // id del degradado: único y estable entre renders
  if (!data || data.length < 2) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const pad = 2;
  const stepX = (width - pad * 2) / (data.length - 1);
  const pts = data.map((v, i) => [pad + i * stepX, height - pad - ((v - min) / span) * (height - pad * 2)]);
  const path = pts.reduce((acc, p, i, arr) => {
    if (i === 0) return `M ${p[0]} ${p[1]}`;
    const prev = arr[i - 1];
    const cpx = (prev[0] + p[0]) / 2;
    return `${acc} C ${cpx} ${prev[1]} ${cpx} ${p[1]} ${p[0]} ${p[1]}`;
  }, "");
  const area = `${path} L ${width - pad} ${height - pad} L ${pad} ${height - pad} Z`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.16" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${gid})`} />}
      <path d={path} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.5" fill={color} />
    </svg>
  );
}

// Chispa de las tarjetas KPI (de «Pulso» · Moxen): se traza de izquierda a
// derecha al llegar los datos, los puntos morfan con resorte si cambian, la
// punta late y, con el cursor, cada punto da su valor en un globo.
export function Chispa({ data, labels, unidad = "", color = "var(--traffic)", height = 40, width = 96 }) {
  const id = useId().replace(/:/g, "");
  const [hov, setHov] = useState(null);
  const vals = useResortes(data || [], { k: 150, c: 17 });
  const traza = useResorte(data && data.length > 1 ? 1 : 0, { k: 26, c: 9.6 });
  if (!data || data.length < 2) return null;
  const min = Math.min(...vals), max = Math.max(...vals), span = max - min || 1, pad = 3;
  const stepX = (width - pad * 2) / (vals.length - 1);
  const pts = vals.map((v, i) => [pad + i * stepX, height - pad - ((v - min) / span) * (height - pad * 2)]);
  const d = curva(pts);
  const ult = pts[pts.length - 1];
  const mueve = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left) / r.width * width - pad) / stepX);
    setHov(Math.max(0, Math.min(data.length - 1, i)));
  };
  const dec = Math.max(...data.map(decimalesDe));
  const h = hov != null ? pts[hov] : null;
  return (
    <div className="gr-lienzo" style={{ width, height }}>
      <svg className="gr-chispa" width={width} height={height} viewBox={`0 0 ${width} ${height}`}
        onPointerMove={mueve} onPointerLeave={() => setHov(null)} aria-hidden="true">
        <defs>
          <linearGradient id={`${id}-g`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.22" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
          <clipPath id={`${id}-c`}><rect x="-2" y="-6" width={(width + 4) * traza} height={height + 12} /></clipPath>
        </defs>
        <g clipPath={`url(#${id}-c)`}>
          <path d={`${d} L ${ult[0]} ${height} L ${pad} ${height} Z`} fill={`url(#${id}-g)`} />
          <path className="gr-trazo" d={d} stroke={color} />
        </g>
        {h && <line className="gr-guia" x1={h[0]} x2={h[0]} y1={0} y2={height} />}
        {traza > .98 && <circle className="gr-punta-onda" cx={ult[0]} cy={ult[1]} r="2.6" stroke={color} />}
        <circle cx={ult[0]} cy={ult[1]} r="2.6" fill={color} opacity={Math.min(1, traza)} />
        {h && <circle cx={h[0]} cy={h[1]} r="3" fill="var(--bg-2)" stroke={color} strokeWidth="1.6" />}
      </svg>
      <div className={`gr-globo${h ? " is-visible" : ""}`}
        style={h ? { left: h[0], top: h[1] } : { left: ult[0], top: ult[1] }}>
        {hov != null && <>
          {labels?.[hov] && <small>{labels[hov]}</small>}
          {data[hov].toLocaleString("es-AR", { maximumFractionDigits: dec })}{unidad && ` ${unidad}`}
        </>}
      </div>
    </div>
  );
}

export function RadialGauge({ value, size = 32, stroke = 3, color = "var(--brand)", track = "var(--bg-4)" }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block", flexShrink: 0, transform: "rotate(-90deg)" }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} strokeLinecap="round" />
    </svg>
  );
}

export function KpiCard({
  label, value, unit, delta,
  trend = "neutral", spark, sparkLabels, sparkUnidad, color = "var(--traffic)",
  Ico, iconClass = "",
}) {
  const cifra = useCuenta(value, decimalesDe(value));
  const trendColor =
    trend === "up"   ? "var(--pos-soft)"   :
    trend === "down" ? "var(--alert-soft)" :
                       "var(--fg-3)";
  const arrow = trend === "up" ? "↑" : trend === "down" ? "↓" : "—";

  return (
    <div className="kpi-card">

      <div className="kpi-card-head">
        <span className="kpi-card-label">{label}</span>
        {Ico && (
          <span className={`kpi-card-icon${iconClass ? ` ${iconClass}` : ""}`}>
            <Ico />
          </span>
        )}
      </div>

      <div className="kpi-card-body">
        <div className="kpi-card-value-row">
          <span className="kpi-card-value">{cifra}</span>
          {unit && <span className="kpi-card-unit">{unit}</span>}
        </div>
        <Chispa data={spark} labels={sparkLabels} unidad={sparkUnidad} color={color} height={40} width={96} />
      </div>

      {delta != null && (
        <div className="kpi-card-foot">
          <span className="mono" style={{ color: trendColor, fontSize: 15, lineHeight: 1 }}>{arrow}</span>
          <span className="kpi-card-delta mono">{delta}</span>
        </div>
      )}

    </div>
  );
}

// ── Grilla de métricas — mismo estilo "stat tile" que Reportes 2.0 ────────
// (ícono en círculo + etiqueta + valor grande, en tarjeta de vidrio; ver
// .stat-tile en index.css). Antes era una barra tipo ticker financiero con
// separadores verticales; unificado al mismo lenguaje que el resto de la
// app en vez de mantener un tercer estilo de métrica solo acá.
export function StatTileRow({ items }) {
  return (
    <div className="stat-tile-row">
      {items.map((it, i) => <StatTile key={i} {...it} />)}
    </div>
  );
}

// Estado operativo EN VIVO (no es una metrica calculada): tarjeta compacta que va dentro de la barra de
// Operaciones, junto a "Actualizar datos" y los filtros. 'tone' pinta el punto: live (verde), alert, idle.
export function LiveTile({ label, value, unit, sub, Ico, tone = "idle" }) {
  return (
    <div className={`live-tile ${tone}`}>
      <span className="live-tile-dot" />
      {Ico && <Ico className="live-tile-ico" style={{ width: 14, height: 14 }} />}
      <span className="live-tile-val">{value}</span>
      <span className="live-tile-text">
        <span className="live-tile-lbl">{label}{unit && <span className="live-tile-unit"> {unit}</span>}</span>
        {sub && <span className="live-tile-sub">{sub}</span>}
      </span>
    </div>
  );
}

export function StatTile({ label, value, unit, trend = "flat", delta, sub, Ico }) {
  const arrow = trend === "up" ? "▲" : trend === "down" ? "▼" : "—";
  return (
    <div className="stat-tile">
      <span className="stat-tile-ico">{Ico && <Ico style={{ width: 15, height: 15 }} />}</span>
      <div className="stat-tile-body">
        <div className="stat-tile-lbl">{label}</div>
        <div className="stat-tile-valrow">
          <span className="stat-tile-val">{value}</span>
          {unit && <span className="stat-tile-unit">{unit}</span>}
          {delta != null && <span className={`stat-tile-trend ${trend}`}>{arrow} {delta}</span>}
        </div>
        {sub && <div className="stat-tile-sub">{sub}</div>}
      </div>
    </div>
  );
}

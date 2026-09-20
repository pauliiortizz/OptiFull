export function Sparkline({ data, color = "var(--traffic)", height = 32, width = 100, fill = true }) {
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
  const gid = "sg-" + Math.random().toString(36).slice(2, 7);
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
  trend = "neutral", spark, color = "var(--traffic)",
  Ico, iconClass = "",
}) {
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
          <span className="kpi-card-value">{value}</span>
          {unit && <span className="kpi-card-unit">{unit}</span>}
        </div>
        <Sparkline data={spark} color={color} height={38} width={88} />
      </div>

      <div className="kpi-card-foot">
        <span className="mono" style={{ color: trendColor, fontSize: 15, lineHeight: 1 }}>{arrow}</span>
        <span className="kpi-card-delta mono">{delta}</span>
      </div>

    </div>
  );
}

// ── KPI ticker — barra horizontal unificada (tipo ticker financiero) ──────
export function KpiTicker({ items }) {
  return (
    <div className="kpi-ticker">
      {items.map((it, i) => <KpiTickerItem key={i} {...it} />)}
    </div>
  );
}

export function KpiTickerItem({ label, value, unit, trend = "flat", delta, sub, Ico }) {
  const arrow = trend === "up" ? "▲" : trend === "down" ? "▼" : "—";
  return (
    <div className="kpi-ticker-item">
      <div className="kpi-ticker-label">{Ico && <Ico style={{ width: 11, height: 11 }} />}{label}</div>
      <div className="kpi-ticker-row">
        <span className="kpi-ticker-value">{value}</span>
        {unit && <span className="kpi-ticker-unit">{unit}</span>}
        {delta != null && (
          <span className={`kpi-ticker-trend ${trend}`}>{arrow} {delta}</span>
        )}
      </div>
      {sub && <div className="kpi-ticker-sub">{sub}</div>}
    </div>
  );
}

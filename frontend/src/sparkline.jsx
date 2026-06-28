// Sparkline component — smooth area path
function Sparkline({ data, color = "var(--brand-soft)", height = 32, width = 120, fill = true }) {
  if (!data || data.length === 0) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const pad = 2;
  const stepX = (width - pad * 2) / (data.length - 1);
  const pts = data.map((v, i) => [pad + i * stepX, height - pad - ((v - min) / span) * (height - pad * 2)]);
  // Catmull–Rom → bezier for smooth curve
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
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${gid})`} />}
      <path d={path} stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.5" fill={color} />
    </svg>
  );
}

function KpiCard({ label, value, unit, delta, trend = "up", spark, color = "var(--brand-soft)", Ico, iconClass = "" }) {
  const deltaCls = trend === "up" ? "up" : trend === "down" ? "down" : "neutral";
  const arrow = trend === "up" ? "↑" : trend === "down" ? "↓" : "→";
  return (
    <div className="panel kpi">
      <div className="kpi-head">
        <div className="kpi-label">{label}</div>
        <div className={`kpi-ico ${iconClass}`}><Ico /></div>
      </div>
      <div>
        <span className="kpi-value">{value}</span>
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
      <div className="kpi-foot">
        <div className={`kpi-delta ${deltaCls}`}>
          <span>{arrow}</span>
          <span className="mono">{delta}</span>
        </div>
        <div className="kpi-spark">
          <Sparkline data={spark} color={color} />
        </div>
      </div>
    </div>
  );
}

window.Sparkline = Sparkline;
window.KpiCard = KpiCard;

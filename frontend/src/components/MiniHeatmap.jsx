// Misma escala termica que FloorPlan.jsx (ver index.css --heat-*) -- antes
// este componente tenia su propia terna de hex ligeramente distinta, lo que
// hacia que el heatmap de la Consola Espacial y el de esta miniatura no
// coincidieran pixel a pixel en el mismo dato.
function heatColor(w) {
  if (w < 0.33) return "var(--heat-cold)";
  if (w < 0.66) return "var(--heat-mid)";
  return "var(--heat-hot)";
}

export function MiniHeatmap({ intensity = 1 }) {
  const W = 320, H = 200;
  const hotspots = [
    { x: 50,  y: 100, r: 38, w: 0.95 },
    { x: 110, y: 60,  r: 32, w: 0.75 },
    { x: 110, y: 140, r: 30, w: 0.55 },
    { x: 180, y: 80,  r: 34, w: 0.85 },
    { x: 180, y: 150, r: 28, w: 0.45 },
    { x: 260, y: 100, r: 42, w: 1.0  },
    { x: 260, y: 160, r: 22, w: 0.30 },
  ];

  return (
    <div className="heat-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" preserveAspectRatio="none"
        style={{ display: "block" }}>
        <defs>
          {hotspots.map((h, i) => (
            <radialGradient key={i} id={`hs-${i}`} cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor={heatColor(h.w * intensity)} stopOpacity={Math.min(0.85, 0.55 + h.w * 0.4)} />
              <stop offset="60%" stopColor={heatColor(h.w * intensity * 0.5)} stopOpacity={0.25} />
              <stop offset="100%" stopColor={heatColor(h.w * intensity * 0.3)} stopOpacity="0" />
            </radialGradient>
          ))}
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M20 0H0V20" stroke="rgba(255,255,255,0.025)" fill="none" />
          </pattern>
        </defs>

        <rect width={W} height={H} fill="#0e1729" />
        <rect width={W} height={H} fill="url(#grid)" />

        <g stroke="rgba(140,165,210,0.28)" strokeWidth="1" fill="rgba(140,165,210,0.05)">
          <rect x="14" y="14" width={W - 28} height={H - 28} rx="3" fill="none" strokeWidth="1.2" />
          <rect x="12" y="80" width="4" height="40" fill="#0e1729" stroke="none" />
          <rect x="90" y="40" width="42" height="14" rx="1.5" />
          <rect x="90" y="58" width="42" height="14" rx="1.5" />
          <rect x="90" y="130" width="42" height="14" rx="1.5" />
          <rect x="90" y="148" width="42" height="14" rx="1.5" />
          <rect x="158" y="40" width="50" height="22" rx="2" />
          <rect x="158" y="138" width="50" height="22" rx="2" />
          <rect x="232" y="78" width="62" height="12" rx="1.5" />
          <rect x="232" y="110" width="62" height="12" rx="1.5" />
        </g>

        <g style={{ mixBlendMode: "screen" }}>
          {hotspots.map((h, i) => (
            <circle key={i} cx={h.x} cy={h.y} r={h.r * 1.4} fill={`url(#hs-${i})`} />
          ))}
        </g>

        <g fontFamily="var(--font-metric)" fontSize="8" fill="rgba(220,230,250,0.55)" letterSpacing="0.05em">
          <text x="20" y="105">ENT</text>
          <text x="94" y="100" fontSize="8">GÓNDOLAS</text>
          <text x="166" y="76">CAFÉ</text>
          <text x="162" y="170">HELADERA</text>
          <text x="246" y="100" fontSize="8">CAJAS</text>
        </g>

        {[[40,30],[160,30],[280,30],[40,180],[160,180],[280,180]].map(([cx,cy], i) => (
          <g key={i} transform={`translate(${cx},${cy})`}>
            <circle r="3" fill="var(--bg-1)" stroke="var(--pos-soft)" strokeWidth="1" />
            <circle r="1" fill="var(--pos-soft)" />
          </g>
        ))}

        {[[58,95],[62,108],[112,68],[180,82],[260,100],[256,110],[178,148]].map(([cx,cy],i) => (
          <g key={i}>
            <circle cx={cx} cy={cy} r="2.5" fill="#fff" opacity=".9" />
            <circle cx={cx} cy={cy} r="5" fill="#fff" opacity=".15">
              <animate attributeName="r" values="2.5;6;2.5" dur={`${1.6 + (i%3)*0.3}s`} repeatCount="indefinite" />
              <animate attributeName="opacity" values=".4;0;.4" dur={`${1.6 + (i%3)*0.3}s`} repeatCount="indefinite" />
            </circle>
          </g>
        ))}
      </svg>
    </div>
  );
}

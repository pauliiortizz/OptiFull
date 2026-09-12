import { useState, useEffect, useRef } from 'react'
import {
  IcoUsers, IcoClock, IcoTrend, IcoHeat, IcoCam,
  IcoStock, IcoReport, IcoDown, IcoExpand, IcoSpinner,
} from '../components/Icons'
import { Sparkline } from '../components/Sparkline'
import { MiniHeatmap } from '../components/MiniHeatmap'
import { useToast } from '../components/Toast'
import { useHeatmapData } from './PagesHeatmapCameras'

// ── Static reference data ─────────────────────────────────────────────────
const WEEK_CURRENT  = [312, 287, 341, 398, 422, 465, 390];
const WEEK_PREVIOUS = [295, 310, 318, 371, 408, 441, 375];
const DAY_LABELS    = ["LUN","MAR","MIÉ","JUE","VIE","SÁB","DOM"];
const WEEKLY_SPARK  = [295, 312, 287, 341, 398, 422, 465];
const DWELL_SPARK   = [18, 22, 19, 24, 21, 20, 23];
const OCC_SPARK     = [62, 71, 68, 74, 78, 82, 79];

const CAMERAS = [
  { id: 1, label: "CAM-01", zone: "Entrada"       },
  { id: 2, label: "CAM-02", zone: "Góndolas"      },
  { id: 3, label: "CAM-03", zone: "Caja — frente" },
  { id: 4, label: "CAM-04", zone: "Caja — lateral"},
];

// ── Trajectory paths (simulated store flow) ───────────────────────────────
// viewBox 420 × 270 — entrance at top, gondola rows mid, checkout at bottom
const TRAJ = [
  // high-frequency main paths (entrance → checkout)
  { d:"M 55 12 C 60 70 75 110 90 150 C 100 180 95 230 88 258",   op:.5  },
  { d:"M 90 12 C 100 75 125 112 140 150 C 152 180 150 228 142 258", op:.45 },
  { d:"M 135 12 C 148 78 168 115 178 150 C 188 180 185 228 178 258", op:.4  },
  { d:"M 182 12 C 188 78 202 115 210 150 C 218 180 216 228 212 258", op:.5  },
  { d:"M 235 12 C 232 75 238 110 242 150 C 246 180 244 228 240 258", op:.35 },
  { d:"M 285 12 C 278 75 272 108 268 150 C 265 180 268 228 270 258", op:.4  },
  { d:"M 335 12 C 322 75 312 108 306 150 C 300 180 302 228 305 258", op:.35 },
  { d:"M 375 12 C 358 75 348 108 342 148 C 338 178 340 228 344 258", op:.45 },
  // cross-gondola browsing (horizontal)
  { d:"M 55 82 C 120 78 220 82 305 80 C 350 78 385 82 410 80",   op:.22 },
  { d:"M 55 138 C 130 132 235 138 315 136 C 360 135 390 138 410 138", op:.18 },
  { d:"M 410 185 C 320 188 225 183 150 185 C 100 187 60 185 28 185", op:.18 },
  // quick browsing paths (partial loops)
  { d:"M 175 12 C 178 60 195 90 185 120 C 175 145 155 148 155 118 C 155 90 168 70 175 12", op:.12 },
  { d:"M 260 12 C 255 60 250 90 248 120 C 246 148 260 152 268 130 C 280 100 272 65 260 12", op:.12 },
];

// ── SVG store floor plan with trajectories ───────────────────────────────
function TrajectoryCanvas({ showArrows }) {
  return (
    <svg
      viewBox="0 0 420 270"
      preserveAspectRatio="xMidYMid meet"
      style={{ width:"100%", height:"100%", background:"#0b0d13", display:"block" }}
    >
      <defs>
        <marker id="arr" markerWidth="5" markerHeight="5" refX="3" refY="2.5" orient="auto">
          <polygon points="0,1 4,2.5 0,4" fill="#3b82f6" opacity="0.7" />
        </marker>
        <linearGradient id="tg1" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.08" />
          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Gondola rows */}
      {[68, 122, 172, 218].map(y => (
        <g key={y}>
          <rect x={28} y={y} width={368} height={22} rx={1}
            fill="#0d1016" stroke="#1e2230" strokeWidth={0.5} />
          {Array.from({length:8},(_,i) => (
            <rect key={i} x={28 + i * 46} y={y + 4} width={38} height={14} rx={0}
              fill="#111520" stroke="none" />
          ))}
        </g>
      ))}

      {/* Checkout counters */}
      {[35, 128, 222, 315].map(x => (
        <rect key={x} x={x} y={248} width={72} height={16} rx={1}
          fill="#0d1016" stroke="#1e2230" strokeWidth={0.5} />
      ))}

      {/* Density overlays */}
      <ellipse cx={192} cy={148} rx={80} ry={28} fill="#d97706" fillOpacity={0.05} />
      <ellipse cx={110} cy={82} rx={55} ry={22} fill="#3b82f6" fillOpacity={0.05} />
      <ellipse cx={200} cy={254} rx={100} ry={12} fill="#22c55e" fillOpacity={0.05} />

      {/* Entry / exit labels */}
      <text x={210} y={10} fill="#3d4f6a" fontSize={8} textAnchor="middle"
        fontFamily="'JetBrains Mono',monospace" letterSpacing="2">ENTRADA</text>
      <line x1={28} y1={15} x2={392} y2={15} stroke="#1e2230" strokeWidth={0.5} strokeDasharray="4 4" />
      <text x={210} y={268} fill="#3d4f6a" fontSize={8} textAnchor="middle"
        fontFamily="'JetBrains Mono',monospace" letterSpacing="2">CAJAS</text>

      {/* Trajectory paths */}
      {TRAJ.map((p, i) => (
        <path key={i} d={p.d} stroke="#3b82f6" strokeWidth={1.2}
          strokeOpacity={p.op} fill="none" strokeLinecap="round"
          markerMid={showArrows ? "url(#arr)" : undefined} />
      ))}

      {/* Zone indicator dots */}
      <circle cx={110} cy={82} r={3} fill="#3b82f6" fillOpacity={0.5} />
      <circle cx={192} cy={148} r={3} fill="#d97706" fillOpacity={0.7} />
      <circle cx={200} cy={254} r={3} fill="#22c55e" fillOpacity={0.7} />
    </svg>
  );
}

// ── Weekly trend chart ────────────────────────────────────────────────────
function WeeklyTrendChart() {
  const W = 600, H = 130;
  const P = { t:16, r:20, b:28, l:44 };
  const cw = W - P.l - P.r, ch = H - P.t - P.b;

  const allV = [...WEEK_CURRENT, ...WEEK_PREVIOUS];
  const maxV = Math.max(...allV) * 1.1;
  const minV = Math.min(...allV) * 0.88;

  const xi = i  => P.l + (i / (DAY_LABELS.length - 1)) * cw;
  const yv = v  => P.t + ch - ((v - minV) / (maxV - minV)) * ch;

  const line = data =>
    data.map((v,i) => `${i===0?"M":"L"} ${xi(i).toFixed(1)} ${yv(v).toFixed(1)}`).join(" ");

  const area = data => {
    const pts = data.map((v,i) => `${i===0?"M":"L"} ${xi(i).toFixed(1)} ${yv(v).toFixed(1)}`).join(" ");
    return `${pts} L ${xi(data.length-1)} ${P.t+ch} L ${xi(0)} ${P.t+ch} Z`;
  };

  const yTicks = [0, 0.5, 1].map(t => minV + t * (maxV - minV));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width:"100%", height:"100%", display:"block" }}>
      <defs>
        <linearGradient id="wfg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.12" />
          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {yTicks.map((v,i) => (
        <g key={i}>
          <line x1={P.l} y1={yv(v)} x2={W-P.r} y2={yv(v)}
            stroke="#1e293b" strokeWidth={1} strokeDasharray="3 3" />
          <text x={P.l-6} y={yv(v)+3} fill="#3d4f6a" fontSize={8}
            textAnchor="end" fontFamily="'JetBrains Mono',monospace">
            {Math.round(v)}
          </text>
        </g>
      ))}

      {/* Previous week — dashed gray */}
      <path d={line(WEEK_PREVIOUS)} stroke="#1e2230" strokeWidth={1.5}
        fill="none" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="4 3" />

      {/* Current week — fill + line */}
      <path d={area(WEEK_CURRENT)} fill="url(#wfg)" />
      <path d={line(WEEK_CURRENT)} stroke="#3b82f6" strokeWidth={1.5}
        fill="none" strokeLinecap="round" strokeLinejoin="round" />

      {/* Data points */}
      {WEEK_CURRENT.map((v,i) => (
        <circle key={i} cx={xi(i)} cy={yv(v)} r={2.5} fill="#3b82f6" />
      ))}

      {/* X axis */}
      {DAY_LABELS.map((l,i) => (
        <text key={i} x={xi(i)} y={H-6} fill="#64748b" fontSize={8.5}
          textAnchor="middle" fontFamily="'JetBrains Mono',monospace">
          {l}
        </text>
      ))}
    </svg>
  );
}

// ── Module access card ────────────────────────────────────────────────────
function ModuleCard({ Icon, title, desc, badge, badgeColor = "#64748b", onClick }) {
  return (
    <button className="module-card" onClick={onClick}>
      <div className="module-card-icon"><Icon /></div>
      <div className="module-card-body">
        <div className="module-card-title">{title}</div>
        <div className="module-card-desc">{desc}</div>
      </div>
      <div className="module-card-end">
        <span className="module-card-badge"
          style={{ color: badgeColor, background: badgeColor + "18", border: `1px solid ${badgeColor}35` }}>
          {badge}
        </span>
        <span className="module-card-arrow">→</span>
      </div>
    </button>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────
function useApiStats() {
  const [stats, setStats]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick]       = useState(0);
  useEffect(() => {
    setLoading(true);
    fetch('/api/stats')
      .then(r => r.json())
      .then(d => { setStats(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [tick]);
  return { stats, loading, refresh: () => setTick(t => t+1) };
}

// ── Helpers ───────────────────────────────────────────────────────────────
function fmtDwell(min) {
  if (!min && min !== 0) return "—";
  const m = Math.floor(Number(min));
  const s = Math.round((Number(min) - m) * 60);
  return `${m}m ${s.toString().padStart(2,"0")}s`;
}

// ── DashboardPage ─────────────────────────────────────────────────────────
export function DashboardPage({ onNavigate }) {
  const toast = useToast();
  const { stats, loading, refresh } = useApiStats();
  const { data: heatmapData }       = useHeatmapData();

  const [camOpen, setCamOpen]       = useState(false);
  const [selectedCam, setSelectedCam] = useState(null);
  const [heatOp, setHeatOp]         = useState(75);
  const [showArrows, setShowArrows] = useState(true);
  const camRef = useRef(null);

  useEffect(() => {
    const h = e => { if (camRef.current && !camRef.current.contains(e.target)) setCamOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const footTraffic = stats?.personas_unicas ?? null;
  const dwellMin    = stats?.permanencia_promedio_min ?? null;
  const deltaFt     = footTraffic != null
    ? Math.round(((footTraffic - WEEK_PREVIOUS[4]) / WEEK_PREVIOUS[4]) * 100)
    : null;

  return (
    <main className="content">

      {/* ── Page head ── */}
      <div className="page-head">
        <div>
          <h1>Vision Ops Overview</h1>
          <p>Strumia · Mendoza — grabaciones analizadas · tiempo real inactivo</p>
        </div>
        <div style={{ display:"flex", gap:6, alignItems:"center" }}>
          <button className="btn-sec" onClick={refresh} disabled={loading}>
            <IcoSpinner style={{ width:11, height:11, animation: loading ? "spin 1s linear infinite" : "none" }} />
            {loading ? "Loading…" : "Refresh"}
          </button>
          <div className="range-tabs">
            {[["hoy","TODAY"],["7d","7D"],["30d","30D"]].map(([k,l]) => (
              <button key={k} className={k==="hoy"?"on":""}
                onClick={() => k!=="hoy" && toast(`Rango ${l} — próximamente`, {kind:"info"})}>
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 1: KPI strip (4 cols) ── */}
      <div className="dash-kpi-row">

        {/* 1 — Foot Traffic */}
        <div className="kpi-v2">
          <div className="kpi-v2-head">
            <span className="kpi-v2-label">FOOT TRAFFIC</span>
            <IcoUsers style={{ width:11, height:11, color:"var(--fg-4)" }} />
          </div>
          <div className="kpi-v2-body">
            <span className="kpi-v2-val">{loading ? "—" : (footTraffic ?? "N/A")}</span>
            <span className="kpi-v2-unit">visitors</span>
          </div>
          <div className="kpi-v2-foot">
            <span className="kpi-v2-delta" style={{ color: deltaFt != null ? (deltaFt >= 0 ? "var(--pos-soft)" : "var(--alert-soft)") : "var(--fg-4)" }}>
              {deltaFt != null ? `${deltaFt >= 0 ? "↑" : "↓"} ${Math.abs(deltaFt)}%` : "—"} vs prev week
            </span>
            <Sparkline data={WEEKLY_SPARK} color="var(--brand-soft)" height={26} width={70} fill={false} />
          </div>
        </div>

        {/* 2 — Dwell Time */}
        <div className="kpi-v2">
          <div className="kpi-v2-head">
            <span className="kpi-v2-label">DWELL TIME</span>
            <IcoClock style={{ width:11, height:11, color:"var(--fg-4)" }} />
          </div>
          <div className="kpi-v2-body">
            <span className="kpi-v2-val kpi-v2-val--sm">{loading ? "—" : fmtDwell(dwellMin)}</span>
          </div>
          <div className="kpi-v2-foot">
            <span className="kpi-v2-delta">avg. per visitor session</span>
            <Sparkline data={DWELL_SPARK} color="var(--pos-soft)" height={26} width={70} fill={false} />
          </div>
        </div>

        {/* 3 — Peak Occupancy */}
        <div className="kpi-v2">
          <div className="kpi-v2-head">
            <span className="kpi-v2-label">PEAK OCCUPANCY</span>
            <span style={{ width:7, height:7, borderRadius:"50%", background:"var(--warn)", display:"inline-block", flexShrink:0 }} />
          </div>
          <div className="kpi-v2-body">
            <span className="kpi-v2-val">82</span>
            <span className="kpi-v2-unit">%</span>
          </div>
          <div style={{ height:2, background:"var(--bg-4)", borderRadius:1, marginBottom:2 }}>
            <div style={{ width:"82%", height:"100%", background:"var(--warn)", borderRadius:1, transition:"width .6s ease" }} />
          </div>
          <div className="kpi-v2-foot">
            <span className="kpi-v2-delta">Sáb 14:30 · cap. 55 pax</span>
            <Sparkline data={OCC_SPARK} color="var(--warn)" height={26} width={70} fill={false} />
          </div>
        </div>

        {/* 4 — Top Zone */}
        <div className="kpi-v2">
          <div className="kpi-v2-head">
            <span className="kpi-v2-label">TOP ZONE</span>
            <span className="kpi-v2-pill" style={{ color:"var(--alert-soft)", background:"rgba(239,68,68,.08)", borderColor:"rgba(239,68,68,.25)" }}>HOT</span>
          </div>
          <div style={{ flex:1, display:"flex", flexDirection:"column", justifyContent:"center", gap:1 }}>
            <span className="kpi-v2-zone">Sector Café</span>
            <span style={{ fontSize:10, color:"var(--fg-3)" }}>/ Zona Cajas</span>
          </div>
          <div className="kpi-v2-foot">
            <span className="kpi-v2-delta">28% dwell share · 7 conc.</span>
            <span className="kpi-v2-pill" style={{ color:"var(--pos-soft)", background:"rgba(34,197,94,.08)", borderColor:"rgba(34,197,94,.22)" }}>↑12%</span>
          </div>
        </div>

      </div>

      {/* ── Row 2: Spatial dual (fixed height) ── */}
      <div className="dash-spatial-row">

        {/* Left: Heatmap */}
        <div className="spatial-card">
          <div className="spatial-card-head">
            <div>
              <div className="spatial-card-title">
                <IcoHeat style={{ width:11, height:11 }} />
                DENSITY MAP
              </div>
              <div className="spatial-card-sub">Heatmap · ocupación por zona</div>
            </div>
            <div ref={camRef} style={{ position:"relative" }}>
              <button className="cam-sel-btn" onClick={() => setCamOpen(o => !o)}>
                <span className="mono" style={{ fontSize:10.5 }}>
                  {selectedCam ? `CAM-0${selectedCam}` : "All cams"}
                </span>
                <IcoDown style={{ width:10, height:10, color:"var(--fg-3)" }} />
              </button>
              {camOpen && (
                <div className="dropdown" style={{ right:0, left:"auto", minWidth:160 }}>
                  <div className="dd-head">Cámara</div>
                  <button className={`dd-item${selectedCam===null?" active":""}`}
                    onClick={() => { setSelectedCam(null); setCamOpen(false); }}>
                    <span style={{ flex:1, textAlign:"left" }}>Todas</span>
                  </button>
                  {CAMERAS.map(c => (
                    <button key={c.id} className={`dd-item${selectedCam===c.id?" active":""}`}
                      onClick={() => { setSelectedCam(c.id); setCamOpen(false); }}>
                      <span className="cam-chip live" style={{ fontSize:8.5 }}>
                        <span className="live-dot" />{c.label}
                      </span>
                      <span style={{ flex:1, textAlign:"left" }}>{c.zone}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="spatial-card-canvas">
            {heatmapData?.imagen_url ? (
              <img src={heatmapData.imagen_url} alt="Heatmap"
                style={{ width:"100%", height:"100%", objectFit:"cover", display:"block", opacity: heatOp/100 }} />
            ) : (
              <MiniHeatmap intensity={0.9} />
            )}
          </div>

          <div className="spatial-card-foot">
            <div style={{ display:"flex", alignItems:"center", gap:6 }}>
              <span className="kpi-v2-label">OPACITY</span>
              <input type="range" min={20} max={100} step={5} value={heatOp}
                onChange={e => setHeatOp(+e.target.value)}
                style={{ width:52, height:2, accentColor:"var(--brand)", cursor:"default" }} />
              <span className="mono" style={{ fontSize:9.5, color:"var(--fg-3)", width:24 }}>{heatOp}%</span>
            </div>
            <button className="spatial-card-action" onClick={() => onNavigate("heatmap")}>
              Inspección detallada de calor →
            </button>
          </div>
        </div>

        {/* Right: Flow vectors */}
        <div className="spatial-card">
          <div className="spatial-card-head">
            <div>
              <div className="spatial-card-title">
                <IcoTrend style={{ width:11, height:11 }} />
                FLOW VECTORS
              </div>
              <div className="spatial-card-sub">Trayectorias · recorridos detectados</div>
            </div>
            <div className="seg">
              <button className={showArrows?"on":""} onClick={() => setShowArrows(true)}>Vectores</button>
              <button className={!showArrows?"on":""} onClick={() => setShowArrows(false)}>Líneas</button>
            </div>
          </div>

          <div className="spatial-card-canvas">
            <TrajectoryCanvas showArrows={showArrows} />
          </div>

          <div className="spatial-card-foot">
            <div style={{ display:"flex", alignItems:"center", gap:10, fontSize:10, color:"var(--fg-3)" }}>
              <span style={{ display:"flex", alignItems:"center", gap:4 }}>
                <span style={{ width:14, height:1.5, background:"#3b82f6", display:"inline-block" }} />
                Flujo actual
              </span>
              <span style={{ display:"flex", alignItems:"center", gap:4 }}>
                <span style={{ width:7, height:7, borderRadius:"50%", background:"#d97706", display:"inline-block" }} />
                Alta densidad
              </span>
              <span style={{ display:"flex", alignItems:"center", gap:4 }}>
                <span style={{ width:7, height:7, borderRadius:"50%", background:"#22c55e", display:"inline-block" }} />
                Checkout
              </span>
            </div>
            <button className="spatial-card-action" onClick={() => onNavigate("tracking")}>
              Inspección detallada de flujo →
            </button>
          </div>
        </div>

      </div>

      {/* ── Row 3: Weekly trend chart ── */}
      <div className="panel" style={{ marginBottom:8 }}>
        <div className="panel-head">
          <div>
            <div className="panel-title">
              <IcoTrend style={{ width:11, height:11 }} />
              TRAFFIC TREND — WEEK OVER WEEK
            </div>
            <div style={{ marginTop:5, display:"flex", gap:14, alignItems:"center" }}>
              <span style={{ display:"flex", alignItems:"center", gap:5, fontSize:10, color:"var(--fg-3)" }}>
                <span style={{ width:14, height:1.5, background:"#3b82f6", display:"inline-block" }} />
                Esta semana
              </span>
              <span style={{ display:"flex", alignItems:"center", gap:5, fontSize:10, color:"var(--fg-3)" }}>
                <span style={{ width:14, height:1.5, background:"#1e2230", display:"inline-block", borderTop:"1px dashed #1e2230" }} />
                Semana anterior
              </span>
            </div>
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:8 }}>
            <span className="mono" style={{ fontSize:10, color:"var(--fg-3)" }}>
              02–08 Sep 2026
            </span>
            <button className="iconbtn" onClick={() => onNavigate("reports")}>
              <IcoExpand />
            </button>
          </div>
        </div>
        <div style={{ height:130 }}>
          <WeeklyTrendChart />
        </div>
      </div>

      {/* ── Row 4: Module access grid ── */}
      <div className="dash-module-row">
        <ModuleCard
          Icon={IcoStock}
          title="Auditoría de Permanencia en Góndolas"
          desc="ROI por zona de exhibición · dwell share"
          badge="ROI"
          badgeColor="#3b82f6"
          onClick={() => onNavigate("heatmap")}
        />
        <ModuleCard
          Icon={IcoClock}
          title="Embudos y Tasa de Retención en Cajas"
          desc="Conversión de paso → espera → pago"
          badge="CAJAS"
          badgeColor="#22c55e"
          onClick={() => onNavigate("tracking")}
        />
        <ModuleCard
          Icon={IcoCam}
          title="Monitoreo Multi-Cámara en Vivo"
          desc="4 feeds · estado de stream en tiempo real"
          badge="LIVE"
          badgeColor="#ef4444"
          onClick={() => onNavigate("cameras")}
        />
        <ModuleCard
          Icon={IcoReport}
          title="Reporte Ejecutivo de Tráfico Semanal"
          desc="Resumen ejecutivo · KPIs + alertas + tendencia"
          badge="PDF"
          badgeColor="#f59e0b"
          onClick={() => onNavigate("reports")}
        />
      </div>

    </main>
  );
}

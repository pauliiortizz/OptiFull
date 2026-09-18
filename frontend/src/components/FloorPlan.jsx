// ── Plano esquemático de tienda — heatmap / trayectorias / zonas ───────────
// Dibuja un layout arquitectónico simplificado (wireframe) y superpone,
// según el modo activo, el mapa de calor, los vectores de trayectoria o el
// resaltado de ROIs. Todo en SVG para mantenerlo nítido a cualquier escala.

const VB_W = 760, VB_H = 460;

// Zonas ROI del plano — coordenadas del polígono en el sistema del viewBox.
// 'tipoReal' mapea cada ROI del esquema visual al 'tipo' real de la tabla
// 'zonas' en Postgres (ver /reportes/permanencia-por-zona) -- el schema solo
// agrupa permanencia real en 3 categorías (caja / gondola / otro), así que
// Ingreso y Cafetería comparten el valor real de 'otro' (Salón/piso general).
// El numero mostrado sobre cada ROI en modo "zones" viene SIEMPRE de datos
// reales via la prop 'zonasReales' (ver DashboardPage) -- nunca hardcodeado.
export const STORE_ZONES = [
  {
    id: "ingreso", roi: "ROI-01", label: "Ingreso", filterKey: "entry",
    tipoReal: "otro", tint: "156,147,188", // lavanda pastel
    poly: [[280, 30], [450, 30], [450, 92], [280, 92]],
    labelAt: [365, 66],
  },
  {
    id: "gondolas", roi: "ROI-02", label: "Góndolas Centrales", filterKey: "aisles",
    tipoReal: "gondola", tint: "106,114,207", // periwinkle pastel
    poly: [[60, 112], [500, 112], [500, 338], [60, 338]],
    labelAt: [280, 128],
  },
  {
    id: "cajas", roi: "ROI-03", label: "Línea de Cajas", filterKey: "checkout",
    tipoReal: "caja", tint: "198,138,62", // apricot pastel
    poly: [[60, 356], [730, 356], [730, 430], [60, 430]],
    labelAt: [90, 374],
  },
  {
    id: "cafeteria", roi: "ROI-04", label: "Sector Cafetería", filterKey: "all",
    tipoReal: "otro", tint: "53,144,112", // sage pastel
    poly: [[540, 30], [730, 30], [730, 198], [540, 198]],
    labelAt: [618, 50],
  },
];

// Góndolas individuales — solo mobiliario para el dibujo del plano (posición
// en el viewBox). Sin métricas propias: el schema real no distingue góndolas
// individuales, solo el tipo de zona agregado (ver STORE_ZONES.tipoReal).
export const GONDOLA_AISLES = [
  { id: "g1", x: 95  },
  { id: "g2", x: 205 },
  { id: "g3", x: 315 },
  { id: "g4", x: 425 },
];

const HOTSPOTS = [
  { cx: 360, cy: 386, r: 100, w: 0.95 },
  { cx: 205, cy: 230, r: 66,  w: 0.62 },
  { cx: 315, cy: 230, r: 78,  w: 0.85 },
  { cx: 95,  cy: 230, r: 54,  w: 0.35 },
  { cx: 425, cy: 230, r: 54,  w: 0.4  },
  { cx: 365, cy: 68,  r: 48,  w: 0.4  },
  { cx: 618, cy: 108, r: 52,  w: 0.28 },
];

// Escala térmica compartida (ver index.css --heat-cold/--heat-mid/--heat-hot):
// azul frío desaturado -> ambar -> coral calido. Nunca un primario al 100% de
// saturacion -- el extremo "caliente" es coral, no rojo puro, para no
// confundirse visualmente con --alert (reservado a alertas reales).
function heatColor(w) {
  if (w < 0.33) return "var(--heat-cold)";
  if (w < 0.66) return "var(--heat-mid)";
  return "var(--heat-hot)";
}

const TRAJECTORIES = [
  { d: "M365,92 C365,110 205,110 205,150", w: 1.6, hot: false },
  { d: "M365,92 C365,115 315,115 315,150", w: 2.6, hot: true  },
  { d: "M365,92 C365,105 95,120 95,150",   w: 1.2, hot: false },
  { d: "M365,92 C365,118 425,118 425,150", w: 1.4, hot: false },
  { d: "M205,320 C205,345 300,345 340,366", w: 1.6, hot: false },
  { d: "M315,320 C315,348 340,348 350,366", w: 2.6, hot: true  },
  { d: "M95,320  C95,352 200,358 250,366",  w: 1.2, hot: false },
  { d: "M425,320 C425,350 470,355 480,366", w: 1.4, hot: false },
  { d: "M600,198 C600,280 520,330 480,362", w: 1.1, hot: false },
];

function polyToPoints(poly) {
  return poly.map((p) => p.join(",")).join(" ");
}
function polyCenter(poly) {
  const x = poly.reduce((s, p) => s + p[0], 0) / poly.length;
  const y = poly.reduce((s, p) => s + p[1], 0) / poly.length;
  return [x, y];
}

// 'zonasReales': mapa tipo -> {pct, promedio_min, visitantes}, tal cual lo
// entrega /reportes/permanencia-por-zona (ver useZonasPermanencia en App.jsx).
// null/undefined mientras carga -- el ROI muestra "—" en vez de inventar un
// numero, y nunca cae de nuevo a un valor hardcodeado.
export function FloorPlan({ mode = "heat", opacity = 80, roiFilter = "all", zonasReales = null }) {
  const heatOpacity = mode === "heat" ? opacity / 100 : 0;
  const vecOpacity  = mode === "vectors" ? Math.max(0.25, opacity / 100) : 0;
  const zoneEmph    = mode === "zones";

  return (
    <svg viewBox={`0 0 ${VB_W} ${VB_H}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet"
      style={{ display: "block" }}>
      <defs>
        <pattern id="fp-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0H0V20" fill="none" stroke="var(--line)" strokeOpacity="0.5" />
        </pattern>
        <marker id="fp-arrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L8,4 L0,8 Z" fill="var(--traffic)" />
        </marker>
        {/* Nucleo termico: color pleno hasta ~35% del radio (se lee como un
            nucleo naranja/rojo definido, no una mancha), luego una aura ambar
            que decae — antes los 3 stops arrancaban ya diluidos y el
            resultado era un borron tenue en vez de un foco de calor. */}
        {HOTSPOTS.map((h, i) => (
          <radialGradient key={i} id={`fp-hs-${i}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%"  stopColor={heatColor(h.w)} stopOpacity={Math.min(0.95, 0.62 + h.w * 0.33)} />
            <stop offset="35%" stopColor={heatColor(h.w)} stopOpacity={Math.min(0.75, 0.42 + h.w * 0.3)} />
            <stop offset="68%" stopColor={heatColor(h.w * 0.55)} stopOpacity="0.32" />
            <stop offset="100%" stopColor={heatColor(h.w * 0.25)} stopOpacity="0" />
          </radialGradient>
        ))}
      </defs>

      {/* Hoja de plano — fondo técnico con grilla */}
      <rect x="0" y="0" width={VB_W} height={VB_H} fill="var(--bg-3)" />
      <rect x="0" y="0" width={VB_W} height={VB_H} fill="url(#fp-grid)" />

      {/* Muro exterior — con hueco para el ingreso */}
      <g stroke="var(--plan-wall)" strokeWidth="1.8" fill="none">
        <line x1="30" y1="30" x2="280" y2="30" />
        <line x1="450" y1="30" x2="730" y2="30" />
        <line x1="730" y1="30" x2="730" y2="430" />
        <line x1="730" y1="430" x2="30" y2="430" />
        <line x1="30" y1="430" x2="30" y2="30" />
      </g>
      {/* Puerta — indicador de ingreso */}
      <g stroke="var(--fg-3)" strokeWidth="1.1" fill="none" strokeDasharray="1 0">
        <path d="M280,30 A 170 170 0 0 1 450,30" strokeDasharray="2 3" opacity="0.5" />
        <path d="M365,44 L358,56 M365,44 L372,56" strokeLinecap="round" opacity="0.7" />
      </g>

      {/* Mobiliario — góndolas. Borde nitido (slate-600) + relleno suave
          (slate-100) para que el mobiliario se lea como objeto solido, no
          como un bloque gris difuso. */}
      {GONDOLA_AISLES.map((g) => (
        <rect key={g.id} x={g.x} y="130" width="40" height="200" rx="1"
          fill="var(--plan-fill)" stroke="var(--plan-line)" strokeWidth="1.4" />
      ))}
      {GONDOLA_AISLES.map((g) => (
        <line key={g.id + "-ln"} x1={g.x + 20} y1="138" x2={g.x + 20} y2="322"
          stroke="var(--plan-line)" strokeWidth="1" strokeDasharray="3 4" opacity="0.5" />
      ))}

      {/* Mobiliario — línea de cajas */}
      <line x1="60" y1="360" x2="730" y2="360" stroke="var(--plan-line)" strokeWidth="1.4" />
      {[90, 225, 360, 495, 630].map((x, i) => (
        <rect key={i} x={x} y="366" width="56" height="34" rx="1"
          fill="var(--plan-fill)" stroke="var(--plan-line)" strokeWidth="1.4" />
      ))}

      {/* Mobiliario — mesas de cafetería */}
      {[[585, 80], [655, 80], [585, 150], [655, 150]].map(([cx, cy], i) => (
        <g key={i}>
          <circle cx={cx} cy={cy} r="11" fill="var(--plan-fill)" stroke="var(--plan-line)" strokeWidth="1.4" />
          <circle cx={cx} cy={cy} r="4" fill="none" stroke="var(--plan-line)" strokeWidth="1" opacity="0.55" />
        </g>
      ))}

      {/* ── Capa: mapa de calor ── */}
      {heatOpacity > 0 && (
        <g style={{ mixBlendMode: "multiply" }} opacity={heatOpacity}>
          {HOTSPOTS.map((h, i) => (
            <circle key={i} cx={h.cx} cy={h.cy} r={h.r} fill={`url(#fp-hs-${i})`} />
          ))}
        </g>
      )}

      {/* ── Capa: trayectorias ── */}
      {vecOpacity > 0 && (
        <g opacity={vecOpacity}>
          {TRAJECTORIES.map((tr, i) => (
            <path key={i} d={tr.d} fill="none"
              stroke={tr.hot ? "var(--brand)" : "var(--traffic)"}
              strokeWidth={tr.w} strokeLinecap="round" opacity={tr.hot ? 0.85 : 0.5}
              markerEnd="url(#fp-arrow)" />
          ))}
        </g>
      )}

      {/* ── Capa: ROIs — polígonos punteados + etiqueta técnica ── */}
      {STORE_ZONES.map((z) => {
        const dim = roiFilter !== "all" && z.filterKey !== roiFilter;
        const baseOp = zoneEmph ? 0.85 : dim ? 0.12 : 0.4;
        const fillOp = zoneEmph ? 0.1 : dim ? 0.02 : 0.045;
        return (
          <g key={z.id} opacity={dim && !zoneEmph ? 0.35 : 1}>
            <polygon points={polyToPoints(z.poly)}
              fill={`rgba(${z.tint},${fillOp})`}
              stroke={`rgba(${z.tint},${baseOp})`}
              strokeWidth={zoneEmph ? 1.6 : 1.1}
              strokeDasharray="5 4" />
            <g transform={`translate(${z.labelAt[0]},${z.labelAt[1]})`}>
              <rect x="-3" y="-11" width={z.roi.length * 5.6 + z.label.length * 5.4 + 20} height="16" rx="2"
                fill="var(--bg-2)" fillOpacity={zoneEmph ? 0.95 : 0.8} stroke="var(--line)" strokeWidth="1" />
              <text x="3" y="1" fontFamily="var(--font-metric)" fontSize="10" fontWeight="700"
                fill={`rgb(${z.tint})`} letterSpacing="0.03em">{z.roi}</text>
              <text x={z.roi.length * 5.6 + 9} y="1" fontFamily="var(--font-ui)" fontSize="10.5"
                fill="var(--fg-1)" letterSpacing="0.01em">{z.label.toUpperCase()}</text>
            </g>
            {zoneEmph && (() => {
              const real = zonasReales?.[z.tipoReal];
              return (
                <text x={polyCenter(z.poly)[0]} y={polyCenter(z.poly)[1]} textAnchor="middle"
                  fontFamily="var(--font-metric)" fontSize="23" fontWeight="600" fill={`rgb(${z.tint})`} opacity="0.85">
                  {real ? `${real.pct}%` : "—"}
                </text>
              );
            })()}
          </g>
        );
      })}
    </svg>
  );
}

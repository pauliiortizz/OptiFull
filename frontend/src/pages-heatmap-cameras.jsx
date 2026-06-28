// HEATMAP / TRACKING / STOCK / CAMERAS / SETTINGS pages

// ═════════════════════════════════════════════════════════════
// HEATMAP PAGE — full layout
// ═════════════════════════════════════════════════════════════
function HeatmapPage() {
  const toast = useToast();
  const [hour, setHour] = React.useState(18);
  const [intensity, setIntensity] = React.useState(1);
  const [layers, setLayers] = React.useState({ heat: true, paths: false, cams: true, people: true });

  return (
    <main className="content docs">
      <PageHeader
        title="Mapa de calor"
        subtitle="Análisis de circulación y densidad por zona — Sucursal Strumia"
        right={
          <>
            <div className="range-tabs">
              <button className="on">Hoy</button>
              <button>Ayer</button>
              <button>Promedio 7d</button>
            </div>
            <button className="btn-sec" onClick={() => toast("Exportando snapshot…")}>
              <IcoDownload style={{ marginRight: 6 }} />PNG
            </button>
          </>
        }
      />
      <WipBanner>
        Vista de planos detallados en progreso · base esquemática operativa, integración con plano CAD prevista para sep. 2026.
      </WipBanner>

      <div className="main-grid" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title">
              <span className="ico"><IcoHeat /></span>Densidad de circulación
              <span className="mono" style={{ marginLeft: 8, fontSize: 11, color: "var(--fg-3)" }}>
                · {hour.toString().padStart(2,"0")}:00 hs
              </span>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {Object.entries(layers).map(([k, v]) => (
                <button key={k} className={`chip-toggle ${v ? "on" : ""}`} onClick={() => setLayers({ ...layers, [k]: !v })}>
                  {({heat:"Heat", paths:"Trayectorias", cams:"Cámaras", people:"Personas"})[k]}
                </button>
              ))}
            </div>
          </div>
          <div style={{ position: "relative" }}>
            <div style={{ height: 420, borderRadius: 10, overflow: "hidden", border: "1px solid var(--line)" }}>
              <MiniHeatmap intensity={intensity} />
            </div>
            <div className="heat-legend" style={{ marginTop: 12 }}>
              <span>Baja</span>
              <div className="heat-bar" />
              <span>Alta</span>
            </div>
          </div>

          {/* Time slider */}
          <div style={{ marginTop: 18, padding: 14, background: "var(--bg-3)", borderRadius: 10, border: "1px solid var(--line)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: ".08em", fontWeight: 600 }}>
                Hora del día
              </div>
              <div className="mono" style={{ fontSize: 13, color: "var(--fg-0)", fontWeight: 500 }}>
                {hour.toString().padStart(2,"0")}:00 — {(hour+1).toString().padStart(2,"0")}:00
              </div>
            </div>
            <input type="range" min={6} max={22} value={hour} onChange={(e) => setHour(+e.target.value)}
              style={{ width: "100%", accentColor: "var(--brand-soft)" }} />
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10, color: "var(--fg-3)" }} className="mono">
              <span>06</span><span>10</span><span>14</span><span>18</span><span>22</span>
            </div>

            <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 11, color: "var(--fg-3)" }}>Intensidad</span>
              <input type="range" min={0.3} max={1.4} step={0.05} value={intensity}
                onChange={(e) => setIntensity(+e.target.value)}
                style={{ flex: 1, accentColor: "var(--brand-soft)" }} />
              <span className="mono" style={{ fontSize: 11, color: "var(--fg-1)", width: 32, textAlign: "right" }}>{intensity.toFixed(2)}</span>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="panel">
            <div className="panel-head">
              <div className="panel-title"><span className="ico"><IcoUsers /></span>Zonas más concurridas</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              {[
                { name: "Cajas",          pct: 32, color: "var(--alert-soft)", count: 178 },
                { name: "Cafetería",      pct: 28, color: "var(--alert-soft)", count: 156 },
                { name: "Góndolas centro",pct: 22, color: "var(--warn)",       count: 122 },
                { name: "Entrada",        pct: 18, color: "var(--brand-soft)", count: 100 },
                { name: "Heladera",       pct: 14, color: "var(--brand-soft)", count: 78  },
                { name: "Playa",          pct: 8,  color: "var(--brand-soft)", count: 44  },
              ].map(z => (
                <div key={z.name} style={{ padding: "8px 10px", background: "var(--bg-3)", borderRadius: 8, border: "1px solid var(--line)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 12, color: "var(--fg-0)", fontWeight: 500 }}>{z.name}</span>
                    <span className="mono" style={{ fontSize: 11, color: "var(--fg-2)" }}>{z.count} pers.</span>
                  </div>
                  <div style={{ height: 4, background: "var(--bg-1)", borderRadius: 99 }}>
                    <div style={{ width: `${z.pct*3}%`, height: "100%", background: z.color, borderRadius: 99 }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <div className="panel-title"><span className="ico"><IcoClock /></span>Permanencia media</div>
            </div>
            <div style={{ fontSize: 12, color: "var(--fg-2)", display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Cafetería</span><span className="mono" style={{ color: "var(--fg-0)" }}>3:48</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Góndolas</span><span className="mono" style={{ color: "var(--fg-0)" }}>2:24</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Cajas</span><span className="mono" style={{ color: "var(--warn)" }}>2:18</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Heladera</span><span className="mono" style={{ color: "var(--fg-0)" }}>1:36</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Total visita</span><span className="mono" style={{ color: "var(--fg-0)", fontWeight: 600 }}>6:54</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

// ═════════════════════════════════════════════════════════════
// TRACKING PAGE
// ═════════════════════════════════════════════════════════════
function TrackingPage() {
  return (
    <main className="content docs">
      <PageHeader
        title="Tracking de personas"
        subtitle="Trayectorias detectadas y conteo en tiempo real con YOLOv8 + ByteTrack."
        right={<div className="range-tabs"><button className="on">Ahora</button><button>Última hora</button><button>Hoy</button></div>}
      />
      <WipBanner>
        Implementación en progreso · pipeline RTSP funcional, visualización de trayectorias prevista para ago. 2026.
      </WipBanner>

      <div className="kpi-grid">
        <KpiCard label="Tracks activos" value="23" unit="ahora" delta="+5 vs hace 10m" trend="up" Ico={IcoUsers} spark={[18,20,22,19,21,24,22,23]} color="var(--brand-soft)" />
        <KpiCard label="Personas detectadas hoy" value="312" unit="únicas" delta="+8.4% vs ayer" trend="up" Ico={IcoTrend} iconClass="pos" spark={[20,40,80,120,160,210,260,290,312]} color="var(--pos-soft)" />
        <KpiCard label="Confianza promedio" value="89%" unit="modelo" delta="estable" trend="neutral" Ico={IcoChip} spark={[85,88,90,87,89,90,89]} color="var(--brand-soft)" />
        <KpiCard label="Tracks perdidos" value="14" unit="hoy" delta="−6 vs ayer" trend="up" Ico={IcoAlert} iconClass="warn" spark={[20,18,16,14,15,14]} color="#e6a83b" />
      </div>

      <div className="main-grid" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><span className="ico"><IcoTrack /></span>Mapa de trayectorias en vivo</div>
            <span className="cam-status"><IcoCam style={{ width: 14, height: 14 }} /><b>cam-1, cam-3, cam-7</b><span className="live">LIVE</span></span>
          </div>
          <TrajectoryMap />
        </div>
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><span className="ico"><IcoUsers /></span>Tracks activos</div>
            <span className="mono" style={{ fontSize: 11, color: "var(--fg-3)" }}>actualizando</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 480, overflowY: "auto" }}>
            {Array.from({ length: 10 }, (_, i) => {
              const tid = 1042 + i * 3;
              const conf = (78 + Math.random() * 18).toFixed(0);
              const time = Math.floor(20 + Math.random() * 240);
              const zones = ["Cafetería","Góndola B","Heladera","Caja 1","Entrada","Caja 2"];
              const z = zones[i % zones.length];
              return (
                <div key={tid} style={{
                  display: "grid", gridTemplateColumns: "auto 1fr auto auto", gap: 10, alignItems: "center",
                  padding: "9px 10px", background: "var(--bg-3)", border: "1px solid var(--line)", borderRadius: 8
                }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: i%4===0 ? "var(--warn)" : "var(--pos-soft)" }} />
                  <div>
                    <div className="mono" style={{ fontSize: 11.5, color: "var(--fg-0)", fontWeight: 500 }}>#{tid}</div>
                    <div style={{ fontSize: 10.5, color: "var(--fg-3)" }}>{z}</div>
                  </div>
                  <div className="mono" style={{ fontSize: 11, color: "var(--fg-1)" }}>{Math.floor(time/60)}:{(time%60).toString().padStart(2,"0")}</div>
                  <div className="mono" style={{ fontSize: 11, color: "var(--fg-2)", width: 30, textAlign: "right" }}>{conf}%</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </main>
  );
}

function TrajectoryMap() {
  // Simplified trajectory overlay
  const paths = [
    "M 30 100 Q 80 80, 130 70 T 240 90",
    "M 30 110 Q 100 130, 180 130 T 280 110",
    "M 30 95  Q 70 60, 110 50 T 220 60",
    "M 30 120 Q 90 140, 160 145 T 270 130",
    "M 30 100 Q 60 95, 100 90 T 180 100 T 270 110",
  ];
  return (
    <div style={{ height: 420, borderRadius: 10, overflow: "hidden", border: "1px solid var(--line)", position: "relative" }}>
      <svg viewBox="0 0 320 200" width="100%" height="100%" preserveAspectRatio="none" style={{ background: "#0e1729" }}>
        <defs>
          <pattern id="tgrid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M20 0H0V20" stroke="rgba(255,255,255,0.025)" fill="none" />
          </pattern>
        </defs>
        <rect width="320" height="200" fill="url(#tgrid)" />
        {/* Fixtures */}
        <g stroke="rgba(140,165,210,0.28)" strokeWidth="1" fill="rgba(140,165,210,0.05)">
          <rect x="14" y="14" width="292" height="172" rx="3" fill="none" />
          <rect x="90" y="40" width="42" height="14" rx="1.5" />
          <rect x="90" y="58" width="42" height="14" rx="1.5" />
          <rect x="90" y="130" width="42" height="14" rx="1.5" />
          <rect x="158" y="40" width="50" height="22" rx="2" />
          <rect x="158" y="138" width="50" height="22" rx="2" />
          <rect x="232" y="78" width="62" height="12" rx="1.5" />
          <rect x="232" y="110" width="62" height="12" rx="1.5" />
        </g>
        {/* Paths */}
        {paths.map((p, i) => (
          <g key={i}>
            <path d={p} stroke={`hsl(${200 + i*30}, 70%, 60%)`} strokeWidth="1.5" fill="none" opacity=".6"
              strokeDasharray="2 3" />
            <circle r="3" fill={`hsl(${200 + i*30}, 80%, 65%)`}>
              <animateMotion dur={`${6 + i}s`} repeatCount="indefinite" path={p} />
            </circle>
          </g>
        ))}
        {/* Cameras */}
        {[[40,30],[160,30],[280,30],[40,180],[160,180],[280,180]].map(([cx,cy], i) => (
          <g key={i}><circle cx={cx} cy={cy} r="3" fill="var(--bg-1)" stroke="var(--pos-soft)" strokeWidth="1" /><circle cx={cx} cy={cy} r="1" fill="var(--pos-soft)" /></g>
        ))}
      </svg>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// STOCK PAGE
// ═════════════════════════════════════════════════════════════
const STOCK_DATA = [
  { sku:"BEB-001", name:"Coca-Cola 500ml",        cat:"Bebidas",   zone:"B3", detected:2,  expected:24, conf:91, status:"critical" },
  { sku:"BEB-002", name:"Agua mineral 1.5L",       cat:"Bebidas",   zone:"C2", detected:6,  expected:18, conf:88, status:"low"      },
  { sku:"SNK-014", name:"Papas Lays clásicas",     cat:"Snacks",    zone:"A1", detected:18, expected:20, conf:94, status:"ok"       },
  { sku:"SNK-027", name:"Doritos queso",           cat:"Snacks",    zone:"A1", detected:12, expected:15, conf:87, status:"ok"       },
  { sku:"GLO-005", name:"Chocolatines surtidos",    cat:"Golosinas", zone:"A2", detected:0,  expected:30, conf:82, status:"critical" },
  { sku:"GLO-011", name:"Caramelos masticables",    cat:"Golosinas", zone:"A2", detected:24, expected:24, conf:96, status:"ok"       },
  { sku:"LAC-003", name:"Yogurt Yogurísimo 200g",  cat:"Lácteos",   zone:"H1", detected:4,  expected:12, conf:79, status:"low"      },
  { sku:"LAC-008", name:"Leche entera 1L",          cat:"Lácteos",   zone:"H1", detected:8,  expected:10, conf:85, status:"ok"       },
  { sku:"CIG-002", name:"Marlboro Rojo 20u",        cat:"Cigarrillos",zone:"R1",detected:6,  expected:30, conf:72, status:"low"      },
  { sku:"PAN-001", name:"Pan de hamburguesa x4",   cat:"Panadería", zone:"P1", detected:5,  expected:8,  conf:88, status:"ok"       },
];

function StockPage() {
  const toast = useToast();
  const [cat, setCat] = React.useState("all");
  const [statusFil, setStatusFil] = React.useState("all");

  const categories = ["all", ...Array.from(new Set(STOCK_DATA.map(s => s.cat)))];
  const filtered = STOCK_DATA.filter(s =>
    (cat === "all" || s.cat === cat) &&
    (statusFil === "all" || s.status === statusFil)
  );

  return (
    <main className="content docs">
      <PageHeader
        title="Control de stock"
        subtitle="Productos detectados en góndola vs stock esperado · alertas de faltantes."
        right={
          <>
            <button className="btn-sec" onClick={() => toast("Re-analizando góndolas…", { kind:"info" })}>
              <IcoSpinner style={{ marginRight: 6 }} />Re-escanear
            </button>
            <button className="btn-pri" onClick={() => toast("Reporte enviado a depósito", { kind:"success" })}>
              <IcoSend style={{ marginRight: 6 }} />Pedir reposición
            </button>
          </>
        }
      />
      <WipBanner>
        Modelo de detección de productos en entrenamiento · datos mostrados son simulados sobre 10 SKUs piloto.
      </WipBanner>

      <div className="stat-row">
        <div className="stat-mini"><span className="stat-mini-lbl">SKUs monitoreados</span><span className="stat-mini-val mono">10</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">Stock crítico</span><span className="stat-mini-val mono" style={{ color: "var(--alert-soft)" }}>2</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">Stock bajo</span><span className="stat-mini-val mono" style={{ color: "var(--warn)" }}>3</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">OK</span><span className="stat-mini-val mono" style={{ color: "var(--pos-soft)" }}>5</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">Confianza promedio</span><span className="stat-mini-val mono">86%</span></div>
      </div>

      <div className="filter-bar">
        <div className="filter-grp">
          <span className="filter-lbl">Estado</span>
          <div className="seg">
            {[["all","Todos"],["critical","Crítico"],["low","Bajo"],["ok","OK"]].map(([k,l]) => (
              <button key={k} className={statusFil===k?"on":""} onClick={() => setStatusFil(k)}>{l}</button>
            ))}
          </div>
        </div>
        <div className="filter-grp">
          <span className="filter-lbl">Categoría</span>
          <select className="select-input" value={cat} onChange={(e) => setCat(e.target.value)}>
            {categories.map(c => <option key={c} value={c}>{c === "all" ? "Todas" : c}</option>)}
          </select>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--fg-3)" }} className="mono">
          {filtered.length} / {STOCK_DATA.length} SKUs
        </div>
      </div>

      <div className="data-table">
        <div className="dt-head dt-row dt-stock">
          <div>SKU</div><div>Producto</div><div>Categoría</div><div>Zona</div>
          <div>Detectado / Esperado</div><div>Confianza</div><div>Estado</div>
        </div>
        {filtered.map(s => {
          const pct = (s.detected / s.expected) * 100;
          const barColor = s.status === "critical" ? "var(--alert-soft)" : s.status === "low" ? "var(--warn)" : "var(--pos-soft)";
          return (
            <div key={s.sku} className="dt-row dt-stock">
              <div className="mono" style={{ color: "var(--fg-2)", fontSize: 11.5 }}>{s.sku}</div>
              <div style={{ color: "var(--fg-0)", fontWeight: 500, fontSize: 12.5 }}>{s.name}</div>
              <div style={{ color: "var(--fg-2)", fontSize: 12 }}>{s.cat}</div>
              <div className="mono" style={{ color: "var(--fg-2)", fontSize: 11.5 }}>{s.zone}</div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="mono" style={{ fontSize: 11.5, color: "var(--fg-0)", minWidth: 50 }}>{s.detected} / {s.expected}</span>
                  <div style={{ flex: 1, height: 4, background: "var(--bg-1)", borderRadius: 99 }}>
                    <div style={{ width: `${Math.min(100, pct)}%`, height: "100%", background: barColor, borderRadius: 99 }} />
                  </div>
                </div>
              </div>
              <div className="mono" style={{ color: s.conf < 80 ? "var(--warn)" : "var(--fg-1)", fontSize: 11.5 }}>{s.conf}%</div>
              <div>{stockBadge(s.status)}</div>
            </div>
          );
        })}
      </div>
    </main>
  );
}

function stockBadge(s) {
  const map = {
    critical: { label: "Crítico", color: "var(--alert-soft)", bg: "rgba(192,57,43,.12)",  border: "rgba(226,92,78,.25)" },
    low:      { label: "Bajo",    color: "var(--warn)",        bg: "rgba(214,137,32,.12)", border: "rgba(214,137,32,.25)" },
    ok:       { label: "OK",      color: "var(--pos-soft)",    bg: "rgba(46,163,79,.1)",   border: "rgba(46,163,79,.22)" },
  };
  const x = map[s];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 99,
      fontSize: 11, fontWeight: 500, color: x.color, background: x.bg, border: `1px solid ${x.border}`, whiteSpace: "nowrap"
    }}>{x.label}</span>
  );
}

// ═════════════════════════════════════════════════════════════
// CAMERAS PAGE
// ═════════════════════════════════════════════════════════════
function CamerasPage() {
  const toast = useToast();
  const cams = ["Cafetería","Caja 1","Caja 2","Góndolas A"].map((name, i) => ({
    id: i + 1,
    name,
    fps: 25 + Math.floor(Math.random() * 5),
    conf: Math.floor(78 + Math.random() * 18),
    status: "ok",
    detections: Math.floor(2 + Math.random() * 8),
  }));

  return (
    <main className="content docs">
      <PageHeader
        title="Cámaras"
        subtitle="Estado del pipeline RTSP y detección en tiempo real por cámara."
        right={
          <>
            <button className="btn-sec" onClick={() => toast("Test de conectividad iniciado…")}>
              <IcoSpinner style={{ marginRight: 6 }} />Test conectividad
            </button>
            <button className="btn-pri" onClick={() => toast("Función disponible próximamente")}>
              <span style={{ marginRight: 4 }}>+</span>Agregar cámara
            </button>
          </>
        }
      />

      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: 14
      }}>
        {cams.map(c => (
          <div key={c.id} className="panel" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{
              aspectRatio: "16/9", background:
                "radial-gradient(circle at 30% 40%, rgba(37,99,168,.18), transparent 60%), repeating-linear-gradient(45deg, transparent 0, transparent 10px, rgba(255,255,255,0.015) 10px, rgba(255,255,255,0.015) 11px), #0e1729",
              position: "relative", display: "grid", placeItems: "center", color: "var(--fg-3)"
            }}>
              <IcoCam style={{ width: 32, height: 32, opacity: .4 }} />
              <div style={{ position: "absolute", top: 8, left: 8, display: "flex", gap: 6, alignItems: "center", fontSize: 10 }}>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 5, padding: "2px 7px", borderRadius: 99,
                  background: "rgba(0,0,0,.5)", color: c.status === "warn" ? "var(--warn)" : "var(--pos-soft)",
                  border: `1px solid ${c.status === "warn" ? "var(--warn)" : "var(--pos-soft)"}33`
                }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: "currentColor", animation: "pulse 1.6s infinite" }} />
                  LIVE
                </span>
                <span className="mono" style={{ padding: "2px 7px", background: "rgba(0,0,0,.5)", borderRadius: 99, color: "var(--fg-1)" }}>
                  cam-{c.id}
                </span>
              </div>
              <div style={{ position: "absolute", bottom: 8, right: 8, fontSize: 10, color: "var(--fg-3)" }} className="mono">
                {new Date().toLocaleTimeString("es-AR")}
              </div>
              {/* Mock bbox */}
              {c.detections > 0 && (
                <>
                  <div style={{ position: "absolute", top: "40%", left: "30%", width: 36, height: 60, border: "1.5px solid var(--pos-soft)", borderRadius: 2, opacity: .8 }}>
                    <span style={{ position: "absolute", top: -16, left: -1, background: "var(--pos-soft)", color: "#000", fontSize: 9, padding: "1px 4px", borderRadius: 2, fontFamily: "JetBrains Mono", fontWeight: 600 }}>person 0.{c.conf}</span>
                  </div>
                  {c.detections > 2 && (
                    <div style={{ position: "absolute", top: "35%", left: "60%", width: 32, height: 56, border: "1.5px solid var(--pos-soft)", borderRadius: 2, opacity: .7 }} />
                  )}
                </>
              )}
            </div>
            <div style={{ padding: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 13, color: "var(--fg-0)", fontWeight: 500 }}>{c.name}</div>
                  <div className="mono" style={{ fontSize: 10.5, color: "var(--fg-3)" }}>rtsp://nvr.local/ch{c.id}</div>
                </div>
                <button className="iconbtn" onClick={() => toast(`Cámara ${c.id} pausada`)}><IcoMore /></button>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, fontSize: 11 }}>
                <div>
                  <div style={{ color: "var(--fg-3)" }}>FPS</div>
                  <div className="mono" style={{ color: "var(--fg-0)", fontWeight: 500 }}>{c.fps}</div>
                </div>
                <div>
                  <div style={{ color: "var(--fg-3)" }}>Confianza</div>
                  <div className="mono" style={{ color: c.conf < 60 ? "var(--warn)" : "var(--fg-0)", fontWeight: 500 }}>{c.conf}%</div>
                </div>
                <div>
                  <div style={{ color: "var(--fg-3)" }}>Detec.</div>
                  <div className="mono" style={{ color: "var(--fg-0)", fontWeight: 500 }}>{c.detections}</div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}

// ═════════════════════════════════════════════════════════════
// SETTINGS PAGE
// ═════════════════════════════════════════════════════════════
function SettingsPage() {
  const toast = useToast();
  const [tab, setTab] = React.useState("general");
  const [thresholds, setThresholds] = React.useState({
    queue: 4, wait: 240, density: 1.8, conf: 60, stockMin: 5,
  });
  const [notif, setNotif] = React.useState({ email: true, push: true, telegram: false });

  return (
    <main className="content docs">
      <PageHeader
        title="Configuración"
        subtitle="Ajustes del sistema y umbrales de alertas."
        right={<button className="btn-pri" onClick={() => toast("Cambios guardados", { kind: "success" })}>Guardar cambios</button>}
      />

      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 14 }}>
        <nav className="nav" style={{ position: "sticky", top: 0 }}>
          {[
            ["general","General"],
            ["thresholds","Umbrales de alertas"],
            ["cameras","Cámaras"],
            ["notif","Notificaciones"],
            ["users","Usuarios y roles"],
          ].map(([k,l]) => (
            <a key={k} className={tab===k?"active":""} onClick={() => setTab(k)}>{l}</a>
          ))}
        </nav>

        <div>
          {tab === "general" && (
            <div className="panel">
              <h3 className="docs-h3">Sucursal</h3>
              <div className="form-grid">
                <Field label="Nombre" value="Strumia — Mendoza" />
                <Field label="Dirección" value="Av. San Martín 1234" />
                <Field label="Zona horaria" value="America/Argentina/Mendoza" readonly />
                <Field label="Horario operativo" value="06:00 – 22:00" />
              </div>
              <h3 className="docs-h3" style={{ marginTop: 24 }}>Sistema</h3>
              <div className="form-grid">
                <Field label="Modelo de detección" value="YOLOv8m" readonly mono />
                <Field label="Tracker" value="ByteTrack" readonly mono />
                <Field label="Frame skip" value="3" mono />
                <Field label="Versión" value="OptiFull v0.3.0" readonly mono />
              </div>
            </div>
          )}

          {tab === "thresholds" && (
            <div className="panel">
              <h3 className="docs-h3">Umbrales que generan alertas</h3>
              <p style={{ fontSize: 12, color: "var(--fg-2)", margin: "0 0 18px" }}>
                Define cuándo el sistema dispara cada tipo de alerta. Valores conservadores reducen falsos positivos.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <Slider label="Cola máxima por caja" v={thresholds.queue} min={2} max={10} unit="personas" onChange={(v) => setThresholds({...thresholds, queue: v})} />
                <Slider label="Espera máxima" v={thresholds.wait} min={60} max={600} step={15} unit="seg" onChange={(v) => setThresholds({...thresholds, wait: v})} />
                <Slider label="Densidad máxima" v={thresholds.density} min={0.5} max={3} step={0.1} unit="pers/m²" onChange={(v) => setThresholds({...thresholds, density: v})} />
                <Slider label="Confianza mínima del modelo" v={thresholds.conf} min={30} max={95} unit="%" onChange={(v) => setThresholds({...thresholds, conf: v})} />
                <Slider label="Stock mínimo en góndola" v={thresholds.stockMin} min={1} max={30} unit="unidades" onChange={(v) => setThresholds({...thresholds, stockMin: v})} />
              </div>
            </div>
          )}

          {tab === "cameras" && (
            <div className="panel">
              <h3 className="docs-h3">Configuración global de cámaras</h3>
              <div className="form-grid">
                <Field label="Protocolo" value="RTSP" readonly mono />
                <Field label="NVR" value="nvr.local:554" mono />
                <Field label="Codec" value="H.264" readonly mono />
                <Field label="Resolución" value="1280×720" mono />
              </div>
              <p style={{ fontSize: 12, color: "var(--fg-3)", marginTop: 16 }}>
                Para configuración individual de cada cámara, ir a la sección <a style={{ color: "var(--brand-soft)", cursor: "default" }}>Cámaras</a>.
              </p>
            </div>
          )}

          {tab === "notif" && (
            <div className="panel">
              <h3 className="docs-h3">Canales de notificación</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {[
                  ["email", "Email", "Enviar alertas críticas a agostina.b@strumia.ypf"],
                  ["push", "Notificaciones push", "Push al navegador cuando el dashboard está abierto"],
                  ["telegram", "Telegram", "Canal de equipo @strumia-ops (próximamente)"],
                ].map(([k, name, desc]) => (
                  <div key={k} style={{
                    padding: "12px 14px", background: "var(--bg-3)", border: "1px solid var(--line)", borderRadius: 10,
                    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14
                  }}>
                    <div>
                      <div style={{ fontSize: 13, color: "var(--fg-0)", fontWeight: 500 }}>{name}</div>
                      <div style={{ fontSize: 11.5, color: "var(--fg-2)", marginTop: 3 }}>{desc}</div>
                    </div>
                    <Switch on={notif[k]} onClick={() => setNotif({ ...notif, [k]: !notif[k] })} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === "users" && (
            <div className="panel">
              <h3 className="docs-h3">Usuarios con acceso</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  ["Agostina Blasón", "Encargada", "AB", "owner"],
                  ["Arnon Daniel Nahmias", "Operador", "AN", "admin"],
                  ["Paulina Ortiz", "Operadora", "PO", "admin"],
                  ["Henry Martinez", "Visualizador YPF", "HM", "viewer"],
                ].map(([name, role, init, level]) => (
                  <div key={name} style={{
                    display: "grid", gridTemplateColumns: "auto 1fr auto auto", alignItems: "center", gap: 12,
                    padding: "10px 14px", background: "var(--bg-3)", border: "1px solid var(--line)", borderRadius: 10
                  }}>
                    <div className="avatar">{init}</div>
                    <div>
                      <div style={{ fontSize: 13, color: "var(--fg-0)" }}>{name}</div>
                      <div style={{ fontSize: 11.5, color: "var(--fg-3)" }}>{role}</div>
                    </div>
                    <span style={{
                      fontSize: 10.5, padding: "2px 8px", borderRadius: 99,
                      background: level === "owner" ? "rgba(37,99,168,.15)" : "var(--bg-2)",
                      color: level === "owner" ? "var(--brand-soft)" : "var(--fg-2)",
                      border: `1px solid ${level === "owner" ? "rgba(37,99,168,.3)" : "var(--line)"}`,
                      textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 500
                    }}>{level}</span>
                    <button className="iconbtn" onClick={() => toast(`Editando permisos de ${name}`)}><IcoMore /></button>
                  </div>
                ))}
              </div>
              <button className="btn-sec" style={{ marginTop: 14 }} onClick={() => toast("Invitar usuario · próximamente")}>+ Invitar usuario</button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

function Field({ label, value, readonly, mono }) {
  return (
    <div className="form-field">
      <label>{label}</label>
      <input type="text" defaultValue={value} readOnly={readonly}
        className={mono ? "mono" : ""}
        style={{ opacity: readonly ? .7 : 1 }} />
    </div>
  );
}

function Slider({ label, v, min, max, step = 1, unit, onChange }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 12.5, color: "var(--fg-1)" }}>{label}</span>
        <span className="mono" style={{ fontSize: 12, color: "var(--fg-0)", fontWeight: 500 }}>
          {v} <span style={{ color: "var(--fg-3)", fontWeight: 400 }}>{unit}</span>
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={v}
        onChange={(e) => onChange(+e.target.value)}
        style={{ width: "100%", accentColor: "var(--brand-soft)" }} />
    </div>
  );
}

function Switch({ on, onClick }) {
  return (
    <button onClick={onClick} style={{
      appearance: "none", border: 0, padding: 0, width: 36, height: 20, borderRadius: 99,
      background: on ? "var(--brand)" : "var(--bg-1)", border: `1px solid ${on ? "var(--brand)" : "var(--line)"}`,
      cursor: "default", position: "relative", transition: "background .15s, border-color .15s"
    }}>
      <span style={{
        position: "absolute", top: 1, left: on ? 17 : 1, width: 16, height: 16, borderRadius: "50%",
        background: "#fff", transition: "left .15s",
        boxShadow: "0 1px 3px rgba(0,0,0,.3)"
      }} />
    </button>
  );
}

window.HeatmapPage = HeatmapPage;
window.TrackingPage = TrackingPage;
window.StockPage = StockPage;
window.CamerasPage = CamerasPage;
window.SettingsPage = SettingsPage;

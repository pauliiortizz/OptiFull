// OptiFull Dashboard — main app
const { useState, useEffect, useMemo, useRef } = React;

// ── Simulated data ────────────────────────────────────────────────────────
const HOURS = ["06","07","08","09","10","11","12","13","14","15","16","17","18","19","20","21","22"];
// People entering store per hour
const FLOW_TODAY = [4, 9, 18, 31, 28, 24, 38, 52, 47, 33, 29, 35, 41, 0, 0, 0, 0];
// Project future hours softly so the curve isn't flat - use a forecast
const forecast = [38, 44, 40, 32, 22];
for (let i = 13, j = 0; i < HOURS.length && j < forecast.length; i++, j++) FLOW_TODAY[i] = forecast[j];
const FLOW_YESTERDAY = [6, 11, 16, 26, 30, 22, 34, 49, 53, 37, 26, 31, 36, 35, 39, 28, 19];

const CURRENT_HOUR_IDX = 12; // 18:00 — index of "18"

// Cajas / registers live state
const REGISTERS_INITIAL = [
  { id: 1, name: "Caja 1", queue: 2, wait: 95,  status: "ok"   },
  { id: 2, name: "Caja 2", queue: 5, wait: 270, status: "warn" },
  { id: 3, name: "Caja 3", queue: 0, wait: 0,   status: "idle" },
];

// Zones with current people count
const ZONES = [
  { name: "Cafetería",  pct: 28, count: 7 },
  { name: "Góndolas",   pct: 22, count: 6 },
  { name: "Cajas",      pct: 18, count: 5 },
  { name: "Heladera",   pct: 14, count: 3 },
  { name: "Entrada",    pct: 12, count: 2 },
  { name: "Otros",      pct:  6, count: 0 },
];

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#2563a8",
  "density": "regular",
  "showCameras": true,
  "liveUpdates": true,
  "heatIntensity": 1
}/*EDITMODE-END*/;

// ── Live clock + ticker ──────────────────────────────────────────────────
function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function useLivePeopleCount(initial = 23) {
  const [n, setN] = useState(initial);
  useEffect(() => {
    const id = setInterval(() => {
      setN((p) => Math.max(8, Math.min(48, p + Math.round((Math.random() - 0.5) * 4))));
    }, 3500);
    return () => clearInterval(id);
  }, []);
  return n;
}

// ── API stats hook ────────────────────────────────────────────────────────
function useApiStats() {
  const [stats, setStats]       = React.useState(null);
  const [loading, setLoading]   = React.useState(true);
  const [tick, setTick]         = React.useState(0);

  React.useEffect(() => {
    setLoading(true);
    fetch('/api/stats')
      .then(r => r.json())
      .then(data => { setStats(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [tick]);

  const refresh = () => setTick(t => t + 1);
  return { stats, loading, refresh };
}

// ── Helpers ──────────────────────────────────────────────────────────────
function fmtClock(d) {
  return d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}
function fmtDate(d) {
  return d.toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" });
}
function fmtMMSS(secs) {
  const m = Math.floor(secs / 60), s = secs % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ── Registers panel ──────────────────────────────────────────────────────
function RegistersPanel({ registers, view = "now", onViewChange = () => {} }) {
  // Synthetic "promedio" data
  const data = view === "avg"
    ? registers.map(r => ({ ...r, queue: Math.max(1, r.queue - 1), wait: Math.max(60, r.wait - 40), status: r.status === "idle" ? "idle" : "ok" }))
    : registers;
  return (
    <div className="panel">
      <div className="panel-head">
        <div className="panel-title"><span className="ico"><IcoClock /></span>Estado de cajas</div>
        <div className="seg">
          <button className={view==="now"?"on":""} onClick={() => onViewChange("now")}>Ahora</button>
          <button className={view==="avg"?"on":""} onClick={() => onViewChange("avg")}>Promedio</button>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {data.map((r) => {
          const cap = 8;
          const pct = Math.min(100, (r.queue / cap) * 100);
          const color =
            r.status === "warn" ? "var(--warn)" :
            r.status === "idle" ? "var(--fg-3)" :
            "var(--pos-soft)";
          return (
            <div key={r.id} style={{
              padding: "12px 12px", border: "1px solid var(--line)",
              borderRadius: 9, background: "var(--bg-3)"
            }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: "50%", background: color,
                    boxShadow: r.status === "warn" ? "0 0 8px var(--warn)" : "none"
                  }} />
                  <span style={{ fontSize: 12.5, fontWeight: 500 }}>{r.name}</span>
                  {r.status === "warn" && (
                    <span style={{ fontSize: 10, color: "var(--warn)", textTransform: "uppercase", letterSpacing: ".08em" }}>
                      saturada
                    </span>
                  )}
                  {r.status === "idle" && (
                    <span style={{ fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: ".08em" }}>
                      libre
                    </span>
                  )}
                </div>
                <div className="mono" style={{ fontSize: 12, color: "var(--fg-1)" }}>
                  <span style={{ color: "var(--fg-3)" }}>cola </span>
                  <b style={{ color: "var(--fg-0)", fontWeight: 600 }}>{r.queue}</b>
                  <span style={{ color: "var(--fg-3)" }}> · espera </span>
                  <b style={{ color: "var(--fg-0)", fontWeight: 600 }}>{r.wait ? fmtMMSS(r.wait) : "—"}</b>
                </div>
              </div>
              <div style={{
                height: 4, background: "var(--bg-1)", borderRadius: 99, overflow: "hidden", position: "relative"
              }}>
                <div style={{
                  width: `${pct}%`, height: "100%", background: color, borderRadius: 99,
                  transition: "width .4s ease"
                }} />
              </div>
            </div>
          );
        })}
      </div>
      <div style={{
        marginTop: 12, padding: "10px 12px", borderRadius: 8, background: "var(--bg-3)",
        border: "1px dashed var(--line)", display: "flex", justifyContent: "space-between",
        fontSize: 11.5, color: "var(--fg-2)"
      }}>
        <span>Tiempo promedio global</span>
        <span className="mono" style={{ color: "var(--fg-0)", fontWeight: 600 }}>2:18</span>
      </div>
    </div>
  );
}

// ── Page metadata for topbar crumb ────────────────────────────────────────
const PAGE_META = {
  dashboard: { crumb: ["Dashboard", "Operativo"] },
  heatmap:   { crumb: ["Análisis", "Mapa de calor"] },
  tracking:  { crumb: ["Análisis", "Tracking de personas"] },
  stock:     { crumb: ["Monitoreo", "Control de stock"] },
  reports:   { crumb: ["Análisis", "Reportes"] },
  alerts:    { crumb: ["Monitoreo", "Alertas"] },
  cameras:   { crumb: ["Sistema", "Cámaras"] },
  docs:      { crumb: ["Documentación", "Diseño"] },
  claude:    { crumb: ["Documentación", "Asistente IA"] },
  settings:  { crumb: ["Sistema", "Configuración"] },
};

// ── Dashboard page component (was inline in App) ─────────────────────────
function DashboardPage({ t, onNavigate }) {
  const toast = useToast();
  const [range, setRange] = useState("hoy");
  const [alertFilter, setAlertFilter] = useState("all");
  const [registerView, setRegisterView] = useState("now");

  const { stats, loading, refresh } = useApiStats();
  const { data: heatmap } = useHeatmapData();
  const people = useLivePeopleCount(23);
  const alerts = useLiveAlerts(8);

  const peopleSpark = useMemo(
    () => [12,15,18,16,21,24,22,19,23,26,28,25,22,20,24,27,30,28,24, people],
    [people]
  );
  const waitSpark   = useMemo(() => [180, 200, 240, 220, 195, 175, 168, 160, 158, 152, 148, 140, 138], []);
  const stockSpark  = useMemo(() => [4, 4, 5, 6, 5, 5, 6, 7, 7, 8, 7, 7, 7], []);

  const activeAlerts = alerts.filter((a) => Date.now() - a.ts < 30 * 60 * 1000);
  const criticalCount = activeAlerts.filter((a) => a.sev === "critical").length;
  const alertSpark = useMemo(() => [2, 3, 5, 4, 3, 2, 4, 3, 5, 6, 4, 3, activeAlerts.length || 3], [activeAlerts.length]);

  const filteredAlerts = alerts.filter(a => {
    if (alertFilter === "critical") return a.sev === "critical";
    if (alertFilter === "today")    return Date.now() - a.ts < 24 * 60 * 60 * 1000;
    return true;
  }).slice(0, 6);

  return (
    <main className="content">
      <div className="page-head">
        <div>
          <h1>Buenas tardes, Agostina</h1>
          <p>Estadísticas de grabaciones analizadas · datos en tiempo real no disponibles</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button className="btn-sec" onClick={refresh} disabled={loading} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <IcoSpinner style={{ width: 13, height: 13, animation: loading ? "spin 1s linear infinite" : "none" }} />
            {loading ? "Actualizando…" : "Actualizar datos"}
          </button>
          <div className="range-tabs">
          {[["hoy","Hoy"],["7d","7 días"],["30d","30 días"],["custom","Personalizado"]].map(([k,l]) => (
            <button key={k} className={range === k ? "on" : ""}
              onClick={() => { setRange(k); if (k === "custom") toast("Selector de rango personalizado próximamente"); }}>
              {l}
            </button>
          ))}
          </div>
        </div>
      </div>

      {/* KPI row */}
      <div className="kpi-grid">
        <KpiCard label="Personas analizadas" value={stats ? stats.personas_totales : "—"} unit="registros"
          delta={stats ? `Fuente: ${stats.fuente.toUpperCase()}` : "cargando…"} trend="neutral" Ico={IcoUsers}
          spark={peopleSpark} color="var(--brand-soft)" />
        <KpiCard label="Permanencia promedio" value={stats ? stats.permanencia_promedio_min : "—"} unit="min"
          delta={stats ? `máx ${stats.permanencia_maxima_min} min` : "cargando…"} trend="neutral" Ico={IcoClock} iconClass="pos"
          spark={waitSpark} color="var(--pos-soft)" />
        <KpiCard label="Alertas activas" value={activeAlerts.length}
          unit={`· ${criticalCount} crítica${criticalCount !== 1 ? "s" : ""}`}
          delta="fuente: grabación" trend="neutral" Ico={IcoAlert} iconClass="alert"
          spark={alertSpark} color="var(--alert-soft)" />
        <KpiCard label="Tiempo real" value="N/D" unit=""
          delta="sin cámara en vivo" trend="neutral" Ico={IcoCam} iconClass="warn"
          spark={[1,1,1,1,1,1,1,1,1,1]} color="var(--fg-3)" />
      </div>

      {/* Row 2 — flow + heatmap */}
      <div className="main-grid">
        <div className="panel">
          <div className="panel-head">
            <div>
              <div className="panel-title">
                <span className="ico"><IcoTrend /></span>
                Flujo de personas por hora
              </div>
              <div style={{ fontSize: 11.5, color: "var(--fg-3)", marginTop: 4 }}>
                Total hoy: <span className="mono" style={{ color: "var(--fg-1)" }}>312</span>
                <span style={{ color: "var(--fg-4)" }}> · </span>
                ayer: <span className="mono">428</span>
                <span style={{ color: "var(--pos-soft)", marginLeft: 8 }} className="mono">↑ pico 19h</span>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div className="flow-legend">
                <span className="sw today">Hoy</span>
                <span className="sw yest">Ayer</span>
              </div>
              <button className="iconbtn" title="Ver reportes completos" onClick={() => onNavigate("reports")}>
                <IcoExpand />
              </button>
            </div>
          </div>
          <div style={{ position: "relative" }}>
            <FlowChart today={FLOW_TODAY} yesterday={FLOW_YESTERDAY} hours={HOURS} currentHour={CURRENT_HOUR_IDX} />
            <div style={{ position: "absolute", inset: 0, background: "rgba(10,16,30,0.78)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 8 }}>
              <IcoCam style={{ width: 28, height: 28, opacity: 0.4 }} />
              <span style={{ fontSize: 13, color: "var(--fg-2)", fontWeight: 500 }}>Sin datos en tiempo real</span>
              <span style={{ fontSize: 11, color: "var(--fg-4)" }}>Requiere conexión de cámara en vivo</span>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head">
            <div className="panel-title">
              <span className="ico"><IcoHeat /></span>
              Mapa de calor — circulación
            </div>
            <button className="iconbtn" title="Ver mapa completo" onClick={() => onNavigate("heatmap")}>
              <IcoExpand />
            </button>
          </div>
          <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid var(--line)" }}>
            {heatmap?.imagen_url ? (
              <img src={heatmap.imagen_url} alt="Heatmap"
                style={{ width: "100%", height: 200, objectFit: "cover", display: "block", cursor: "default" }}
                onClick={() => onNavigate("heatmap")} />
            ) : (
              <div style={{ position: "relative" }}>
                <MiniHeatmap intensity={t.heatIntensity} />
                <div style={{ position: "absolute", inset: 0, background: "rgba(10,16,30,0.78)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 8 }}>
                  <IcoHeat style={{ width: 28, height: 28, opacity: 0.4 }} />
                  <span style={{ fontSize: 13, color: "var(--fg-2)", fontWeight: 500 }}>Sin datos aún</span>
                  <span style={{ fontSize: 11, color: "var(--fg-4)" }}>Ejecutá detectar_con_calor.py</span>
                </div>
              </div>
            )}
          </div>
          <div className="heat-legend">
            <span>Baja</span>
            <div className="heat-bar" />
            <span>Alta</span>
          </div>
          <div style={{
            marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--line-soft)",
            display: "flex", flexDirection: "column", gap: 6
          }}>
            {(heatmap?.zonas_ranking?.length > 0 ? heatmap.zonas_ranking.slice(0, 4) : ZONES.slice(0, 4)).map((z) => {
              const name = z.nombre || z.name;
              const pct  = z.pct;
              return (
                <div key={name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11.5 }}>
                  <span style={{ color: "var(--fg-2)", width: 80, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
                  <div style={{ flex: 1, height: 4, background: "var(--bg-3)", borderRadius: 99 }}>
                    <div style={{
                      width: `${Math.min(100, pct * (heatmap?.zonas_ranking?.length > 0 ? 1 : 3))}%`, height: "100%",
                      background: pct > 40 ? "var(--alert-soft)" : pct > 25 ? "var(--warn)" : "var(--brand-soft)",
                      borderRadius: 99
                    }} />
                  </div>
                  <span className="mono" style={{ color: "var(--fg-1)", fontSize: 11, width: 36, textAlign: "right" }}>{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Row 3 — alerts + registers */}
      <div className="row2">
        <div className="panel">
          <div className="panel-head">
            <div>
              <div className="panel-title">
                <span className="ico"><IcoAlert /></span>
                Alertas recientes
                <span style={{
                  marginLeft: 6, padding: "1px 7px", borderRadius: 99, fontSize: 10,
                  background: "var(--bg-3)", color: "var(--fg-2)", fontWeight: 500
                }} className="mono">{filteredAlerts.length}</span>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <div className="seg">
                {[["all","Todas"],["critical","Críticas"],["today","Hoy"]].map(([k,l]) => (
                  <button key={k} className={alertFilter===k?"on":""} onClick={() => setAlertFilter(k)}>{l}</button>
                ))}
              </div>
              <button className="iconbtn" onClick={() => toast("Configuración de feed próximamente")}><IcoMore /></button>
            </div>
          </div>
          {filteredAlerts.length === 0 ? (
            <div style={{ padding: "40px 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
              No hay alertas en este filtro.
            </div>
          ) : (
            <AlertsFeed alerts={filteredAlerts} />
          )}
          <div style={{
            marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--line-soft)",
            textAlign: "center"
          }}>
            <button onClick={() => onNavigate("alerts")} style={{
              appearance: "none", border: 0, background: "transparent", color: "var(--brand-soft)",
              fontSize: 12, fontWeight: 500, cursor: "default", padding: "4px 10px",
              borderRadius: 6, transition: "background .12s"
            }}
              onMouseEnter={(e) => e.currentTarget.style.background = "var(--bg-3)"}
              onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
            >
              Ver todas las alertas →
            </button>
          </div>
        </div>

        <RegistersPanel registers={REGISTERS_INITIAL} view={registerView} onViewChange={setRegisterView} />
      </div>
    </main>
  );
}

// ── Main App ─────────────────────────────────────────────────────────────
function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [page, setPage] = useState("dashboard");
  const now = useClock();

  // Apply accent override (tweak)
  useEffect(() => {
    document.documentElement.style.setProperty("--brand", t.accent);
    document.documentElement.style.setProperty("--brand-soft", lighten(t.accent, 0.18));
  }, [t.accent]);

  return (
    <ToastProvider>
      <AppShell t={t} setTweak={setTweak} page={page} setPage={setPage} now={now} />
    </ToastProvider>
  );
}

function AppShell({ t, setTweak, page, setPage, now }) {
  const toast = useToast();
  const alerts = useLiveAlerts(8);
  const activeAlerts = alerts.filter((a) => Date.now() - a.ts < 30 * 60 * 1000);
  const criticalCount = activeAlerts.filter((a) => a.sev === "critical").length;

  const [branchOpen, setBranchOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const branchRef = useRef(null);
  const notifRef = useRef(null);

  // Click outside handlers
  useEffect(() => {
    const handler = (e) => {
      if (branchRef.current && !branchRef.current.contains(e.target)) setBranchOpen(false);
      if (notifRef.current && !notifRef.current.contains(e.target)) setNotifOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const crumb = PAGE_META[page]?.crumb || ["—", "—"];

  const renderPage = () => {
    switch (page) {
      case "alerts":   return <AlertsPage />;
      case "reports":  return <ReportsPage />;
      case "heatmap":  return <HeatmapPage />;
      case "tracking": return <TrackingPage />;
      case "stock":    return <StockPage />;
      case "cameras":  return <CamerasPage />;
      case "settings": return <SettingsPage />;
      case "docs":     return <DocsPage />;
      case "claude":   return <ClaudeDocsPage />;
      default:         return <DashboardPage t={t} onNavigate={setPage} />;
    }
  };

  return (
    <div className="app">
      <Sidebar active={page} alertCount={activeAlerts.length} onNavigate={setPage} />

      <div className="main">
        {/* Topbar */}
        <header className="topbar">
          <div className="crumb">
            <b>{crumb[0]}</b>
            <IcoChev style={{ width: 12, height: 12 }} />
            <span>{crumb[1]}</span>
          </div>

          <div ref={branchRef} style={{ position: "relative" }}>
            <button className="branch-sel" onClick={() => setBranchOpen(o => !o)} style={{ appearance: "none", border: "1px solid var(--line)" }}>
              <span className="dot" />
              <span style={{ color: "var(--fg-3)", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".08em", marginRight: 4 }}>Sucursal</span>
              <b style={{ color: "var(--fg-0)", fontWeight: 500 }}>Strumia — Mendoza</b>
              <IcoDown style={{ width: 14, height: 14, color: "var(--fg-3)", marginLeft: 4, transition: "transform .15s", transform: branchOpen ? "rotate(180deg)" : "none" }} />
            </button>
            {branchOpen && (
              <div className="dropdown">
                <div className="dd-head">Sucursales activas</div>
                {[
                  { name: "Strumia — Mendoza",     status: "live",   active: true },
                  { name: "Centro — Córdoba",       status: "offline" },
                  { name: "Norte — Buenos Aires",   status: "offline" },
                ].map(b => (
                  <button key={b.name} className={`dd-item ${b.active ? "active" : ""}`} onClick={() => {
                    setBranchOpen(false);
                    if (!b.active) toast(`Cambiando a ${b.name}…`, { kind: "info" });
                  }}>
                    <span className={`dd-dot ${b.status}`} />
                    <span style={{ flex: 1, textAlign: "left" }}>{b.name}</span>
                    {b.active && <IcoCheck size={12} stroke={2.4} />}
                  </button>
                ))}
                <div className="dd-foot">
                  <button onClick={() => { setBranchOpen(false); toast("Agregar sucursal — fuera del alcance del prototipo", { kind: "warn" }); }}>
                    + Agregar sucursal
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="topbar-spacer" />

          <div className="cam-status">
            <IcoCam style={{ width: 14, height: 14 }} />
            <b>4 cámaras</b>
            <span style={{ color: "var(--fg-3)" }}>·</span>
            <span style={{ color: "var(--fg-3)", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".08em" }}>grabación</span>
          </div>

          <div ref={notifRef} style={{ position: "relative" }}>
            <button className="iconbtn" title="Notificaciones" style={{ position: "relative" }}
              onClick={() => setNotifOpen(o => !o)}>
              <IcoBell />
              {criticalCount > 0 && (
                <span style={{
                  position: "absolute", top: -3, right: -3, width: 8, height: 8, borderRadius: "50%",
                  background: "var(--alert)", boxShadow: "0 0 0 2px var(--bg-0)"
                }} />
              )}
            </button>
            {notifOpen && (
              <div className="dropdown" style={{ width: 320, right: 0, left: "auto" }}>
                <div className="dd-head">
                  Notificaciones
                  <span className="mono" style={{ color: "var(--fg-3)", fontWeight: 400 }}> · {activeAlerts.length}</span>
                </div>
                {activeAlerts.slice(0, 4).map(a => {
                  const secs = Math.floor((Date.now() - a.ts) / 1000);
                  const rel = secs < 60 ? `${secs}s` : `${Math.floor(secs/60)}m`;
                  return (
                    <div key={a.id} className="dd-item" onClick={() => { setNotifOpen(false); setPage("alerts"); }}>
                      <span className={`alert-dot ${a.sev}`} style={{ marginTop: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, color: "var(--fg-0)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.title}</div>
                        <div style={{ fontSize: 10.5, color: "var(--fg-3)" }} className="mono">hace {rel}</div>
                      </div>
                    </div>
                  );
                })}
                <div className="dd-foot">
                  <button onClick={() => { setNotifOpen(false); setPage("alerts"); }}>Ver todas las alertas →</button>
                </div>
              </div>
            )}
          </div>

          <div className="clock">
            <div className="mono" style={{ fontWeight: 500 }}>{fmtClock(now)}</div>
            <small>{fmtDate(now)}</small>
          </div>
        </header>

        {/* Page content */}
        {renderPage()}
      </div>

      {/* Tweaks */}
      <TweaksPanel>
        <TweakSection label="Apariencia" />
        <TweakColor label="Color de acento" value={t.accent}
          options={["#2563a8", "#7a5ad9", "#1a7a3a", "#d68920"]}
          onChange={(v) => setTweak("accent", v)} />
        <TweakRadio label="Densidad" value={t.density}
          options={["compact", "regular"]}
          onChange={(v) => setTweak("density", v)} />

        <TweakSection label="Visualización" />
        <TweakSlider label="Intensidad heatmap" value={t.heatIntensity}
          min={0.4} max={1.4} step={0.1}
          onChange={(v) => setTweak("heatIntensity", v)} />
        <TweakToggle label="Mostrar cámaras en mapa" value={t.showCameras}
          onChange={(v) => setTweak("showCameras", v)} />
        <TweakToggle label="Actualizaciones en vivo" value={t.liveUpdates}
          onChange={(v) => setTweak("liveUpdates", v)} />
      </TweaksPanel>
    </div>
  );
}

// Lighten utility (hex)
function lighten(hex, amt) {
  const h = hex.replace("#", "");
  const num = parseInt(h, 16);
  const r = Math.min(255, ((num >> 16) & 255) + Math.round(255 * amt));
  const g = Math.min(255, ((num >> 8) & 255) + Math.round(255 * amt));
  const b = Math.min(255, (num & 255) + Math.round(255 * amt));
  return `rgb(${r}, ${g}, ${b})`;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);

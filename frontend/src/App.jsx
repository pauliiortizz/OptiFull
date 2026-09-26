import { useState, useEffect, useMemo, useRef } from 'react'
import {
  IcoUsers, IcoClock, IcoBell, IcoHeat, IcoCam, IcoAlert,
  IcoChev, IcoDown, IcoCheck, IcoMore, IcoExpand, IcoSpinner,
  IcoPlay, IcoPause, IcoTrend, IcoHome,
} from './components/Icons'
import { Sparkline, KpiCard, KpiTicker, RadialGauge } from './components/Sparkline'
import { FloorPlan } from './components/FloorPlan'
import { AlertsFeed, useLiveAlerts } from './components/AlertsFeed'
import { ToastProvider, useToast, PageHeader } from './components/Toast'
import { Sidebar } from './components/Sidebar'
import {
  useTweaks, TweaksPanel, TweakSection,
  TweakSlider, TweakToggle, TweakColor, TweakRadio
} from './components/TweaksPanel'
import { AlertsPage } from './pages/SectionPages'
import {
  HeatmapPage,
  TrackingPage, StockPage, SettingsPage
} from './pages/PagesHeatmapCameras'
import { ReportsV2Page } from './pages/ReportsV2Page'
import { ReportsLegacyPage } from './pages/ReportsLegacyPage'

// ── Simulated data ────────────────────────────────────────────────────────
const REGISTERS_INITIAL = [
  { id: 1, name: "Caja 1", queue: 2, wait: 95,  status: "ok"   },
  { id: 2, name: "Caja 2", queue: 5, wait: 270, status: "warn" },
  { id: 3, name: "Caja 3", queue: 0, wait: 0,   status: "idle" },
];

// Etiqueta y tinte por tipo REAL de zona (ver NOMBRES_TIPO en reportes.py) --
// mismo color que usa FloorPlan.STORE_ZONES para la zona equivalente en el
// plano, asi la barra del panel lateral y el resaltado del ROI coinciden.
// 'otro' agrupa Ingreso y Cafetería: el schema no las distingue (ambas
// comparten permanencia real de 'Salón'), así que se etiqueta como zona
// compuesta en vez de mostrar dos filas con el mismo número disfrazadas de
// zonas distintas.
const ZONA_ROI = {
  gondola: { label: "Góndolas Centrales",         tint: "106,114,207" },
  caja:    { label: "Línea de Cajas",              tint: "198,138,62"  },
  otro:    { label: "Salón (Ingreso / Cafetería)", tint: "156,147,188" },
};

const TWEAK_DEFAULTS = {
  accent: "#4f68e5", // azul del sitio Optifull — acento de la interfaz
  density: "regular",
  showCameras: true,
  liveUpdates: true,
  heatIntensity: 1,
};

// ── Hooks ─────────────────────────────────────────────────────────────────
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

// Permanencia real por zona (Caja / Góndolas / Salón) — ver
// /reportes/permanencia-por-zona en frontend/api/reportes.py. Alimenta tanto
// el numero superpuesto en el plano (modo "Zonas" de FloorPlan) como los dos
// paneles laterales de la consola espacial, reemplazando los valores
// hardcodeados que tenía antes (STORE_ZONES.occ / GONDOLA_AISLES.dwellMin).
function useZonasPermanencia() {
  const [zonas, setZonas]     = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetch('/api/reportes/permanencia-por-zona')
      .then(r => r.json())
      .then(d => { setZonas(d?.zonas || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  // Mapa tipo -> fila, para que FloorPlan pueda mirar cada ROI por su tipoReal.
  const porTipo = useMemo(() => Object.fromEntries(zonas.map(z => [z.tipo, z])), [zonas]);
  return { zonas, porTipo, loading };
}

// Hora de mayor ocupación real (promedio de clientes simultáneos), ya
// calculada por /reportes/congestion-horaria a partir de la tabla 'visitas'
// -- ver reportes.py: agrupa por dia-de-semana/hora y detecta el rango
// horario que es maximo local y significativo (>=60% del pico de ese dia).
// Alimenta el KPI "Hora Pico", que reemplaza al placeholder "Live Feed: N/A".
function useHoraPico() {
  const [pico, setPico]       = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetch('/api/reportes/congestion-horaria')
      .then(r => r.json())
      .then(d => { setPico(d?.pico || null); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { pico, loading };
}

function useApiStats() {
  const [stats, setStats]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick]       = useState(0);

  useEffect(() => {
    setLoading(true);
    fetch('/api/stats')
      .then(r => r.json())
      .then(data => { setStats(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [tick]);

  const refresh = () => setTick(t => t + 1);
  return { stats, loading, refresh };
}

// Reproducción de la circulación en planta — franja horaria 08:00–22:00.
function usePlanScrubber() {
  const [pct, setPct]         = useState(46);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setPct((p) => (p >= 100 ? 0 : p + 1)), 220);
    return () => clearInterval(id);
  }, [playing]);
  const totalMin = 14 * 60; // 08:00–22:00
  const mins = Math.round((pct / 100) * totalMin);
  const label = `${String(8 + Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
  return { pct, setPct, playing, setPlaying, label };
}

// ── Helpers ───────────────────────────────────────────────────────────────
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
function lighten(hex, amt) {
  const h = hex.replace("#", "");
  const num = parseInt(h, 16);
  const r = Math.min(255, ((num >> 16) & 255) + Math.round(255 * amt));
  const g = Math.min(255, ((num >> 8) & 255) + Math.round(255 * amt));
  const b = Math.min(255, (num & 255) + Math.round(255 * amt));
  return `rgb(${r}, ${g}, ${b})`;
}

// ── RegistersPanel ────────────────────────────────────────────────────────
function RegistersPanel({ registers, view = "now", onViewChange = () => {} }) {
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
          const color = r.status === "warn" ? "var(--warn)" : r.status === "idle" ? "var(--fg-3)" : "var(--pos-soft)";
          return (
            <div key={r.id} style={{ padding: "10px", border: "1px solid var(--line)", borderRadius: "var(--radius-lg)", background: "var(--bg-3)", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ position: "relative", width: 28, height: 28, flexShrink: 0 }}>
                <RadialGauge value={pct} size={28} stroke={3} color={color} track="var(--bg-4)" />
                <span className="mono" style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", fontSize: 9, fontWeight: 700, color: "var(--fg-1)" }}>{r.queue}</span>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 14.5, fontWeight: 500 }}>{r.name}</span>
                    {r.status === "warn" && <span style={{ fontSize: 11.5, color: "var(--warn)", textTransform: "uppercase", letterSpacing: ".08em" }}>saturada</span>}
                    {r.status === "idle" && <span style={{ fontSize: 11.5, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: ".08em" }}>libre</span>}
                  </div>
                  <div className="mono" style={{ fontSize: 14, color: "var(--fg-1)" }}>
                    <span style={{ color: "var(--fg-3)" }}>cola </span>
                    <b style={{ color: "var(--fg-0)", fontWeight: 600 }}>{r.queue}</b>
                    <span style={{ color: "var(--fg-3)" }}> · espera </span>
                    <b style={{ color: "var(--fg-0)", fontWeight: 600 }}>{r.wait ? fmtMMSS(r.wait) : "—"}</b>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 10, padding: "8px 10px", borderRadius: "var(--radius-md)", background: "var(--bg-3)", border: "1px solid var(--line)", display: "flex", justifyContent: "space-between", fontSize: 12.5, color: "var(--fg-2)" }}>
        <span>Tiempo promedio global</span>
        <span className="mono" style={{ color: "var(--fg-0)", fontWeight: 600 }}>2:18</span>
      </div>
    </div>
  );
}

// ── Page metadata ─────────────────────────────────────────────────────────
const PAGE_META = {
  dashboard: { crumb: ["Dashboard", "Operativo"] },
  heatmap:   { crumb: ["Análisis", "Mapa de calor"] },
  tracking:  { crumb: ["Análisis", "Tracking de personas"] },
  stock:     { crumb: ["Monitoreo", "Control de stock"] },
  reports:   { crumb: ["Análisis", "Reportes 2.0"] },
  "reports-legacy": { crumb: ["Análisis", "Reportes (versión anterior)"] },
  alerts:    { crumb: ["Monitoreo", "Alertas"] },
  settings:  { crumb: ["Sistema", "Configuración"] },
};

// ── Dashboard page ────────────────────────────────────────────────────────
function DashboardPage({ t, onNavigate }) {
  const toast = useToast();
  const [range, setRange]           = useState("hoy");
  const [alertFilter, setAlertFilter] = useState("all");
  const [registerView, setRegisterView] = useState("now");
  const [vizMode, setVizMode]       = useState("heat");
  const [heatOp, setHeatOp]         = useState(80);
  const [activeRoi, setActiveRoi]   = useState("all");

  const { stats, loading, refresh } = useApiStats();
  const { pct: scrubPct, setPct: setScrubPct, playing, setPlaying, label: scrubLabel } = usePlanScrubber();
  const people = useLivePeopleCount(23);
  const alerts = useLiveAlerts(8);
  const { zonas: zonasPermanencia, porTipo: zonasPorTipo, loading: loadingZonas } = useZonasPermanencia();
  const { pico: horaPico } = useHoraPico();

  const activeAlerts = alerts.filter((a) => Date.now() - a.ts < 30 * 60 * 1000);
  const criticalCount = activeAlerts.filter((a) => a.sev === "critical").length;

  const filteredAlerts = alerts.filter(a => {
    if (alertFilter === "critical") return a.sev === "critical";
    if (alertFilter === "today")    return Date.now() - a.ts < 24 * 60 * 60 * 1000;
    return true;
  }).slice(0, 6);

  // Ordenadas por permanencia promedio real, mayor a menor (mismo criterio
  // visual que antes tenía el ranking hardcodeado de STORE_ZONES).
  const zonasOrdenadas = useMemo(
    () => [...zonasPermanencia].sort((a, b) => b.permanencia_promedio_min - a.permanencia_promedio_min),
    [zonasPermanencia]
  );

  return (
    <main className="content">
      <div className="page-head">
        <div>
          <h1>Operaciones — Strumia · Mendoza</h1>
          <p>Grabaciones analizadas · tiempo real no disponible · modo offline</p>
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

      <KpiTicker items={[
        {
          label: "Foot Traffic", Ico: IcoUsers,
          value: stats ? stats.personas_unicas : "—", unit: "unique",
          trend: "up", delta: "+8.4%",
          sub: stats ? `${people} en tienda ahora · ${stats.fuente.toUpperCase()}` : "cargando…",
        },
        {
          label: "Dwell Time", Ico: IcoClock,
          value: stats ? stats.permanencia_promedio_min : "—", unit: "min avg",
          trend: "down", delta: "-3.1%",
          sub: stats ? `máx ${stats.permanencia_maxima_min} min` : "cargando…",
        },
        {
          label: "Active Alerts", Ico: IcoAlert,
          value: activeAlerts.length, unit: `· ${criticalCount} crit`,
          trend: criticalCount > 0 ? "down" : "flat", delta: criticalCount > 0 ? `${criticalCount} críticas` : "estable",
          sub: "source: recording",
        },
        {
          label: "Hora Pico", Ico: IcoTrend,
          value: horaPico ? `${String(horaPico.hora_inicio).padStart(2, "0")}–${String((horaPico.hora_fin + 1) % 24).padStart(2, "0")}` : "—",
          unit: horaPico ? "hs" : "",
          trend: "flat",
          delta: horaPico ? `${horaPico.promedio} pers. simult.` : "sin datos",
          sub: horaPico ? `franja habitual · ${horaPico.dia}` : "cargando…",
        },
      ]} />

      <div className="console-grid">
        <div className="panel console-plan">
          <div className="panel-head">
            <div>
              <div className="panel-title"><span className="ico"><IcoHeat /></span>Consola espacial — circulación en planta</div>
              <div className="panel-sub" style={{ marginTop: 3, marginBottom: 0 }}>Strumia · Mendoza — planta baja</div>
            </div>
            <button className="iconbtn" onClick={() => onNavigate("heatmap")}><IcoExpand /></button>
          </div>

          <div className="console-plan-stage">
            <div className="console-plan-canvas">
              <div className="plan-layers">
                {[["heat", "Calor"], ["vectors", "Trayectorias"], ["zones", "Zonas"]].map(([k, l]) => (
                  <button key={k} className={vizMode === k ? "on" : ""} onClick={() => setVizMode(k)}>{l}</button>
                ))}
              </div>
              <div className="plan-opacity">
                <span>OPAC.</span>
                <input type="range" min={20} max={100} step={5} value={heatOp}
                  onChange={e => setHeatOp(+e.target.value)} />
                <span className="mono" style={{ width: 26, textAlign: "right" }}>{heatOp}%</span>
              </div>
              <FloorPlan mode={vizMode} opacity={heatOp} roiFilter={activeRoi} zonasReales={zonasPorTipo} />
            </div>
          </div>

          <div className="plan-scrubber">
            <button className="plan-scrub-btn" onClick={() => setPlaying(p => !p)} title={playing ? "Pausar" : "Reproducir"}>
              {playing ? <IcoPause style={{ width: 10, height: 10 }} /> : <IcoPlay style={{ width: 10, height: 10 }} />}
            </button>
            <span className="plan-scrub-time mono">{scrubLabel}</span>
            <div className="plan-scrub-track">
              <input type="range" min={0} max={100} value={scrubPct} onChange={e => setScrubPct(+e.target.value)} />
            </div>
            <span className="plan-scrub-range mono">08:00–22:00</span>
            <div className="seg">
              {[["all", "Todo"], ["entry", "Entrada"], ["checkout", "Caja"], ["aisles", "Góndolas"]].map(([k, l]) => (
                <button key={k} className={activeRoi === k ? "on" : ""} onClick={() => setActiveRoi(k)}>{l}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="console-side">
          <div className="panel">
            <div className="panel-head">
              <div className="panel-title">Analítica de zonas (ROI)</div>
              <span className="mono" style={{ fontSize: 11.5, color: "var(--fg-3)" }}>real · trayectorias</span>
            </div>
            {loadingZonas && (
              <div style={{ padding: "20px 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12.5 }}>Cargando…</div>
            )}
            {!loadingZonas && zonasOrdenadas.length === 0 && (
              <div style={{ padding: "20px 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12.5 }}>Sin datos de permanencia todavía.</div>
            )}
            {!loadingZonas && zonasOrdenadas.length > 0 && (
              <>
                <div className="roi-list">
                  {zonasOrdenadas.map((z) => {
                    const roi = ZONA_ROI[z.tipo] || { label: z.nombre, tint: "100,116,139" };
                    return (
                      <div key={z.tipo} className="roi-row">
                        <span className="roi-dot" style={{ background: `rgb(${roi.tint})` }} />
                        <span className="roi-label">{roi.label}</span>
                        <span className="roi-dwell mono">{z.permanencia_promedio_min.toFixed(1)}m</span>
                        <div className="roi-bar">
                          <span style={{ width: `${z.pct}%`, background: `rgb(${roi.tint})` }} />
                        </div>
                        <span className="roi-pct mono">{z.pct}%</span>
                      </div>
                    );
                  })}
                </div>
                <div className="roi-foot">
                  {zonasOrdenadas.reduce((a, z) => a + z.visitantes, 0)} visitantes distintos considerados · dwell time promedio y % de afluencia por zona
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="row2">
        <div className="panel">
          <div className="panel-head">
            <div>
              <div className="panel-title">
                <span className="ico"><IcoAlert /></span>
                Alertas recientes
                <span style={{ marginLeft: 6, padding: "1px 6px", borderRadius: "var(--radius-sm)", fontSize: 11.5, background: "var(--bg-3)", color: "var(--fg-3)", fontWeight: 500 }} className="mono">{filteredAlerts.length}</span>
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
            <div style={{ padding: "40px 0", textAlign: "center", color: "var(--fg-3)", fontSize: 14 }}>No hay alertas en este filtro.</div>
          ) : (
            <AlertsFeed alerts={filteredAlerts} />
          )}
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--line-soft)", textAlign: "center" }}>
            <button onClick={() => onNavigate("alerts")} style={{ appearance: "none", border: 0, background: "transparent", color: "var(--brand-soft)", fontSize: 12.5, cursor: "default", padding: "3px 8px", borderRadius: "var(--radius-sm)" }}>
              Ver todas las alertas →
            </button>
          </div>
        </div>

        <RegistersPanel registers={REGISTERS_INITIAL} view={registerView} onViewChange={setRegisterView} />
      </div>
    </main>
  );
}

// ── App Shell ─────────────────────────────────────────────────────────────
function AppShell({ t, setTweak, page, setPage, now }) {
  const toast = useToast();
  const alerts = useLiveAlerts(8);
  const activeAlerts = alerts.filter((a) => Date.now() - a.ts < 30 * 60 * 1000);
  const criticalCount = activeAlerts.filter((a) => a.sev === "critical").length;

  const [branchOpen, setBranchOpen] = useState(false);
  const [notifOpen, setNotifOpen]   = useState(false);
  const [camOpen, setCamOpen]       = useState(false);
  const [activeCam, setActiveCam]   = useState(null); // null = todas
  const branchRef = useRef(null);
  const notifRef  = useRef(null);
  const camRef    = useRef(null);

  const CAMERAS = [
    { id: 1, label: "CAM-01", zone: "Entrada",    status: "live"    },
    { id: 2, label: "CAM-02", zone: "Góndolas",   status: "live"    },
    { id: 3, label: "CAM-03", zone: "Caja frente",status: "live"    },
    { id: 4, label: "CAM-04", zone: "Caja lateral",status:"live"    },
  ];
  const activeCamObj = CAMERAS.find(c => c.id === activeCam);

  useEffect(() => {
    const handler = (e) => {
      if (branchRef.current && !branchRef.current.contains(e.target)) setBranchOpen(false);
      if (notifRef.current  && !notifRef.current.contains(e.target))  setNotifOpen(false);
      if (camRef.current    && !camRef.current.contains(e.target))    setCamOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const crumb = PAGE_META[page]?.crumb || ["—", "—"];

  const renderPage = () => {
    switch (page) {
      case "alerts":   return <AlertsPage />;
      case "reports":  return <ReportsV2Page onNavigate={setPage} />;
      case "reports-legacy": return <ReportsLegacyPage onNavigate={setPage} />;
      case "heatmap":  return <HeatmapPage />;
      case "tracking": return <TrackingPage />;
      case "stock":    return <StockPage />;
      case "settings": return <SettingsPage />;
      default:         return <DashboardPage t={t} onNavigate={setPage} />;
    }
  };

  return (
    <div className="app">
      <Sidebar active={page === "reports-legacy" ? "reports" : page} alertCount={activeAlerts.length} onNavigate={setPage} />

      <div className="main">
        <header className="topbar">
          <div className="crumb">
            <IcoHome style={{ width: 18, height: 18 }} />
            <b>{crumb[0]}</b>
            <IcoChev style={{ width: 12, height: 12 }} />
            <span>{crumb[1]}</span>
          </div>

          <div ref={branchRef} style={{ position: "relative" }}>
            <button className="branch-sel" onClick={() => setBranchOpen(o => !o)}
              style={{ appearance: "none", border: "1px solid var(--line)" }}>
              <span className="dot" />
              <span style={{ color: "var(--fg-3)", fontSize: 12, textTransform: "uppercase", letterSpacing: ".08em", marginRight: 4 }}>Sucursal</span>
              <b style={{ color: "var(--fg-0)", fontWeight: 500 }}>Strumia — Mendoza</b>
              <IcoDown style={{ width: 14, height: 14, color: "var(--fg-3)", marginLeft: 4 }} />
            </button>
            {branchOpen && (
              <div className="dropdown">
                <div className="dd-head">Sucursales activas</div>
                {[
                  { name: "Strumia — Mendoza", status: "live",    active: true },
                  { name: "Centro — Córdoba",  status: "offline" },
                  { name: "Norte — Bs. As.",   status: "offline" },
                ].map(b => (
                  <button key={b.name} className={`dd-item ${b.active ? "active" : ""}`}
                    onClick={() => { setBranchOpen(false); if (!b.active) toast(`Cambiando a ${b.name}…`, { kind: "info" }); }}>
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

          {/* Camera selector */}
          <div className="topbar-sep" />
          <div ref={camRef} style={{ position: "relative" }}>
            <button className="cam-sel-btn" onClick={() => setCamOpen(o => !o)}>
              <IcoCam style={{ width: 13, height: 13, color: "var(--fg-3)" }} />
              {activeCamObj ? (
                <span className="mono" style={{ fontSize: 13 }}>{activeCamObj.label}</span>
              ) : (
                <span style={{ fontSize: 13, color: "var(--fg-2)" }}>Todas las cámaras</span>
              )}
              <span className="cam-chip live">
                <span className="live-dot" />
                4 LIVE
              </span>
              <IcoDown style={{ width: 12, height: 12, color: "var(--fg-3)" }} />
            </button>
            {camOpen && (
              <div className="dropdown" style={{ minWidth: 240 }}>
                <div className="dd-head">Seleccionar cámara</div>
                <button
                  className={`dd-item${activeCam === null ? " active" : ""}`}
                  onClick={() => { setActiveCam(null); setCamOpen(false); }}
                >
                  <IcoCam style={{ width: 13, height: 13, color: "var(--fg-3)" }} />
                  <span style={{ flex: 1, textAlign: "left" }}>Todas las cámaras</span>
                  {activeCam === null && <IcoCheck size={12} stroke={2.4} />}
                </button>
                {CAMERAS.map(cam => (
                  <button
                    key={cam.id}
                    className={`dd-item${activeCam === cam.id ? " active" : ""}`}
                    onClick={() => { setActiveCam(cam.id); setCamOpen(false); }}
                  >
                    <span className={`cam-chip ${cam.status}`} style={{ fontSize: 11 }}>
                      {cam.status === "live" && <span className="live-dot" />}
                      {cam.label}
                    </span>
                    <div style={{ flex: 1, textAlign: "left" }}>
                      <div style={{ fontSize: 14, color: "var(--fg-0)" }}>{cam.label}</div>
                      <div style={{ fontSize: 12, color: "var(--fg-3)" }}>{cam.zone}</div>
                    </div>
                    {activeCam === cam.id && <IcoCheck size={12} stroke={2.4} />}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="topbar-spacer" />

          <div className="cam-status">
            <IcoCam style={{ width: 13, height: 13 }} />
            <b>4 cámaras</b>
            <span style={{ color: "var(--fg-3)" }}>·</span>
            <span style={{ color: "var(--fg-3)", fontSize: 12, textTransform: "uppercase", letterSpacing: ".08em" }}>grabación</span>
          </div>

          <div ref={notifRef} style={{ position: "relative" }}>
            <button className="iconbtn" onClick={() => setNotifOpen(o => !o)} style={{ position: "relative" }}>
              <IcoBell />
              {criticalCount > 0 && (
                <span style={{ position: "absolute", top: -2, right: -2, width: 7, height: 7, borderRadius: "50%", background: "var(--alert)", outline: "2px solid var(--bg-0)" }} />
              )}
            </button>
            {notifOpen && (
              <div className="dropdown" style={{ width: 320, right: 0, left: "auto" }}>
                <div className="dd-head">Notificaciones <span className="mono" style={{ color: "var(--fg-3)", fontWeight: 400 }}>· {activeAlerts.length}</span></div>
                {activeAlerts.slice(0, 4).map(a => {
                  const secs = Math.floor((Date.now() - a.ts) / 1000);
                  const rel = secs < 60 ? `${secs}s` : `${Math.floor(secs/60)}m`;
                  return (
                    <div key={a.id} className="dd-item" onClick={() => { setNotifOpen(false); setPage("alerts"); }}>
                      <span className={`alert-dot ${a.sev}`} style={{ marginTop: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 14, color: "var(--fg-0)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.title}</div>
                        <div style={{ fontSize: 12, color: "var(--fg-3)" }} className="mono">hace {rel}</div>
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

        {renderPage()}
      </div>

      <TweaksPanel>
        <TweakSection label="Apariencia" />
        <TweakColor label="Color de acento" value={t.accent}
          options={["#4f68e5", "#fa98d1", "#359070", "#c68a3e"]}
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

// ── Root App ──────────────────────────────────────────────────────────────
export default function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [page, setPage] = useState("dashboard");
  const now = useClock();

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

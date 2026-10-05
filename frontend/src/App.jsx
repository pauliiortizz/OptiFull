import { useState, useEffect, useMemo, useRef } from 'react'
import { flushSync } from 'react-dom'
import {
  IcoUsers, IcoClock, IcoBell, IcoHeat, IcoAlert,
  IcoChev, IcoDown, IcoCheck, IcoSpinner,
  IcoPlay, IcoPause, IcoTrend, IcoHome,
} from './components/Icons'
import { Sparkline, KpiCard, StatTileRow } from './components/Sparkline'
import { FloorPlan } from './components/FloorPlan'
import { ReportMetrics } from './components/ReportMetrics'
import { useLiveAlerts } from './components/AlertsFeed'
import { ToastProvider, useToast, PageHeader } from './components/Toast'
import { Sidebar } from './components/Sidebar'
import {
  useTweaks, TweaksPanel, TweakSection,
  TweakSlider, TweakToggle, TweakColor, TweakRadio
} from './components/TweaksPanel'
import { AlertsPage } from './pages/SectionPages'
import {
  StockPage, SettingsPage
} from './pages/PagesHeatmapCameras'
import { ReportsV2Page } from './pages/ReportsV2Page'
import { LandingPage } from './pages/LandingPage'

// ── Simulated data ────────────────────────────────────────────────────────
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

// Ruteo mínimo basado en window.location.pathname -- el proyecto no usa
// react-router (la navegación interna del dashboard es un estado "page" en
// memoria, ver AppShell). Solo dos destinos reales de URL: "/" (landing) y
// todo lo demás (dashboard operativo en "/dashboard"). Flask (api/__init__.py)
// y el dev server de Vite ya devuelven index.html para cualquier ruta
// desconocida, así que refrescar "/dashboard" funciona en local y en prod.
function useRoute() {
  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  // Cross-fade nativo entre bienvenida y dashboard (View Transitions API) --
  // sin esto el cambio de "landing" a "dashboard" es un corte seco pese a
  // ser SPA; con esto se siente como una progresión de la misma interfaz,
  // no un salto a otra pantalla. Degrada con gracia donde no hay soporte
  // (Safari/Firefox actuales: navega igual, solo sin el fundido) y respeta
  // prefers-reduced-motion.
  const navigate = (to) => {
    const commit = () => {
      if (to !== window.location.pathname) window.history.pushState(null, "", to);
      setPath(to);
    };
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (document.startViewTransition && !reduced) {
      document.startViewTransition(() => flushSync(commit));
    } else {
      commit();
    }
  };
  return [path, navigate];
}

// Estado real de sincronización -- pulsa /api/health (mismo endpoint que usa
// Render para el healthcheck) en vez de un pulso puramente decorativo: el
// badge de la topbar refleja si la base responde, no una animación fija.
function useSystemHealth(intervalMs = 30000) {
  const [ok, setOk] = useState(true);
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    let cancelled = false;
    const check = () => {
      fetch("/api/health")
        .then((r) => r.json())
        .then((d) => { if (!cancelled) { setOk(d?.db === "ok"); setChecking(false); } })
        .catch(() => { if (!cancelled) { setOk(false); setChecking(false); } });
    };
    check();
    const id = setInterval(check, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [intervalMs]);
  return { ok, checking };
}

// Personas en tienda AHORA, de /api/en-tienda (clientes con deteccion reciente
// en sesiones abiertas -- analisis en vivo). Se refresca cada 5 s.
function useLivePeopleCount(intervalMs = 5000) {
  const [live, setLive] = useState({ total: null, enVivo: false });
  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      fetch("/api/en-tienda")
        .then((r) => r.json())
        .then((d) => { if (!cancelled) setLive({ total: d?.total ?? null, enVivo: !!d?.en_vivo }); })
        .catch(() => { if (!cancelled) setLive({ total: null, enVivo: false }); });
    };
    poll();
    const id = setInterval(poll, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [intervalMs]);
  return live;
}

// Calor real por zona, combinado entre camaras (ver /api/heatmap/plano y api/plano_calor.py).
// Alimenta el croquis de la tienda; null mientras carga o si falla (el plano no dibuja calor).
// ── Filtro de periodo del dashboard (Hoy / 7 dias / 30 dias / Personalizado) ─────
// Las fechas se calculan en el navegador (hora local del local) y se mandan al backend como ?desde=&hasta=.
// Afecta a Permanencia, Hora pico y la analitica de zonas. NO afecta a "Personas en tienda" (en vivo) ni al
// calor y las trayectorias del croquis (promedio de todos los dias, ver FloorPlan).
const fechaISO = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const fechaCorta = (iso) => iso.split("-").reverse().join("/");

function rangoDeFiltro(range, custom) {
  const hoy = new Date();
  const atras = (n) => { const d = new Date(hoy); d.setDate(d.getDate() - n); return fechaISO(d); };
  const fin = fechaISO(hoy);
  if (range === "7d")  return { desde: atras(6),  hasta: fin };
  if (range === "30d") return { desde: atras(29), hasta: fin };
  if (range === "custom") return { desde: custom.desde || fin, hasta: custom.hasta || fin };
  return { desde: fin, hasta: fin };
}

function etiquetaRango(range, { desde, hasta }) {
  if (range === "hoy") return `Hoy · ${fechaCorta(hasta)}`;
  if (range === "7d")  return `Últimos 7 días · ${fechaCorta(desde)} – ${fechaCorta(hasta)}`;
  if (range === "30d") return `Últimos 30 días · ${fechaCorta(desde)} – ${fechaCorta(hasta)}`;
  return desde === hasta ? fechaCorta(desde) : `${fechaCorta(desde)} – ${fechaCorta(hasta)}`;
}

const qRango = ({ desde, hasta }) => `desde=${desde}&hasta=${hasta}`;

function usePlanoCalor(intervalMs = 60000, tick = 0) {
  const [calor, setCalor] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const cargar = () => {
      fetch("/api/heatmap/plano")
        .then((r) => r.json())
        .then((d) => { if (!cancelled) setCalor(d?.zonas ? d : null); })
        .catch(() => { if (!cancelled) setCalor(null); });
    };
    cargar();
    const id = setInterval(cargar, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [intervalMs, tick]);
  return calor;
}

// Permanencia real por zona (Caja / Góndolas / Salón) — ver
// /reportes/permanencia-por-zona en frontend/api/reportes.py. Alimenta tanto
// el numero superpuesto en el plano (modo "Zonas" de FloorPlan) como los dos
// paneles laterales de la consola espacial, reemplazando los valores
// hardcodeados que tenía antes (STORE_ZONES.occ / GONDOLA_AISLES.dwellMin).
function useZonasPermanencia(rango, tick = 0) {
  const [zonas, setZonas]     = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/reportes/permanencia-por-zona?${qRango(rango)}`)
      .then(r => r.json())
      .then(d => { if (!cancelled) { setZonas(d?.zonas || []); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [rango.desde, rango.hasta, tick]);
  // Mapa tipo -> fila, para que FloorPlan pueda mirar cada ROI por su tipoReal.
  const porTipo = useMemo(() => Object.fromEntries(zonas.map(z => [z.tipo, z])), [zonas]);
  return { zonas, porTipo, loading };
}

// Hora de mayor ocupación real (promedio de clientes simultáneos), ya
// calculada por /reportes/congestion-horaria a partir de la tabla 'visitas'
// -- ver reportes.py: agrupa por dia-de-semana/hora y detecta el rango
// horario que es maximo local y significativo (>=60% del pico de ese dia).
// Alimenta el KPI "Hora Pico", que reemplaza al placeholder "Live Feed: N/A".
function useHoraPico(rango, tick = 0) {
  const [pico, setPico]       = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/reportes/congestion-horaria?${qRango(rango)}`)
      .then(r => r.json())
      .then(d => { if (!cancelled) { setPico(d?.pico || null); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [rango.desde, rango.hasta, tick]);
  return { pico, loading };
}

function useApiStats(rango, tick = 0) {
  const [stats, setStats]     = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/stats?${qRango(rango)}`)
      .then(r => r.json())
      .then(data => { if (!cancelled) { setStats(data); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [rango.desde, rango.hasta, tick]);

  return { stats, loading };
}

// Reproducción de la circulación en planta — franja horaria 08:00–22:00.
// Datos con hora para reproducir el calor del croquis (ver /api/heatmap/plano/tiempo): promedio de
// TODOS los dias, de las camaras fuente combinadas (Salon = camara 2; Gondolas y Caja = camara 4).
function usePlanoTiempo(tick = 0) {
  const [data, setData] = useState(null);
  const [cargando, setCargando] = useState(true);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/heatmap/plano/tiempo" + (tick ? "?refrescar=1" : ""))
      .then((r) => r.json())
      .then((d) => { if (!cancelled) { setData(d?.zonas ? d : null); setCargando(false); } })
      .catch(() => { if (!cancelled) { setData(null); setCargando(false); } });
    return () => { cancelled = true; };
  }, [tick]);
  return { data, cargando };
}

// Recorridos de clientes de las camaras fuente (ver /api/heatmap/plano/flujo): se agrupan en el croquis
// para dibujar las rutas frecuentes. null mientras carga o si falla.
function usePlanoFlujo(tick = 0) {
  const [flujo, setFlujo] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/heatmap/plano/flujo" + (tick ? "?refrescar=1" : ""))
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setFlujo(d?.zonas ? d : null); })
      .catch(() => { if (!cancelled) setFlujo(null); });
    return () => { cancelled = true; };
  }, [tick]);
  return flujo;
}

// Reproductor del croquis: el minuto del dia avanza solo mientras 'playing', dentro del rango horario de
// los datos. Arranca en la hora actual; al llegar al final se detiene, y si se da play desde el final,
// vuelve a empezar.
const PASO_REPRODUCCION_MIN = 5, TICK_REPRODUCCION_MS = 900;   // 5 min del dia cada 0,9 s (~5,5 min por segundo): lo bastante lento para ver como se dibujan las flechas
function usePlanScrubber(rango) {
  const desde = rango?.desde ?? 8 * 60, hasta = rango?.hasta ?? 22 * 60;
  const ahora = new Date();
  const inicio = Math.min(hasta, Math.max(desde, Math.round((ahora.getHours() * 60 + ahora.getMinutes()) / 5) * 5));
  const [minuto, setMinuto] = useState(inicio);
  const [playing, setPlaying] = useState(false);
  // Al cambiar el rango (llegan los datos): se pausa y se muestra la hora actual.
  useEffect(() => { setMinuto(inicio); setPlaying(false); }, [desde, hasta]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setMinuto((m) => {
        const siguiente = m + PASO_REPRODUCCION_MIN;
        if (siguiente >= hasta) { setPlaying(false); return hasta; }
        return siguiente;
      });
    }, TICK_REPRODUCCION_MS);
    return () => clearInterval(id);
  }, [playing, hasta]);
  const alternar = () => {
    if (!playing && minuto >= hasta) setMinuto(desde);
    setPlaying((p) => !p);
  };
  const hh = (m) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  return { minuto, setMinuto, playing, alternar, desde, hasta, label: hh(minuto), labelDesde: hh(desde), labelHasta: hh(hasta === 1440 ? 1439 : hasta) };
}

// ── Helpers ───────────────────────────────────────────────────────────────
function fmtClock(d) {
  return d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}
function fmtDate(d) {
  return d.toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" });
}
function lighten(hex, amt) {
  const h = hex.replace("#", "");
  const num = parseInt(h, 16);
  const r = Math.min(255, ((num >> 16) & 255) + Math.round(255 * amt));
  const g = Math.min(255, ((num >> 8) & 255) + Math.round(255 * amt));
  const b = Math.min(255, (num & 255) + Math.round(255 * amt));
  return `rgb(${r}, ${g}, ${b})`;
}

// Única sucursal con datos reales hoy (ver .env / Supabase); las demás
// existen en la UI como "offline" -- seleccionarlas no cambia datos porque
// no hay backend detrás todavía (ver el toast en su onClick más abajo).
const BRANCHES = [
  { id: "strumia", name: "Strumia — Mendoza", status: "live" },
  { id: "centro",  name: "Centro — Córdoba",  status: "offline" },
  { id: "norte",   name: "Norte — Bs. As.",   status: "offline" },
];

// ── Sync badge ────────────────────────────────────────────────────────────
function SyncBadge() {
  const { ok, checking } = useSystemHealth();
  const label = checking ? "Conectando…" : ok ? "Sincronizado" : "Reconectando…";
  return (
    <div className={`sync-badge${!checking && !ok ? " down" : ""}`} role="status" aria-live="polite">
      <span className="sync-dot" />
      <span>{label}</span>
    </div>
  );
}

// ── Page metadata ─────────────────────────────────────────────────────────
const PAGE_META = {
  dashboard: { crumb: ["Dashboard", "Operativo"] },
  stock:     { crumb: ["Monitoreo", "Control de stock"] },
  reports:   { crumb: ["Análisis", "Reportes"] },
  alerts:    { crumb: ["Monitoreo", "Alertas"] },
  settings:  { crumb: ["Sistema", "Configuración"] },
};

// ── Dashboard page ────────────────────────────────────────────────────────
function DashboardPage({ t }) {
  const [range, setRange]           = useState("hoy");
  const [custom, setCustom]         = useState(() => {   // rango personalizado: por defecto, los ultimos 7 dias
    const r = rangoDeFiltro("7d", {});
    return { desde: r.desde, hasta: r.hasta };
  });
  const [tickDatos, setTickDatos]   = useState(0);       // "Actualizar datos": recarga todo
  const rango = useMemo(() => rangoDeFiltro(range, custom), [range, custom]);
  const refresh = () => setTickDatos((t) => t + 1);
  const [vizMode, setVizMode]       = useState("heat");
  const [heatOp, setHeatOp]         = useState(80);
  const [activeRoi, setActiveRoi]   = useState("all");

  const { stats, loading: loadingStats } = useApiStats(rango, tickDatos);
  const [acumulado, setAcumulado] = useState(false);          // false = ultimos 30 min; true = acumulado hasta esa hora
  const { data: calorTiempo, cargando: cargandoTiempo } = usePlanoTiempo(tickDatos);
  const flujoPlano = usePlanoFlujo(tickDatos);
  const scrub = usePlanScrubber(calorTiempo?.rango);
  const { total: people, enVivo } = useLivePeopleCount();
  const alerts = useLiveAlerts(8);
  const { zonas: zonasPermanencia, porTipo: zonasPorTipo, loading: loadingZonas } = useZonasPermanencia(rango, tickDatos);
  const { pico: horaPico, loading: loadingPico } = useHoraPico(rango, tickDatos);
  const calorPlano = usePlanoCalor(60000, tickDatos);
  const loading = loadingStats || loadingZonas || loadingPico;

  const activeAlerts = alerts.filter((a) => Date.now() - a.ts < 30 * 60 * 1000);
  const criticalCount = activeAlerts.filter((a) => a.sev === "critical").length;

  // Ordenadas por permanencia promedio real, mayor a menor (mismo criterio
  // visual que antes tenía el ranking hardcodeado de STORE_ZONES).
  const zonasOrdenadas = useMemo(
    () => [...zonasPermanencia].sort((a, b) => b.permanencia_promedio_min - a.permanencia_promedio_min),
    [zonasPermanencia]
  );

  return (
    <main className="content">
      <PageHeader
        title="Operaciones — Strumia · Mendoza"
        subtitle={`${enVivo ? "Cámaras en vivo · análisis en curso" : "Sin análisis en vivo · mostrando datos guardados"} · ${etiquetaRango(range, rango)}`}
        right={
          <>
            <button className="btn-sec" onClick={refresh} disabled={loading} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <IcoSpinner style={{ width: 13, height: 13, animation: loading ? "spin 1s linear infinite" : "none" }} />
              {loading ? "Actualizando…" : "Actualizar datos"}
            </button>
            <div className="range-tabs">
              {[["hoy","Hoy"],["7d","7 días"],["30d","30 días"],["custom","Personalizado"]].map(([k,l]) => (
                <button key={k} className={range === k ? "on" : ""} onClick={() => setRange(k)}>{l}</button>
              ))}
            </div>
            {range === "custom" && (
              <div className="range-custom">
                <label>Desde
                  <input type="date" className="select-input" value={custom.desde} max={custom.hasta || fechaISO(new Date())}
                    onChange={(e) => e.target.value && setCustom((c) => ({ ...c, desde: e.target.value }))} />
                </label>
                <label>Hasta
                  <input type="date" className="select-input" value={custom.hasta} min={custom.desde} max={fechaISO(new Date())}
                    onChange={(e) => e.target.value && setCustom((c) => ({ ...c, hasta: e.target.value }))} />
                </label>
              </div>
            )}
          </>
        }
      />

      <StatTileRow items={[
        {
          label: "Personas en tienda", Ico: IcoUsers,
          value: enVivo ? (people ?? 0) : "—", unit: "ahora",
          sub: enVivo ? "en vivo · cámaras" : "sin cámara en vivo",
        },
        {
          label: "Permanencia", Ico: IcoClock,
          value: stats && stats.personas_validas > 0 ? stats.permanencia_promedio_min : "—", unit: "min prom.",
          sub: !stats ? "cargando…" : stats.personas_validas > 0 ? `máx ${stats.permanencia_maxima_min} min · ${stats.personas_validas} personas` : "sin datos en este período",
        },
        {
          label: "Alertas activas", Ico: IcoAlert,
          value: activeAlerts.length, unit: `· ${criticalCount} crít.`,
          trend: criticalCount > 0 ? "down" : "flat", delta: criticalCount > 0 ? `${criticalCount} críticas` : "estable",
          sub: "fuente: grabación",
        },
        {
          label: "Hora pico", Ico: IcoTrend,
          value: horaPico ? `${String(horaPico.hora_inicio).padStart(2, "0")}–${String((horaPico.hora_fin + 1) % 24).padStart(2, "0")}` : "—",
          unit: horaPico ? "hs" : "",
          trend: "flat",
          delta: horaPico ? `${horaPico.promedio} pers. simult.` : "sin datos",
          sub: horaPico ? `${horaPico.dia}` : loadingPico ? "cargando…" : "sin datos en este período",
        },
      ]} />

      <ReportMetrics stats={stats} onStatsChange={refresh}>
        {({ side, wide }) => (
          <>
      <div className="console-grid">
        <div className="panel console-plan">
          <div className="panel-head">
            <div>
              <div className="panel-title"><span className="ico"><IcoHeat /></span>Consola espacial — circulación en planta</div>
              <div className="panel-sub" style={{ marginTop: 3, marginBottom: 0 }}>Strumia · Mendoza — planta baja</div>
            </div>
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
              <FloorPlan mode={vizMode} opacity={heatOp} roiFilter={activeRoi} zonasReales={zonasPorTipo} calorReal={calorPlano}
                calorTiempo={calorTiempo} minuto={scrub.minuto} acumulado={acumulado} flujo={flujoPlano} />
            </div>
          </div>

          <div className="plan-scrubber">
            <button className="plan-scrub-btn" onClick={scrub.alternar} title={scrub.playing ? "Pausar" : "Reproducir"}>
              {scrub.playing ? <IcoPause style={{ width: 10, height: 10 }} /> : <IcoPlay style={{ width: 10, height: 10 }} />}
            </button>
            <span className="plan-scrub-time mono">{scrub.label}</span>
            <div className="plan-scrub-track">
              <input type="range" min={scrub.desde} max={scrub.hasta} step={5} value={scrub.minuto}
                onChange={e => { scrub.setMinuto(+e.target.value); }} />
            </div>
            <span className="plan-scrub-range mono">{scrub.labelDesde}–{scrub.labelHasta}</span>
            <div className="seg">
              {[["all", "Todo"], ["checkout", "Caja"], ["aisles", "Góndolas"]].map(([k, l]) => (
                <button key={k} className={activeRoi === k ? "on" : ""} onClick={() => setActiveRoi(k)}>{l}</button>
              ))}
            </div>
          </div>
          <div className="plan-timebar">
            <div className="seg">
              <button className={!acumulado ? "on" : ""} onClick={() => setAcumulado(false)}>Últimos 30 min</button>
              <button className={acumulado ? "on" : ""} onClick={() => setAcumulado(true)}>Acumulado hasta esa hora</button>
            </div>
            <span className="plan-timebar-note">
              {cargandoTiempo ? "Cargando…" : "Promedio de todos los días por hora · Salón: cámara 2 · Góndolas y Caja: cámara 4"}
            </span>
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
              <div style={{ padding: "20px 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12.5 }}>Sin datos de permanencia en este período.</div>
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
          {side}
        </div>
      </div>
            {wide}
          </>
        )}
      </ReportMetrics>
    </main>
  );
}

// ── App Shell ─────────────────────────────────────────────────────────────
function AppShell({ t, setTweak, page, setPage, now }) {
  const toast = useToast();
  const alerts = useLiveAlerts(8);
  const activeAlerts = alerts.filter((a) => Date.now() - a.ts < 30 * 60 * 1000);
  const criticalCount = activeAlerts.filter((a) => a.sev === "critical").length;

  const [menuAbierto, setMenuAbierto] = useState(false);   // cajon del menu lateral (solo celular)
  const [branchOpen, setBranchOpen] = useState(false);
  const [notifOpen, setNotifOpen]   = useState(false);
  const [activeBranch, setActiveBranch] = useState(BRANCHES[0]);
  const branchRef = useRef(null);
  const notifRef  = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (branchRef.current && !branchRef.current.contains(e.target)) setBranchOpen(false);
      if (notifRef.current  && !notifRef.current.contains(e.target))  setNotifOpen(false);
    };
    document.addEventListener("mousedown", handler);
    const alEscape = (e) => { if (e.key === "Escape") setMenuAbierto(false); };
    document.addEventListener("keydown", alEscape);
    return () => { document.removeEventListener("mousedown", handler); document.removeEventListener("keydown", alEscape); };
  }, []);

  const crumb = PAGE_META[page]?.crumb || ["—", "—"];

  const renderPage = () => {
    switch (page) {
      case "alerts":   return <AlertsPage />;
      case "reports":  return <ReportsV2Page onNavigate={setPage} />;
      case "stock":    return <StockPage />;
      case "settings": return <SettingsPage />;
      default:         return <DashboardPage t={t} />;
    }
  };

  return (
    <div className="app">
      <Sidebar active={page} alertCount={activeAlerts.length} onNavigate={setPage}
        mobileOpen={menuAbierto} onClose={() => setMenuAbierto(false)} />
      <div className={`side-backdrop${menuAbierto ? " on" : ""}`} onClick={() => setMenuAbierto(false)} aria-hidden="true" />

      <div className="main">
        <header className="topbar">
          <button type="button" className="iconbtn topbar-burger" aria-label="Abrir menú" onClick={() => setMenuAbierto(true)}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
              <path d="M3 5h12M3 9h12M3 13h12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
            </svg>
          </button>
          <nav className="crumb" aria-label="Ruta de navegación">
            <button type="button" className="crumb-seg crumb-root" onClick={() => setPage("dashboard")}>
              <IcoHome style={{ width: 15, height: 15 }} />
              <span>OptiFull</span>
            </button>
            <IcoChev className="crumb-sep" />
            <span ref={branchRef} style={{ position: "relative" }}>
              <button type="button" className="crumb-seg" onClick={() => setBranchOpen(o => !o)}>
                {activeBranch.name}
                <IcoDown style={{ width: 11, height: 11, color: "var(--glass-label-2)" }} />
              </button>
              {branchOpen && (
                <div className="dropdown">
                  <div className="dd-head">Sucursales activas</div>
                  {BRANCHES.map(b => (
                    <button key={b.id} className={`dd-item ${activeBranch.id === b.id ? "active" : ""}`}
                      onClick={() => {
                        setBranchOpen(false);
                        if (b.status === "offline") { toast(`${b.name} todavía no tiene cámaras conectadas`, { kind: "warn" }); return; }
                        setActiveBranch(b);
                      }}>
                      <span className={`dd-dot ${b.status}`} />
                      <span style={{ flex: 1, textAlign: "left" }}>{b.name}</span>
                      {activeBranch.id === b.id && <IcoCheck size={12} stroke={2.4} />}
                    </button>
                  ))}
                  <div className="dd-foot">
                    <button onClick={() => { setBranchOpen(false); toast("Agregar sucursal — fuera del alcance del prototipo", { kind: "warn" }); }}>
                      + Agregar sucursal
                    </button>
                  </div>
                </div>
              )}
            </span>
            <IcoChev className="crumb-sep" />
            <span className="crumb-seg crumb-static">{crumb[1]}</span>
          </nav>

          <span className="topbar-title">{crumb[1]}</span>

          <SyncBadge />

          <div className="topbar-spacer" />

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

        <footer className="legal-foot">
          © {new Date().getFullYear()} OptiFull. Todos los derechos reservados.
        </footer>
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
  const [route, navigate] = useRoute();

  useEffect(() => {
    document.documentElement.style.setProperty("--brand", t.accent);
    document.documentElement.style.setProperty("--brand-soft", lighten(t.accent, 0.18));
  }, [t.accent]);

  // "/" es la puerta de acceso; cualquier otra ruta (p. ej. "/dashboard")
  // aísla el operativo existente, que conserva su propia navegación interna
  // (sidebar / setPage) sin cambios.
  if (route === "/") {
    return <LandingPage onEnter={() => navigate("/dashboard")} />;
  }

  return (
    <ToastProvider>
      <AppShell t={t} setTweak={setTweak} page={page} setPage={setPage} now={now} />
    </ToastProvider>
  );
}

import { useEffect, useRef, useState } from 'react'
import { Logo } from '../components/Logo'
import imgDeteccion from '../assets/landing-deteccion.jpg'
import { IcoChev } from '../components/Icons'
import { ThemeToggle } from '../components/ThemeToggle'
import './LandingPage.css'

// Vistas del panel de demostración. La imagen de detección es una salida real
// del detector (YOLO) sobre un cuadro de una cámara de la tienda piloto, con las
// caras difuminadas por privacidad. Mapa de calor y métricas son datos reales
// del sistema (/api/heatmap/camara/4 y /api/stats).
const VISTAS = [
  { id: 'deteccion', t: 'Detección', cap: 'Detección de personas en caja — cámara de la tienda piloto, caras difuminadas.' },
  { id: 'calor',     t: 'Mapa de calor', cap: 'Mapa de calor real de la zona de cajas sobre un croquis ilustrativo (no es el plano exacto de la tienda).' },
  { id: 'metricas',  t: 'Métricas', cap: 'Permanencia de clientes en la tienda piloto.' },
];

// Experimento de validación: medimos clics y envíos con lo que haya cargado
// en la página (Microsoft Clarity o Google Analytics); si no hay ninguno,
// no hace nada. Los utm_* del link de origen viajan con el pedido de demo.
const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content'];
function track(evento) {
  try { window.clarity?.('event', evento); } catch { /* sin Clarity */ }
  try { window.gtag?.('event', evento); } catch { /* sin GA */ }
}
function leerUtm() {
  const q = new URLSearchParams(window.location.search);
  return Object.fromEntries(UTM_KEYS.map((k) => [k, q.get(k) || '']));
}

const ROLES = ['Dueño / franquiciado', 'Gerente de tienda', 'Jefe zonal / operaciones', 'Otro'];
const CAMARAS = ['1 a 3', '4 a 8', 'Más de 8', 'No sé'];
// Las opciones coinciden con lo que la sección "Qué resuelve" promete.
const PROBLEMAS = [
  { v: 'colas',     t: 'Colas en caja' },
  { v: 'faltantes', t: 'Faltantes de stock' },
  { v: 'picos',     t: 'Horarios pico y turnos' },
  { v: 'otro',      t: 'Otro' },
];

const RESUELVE = [
  { t: 'Colas en caja',
    d: 'Te avisa cuando la fila supera el límite que definas, para abrir otra caja antes de que el cliente se vaya.',
    ico: <><circle cx="6" cy="7" r="2.5" /><circle cx="12" cy="7" r="2.5" /><circle cx="18" cy="7" r="2.5" /><path d="M2 20c0-3 2-5 4-5s4 2 4 5M8 20c0-3 2-5 4-5s4 2 4 5M14 20c0-3 2-5 4-5s4 2 4 5" /></> },
  { t: 'Faltantes en góndola',
    d: 'Detecta estantes y heladeras que se están vaciando, para reponer antes de perder la venta.',
    ico: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 10h18M3 15h18M9 4v16" /></> },
  { t: 'Horarios pico',
    d: 'Mostrá a qué hora entra más gente y cuánto se queda, para armar los turnos del personal con datos.',
    ico: <path d="M3 20V10M9 20V4M15 20v-8M21 20v-5" /> },
];
const PASOS = [
  { t: 'Conectamos tus cámaras', d: 'Nos sumamos a las cámaras de seguridad que ya están instaladas. No hace falta comprar equipos.' },
  { t: 'El sistema mira por vos', d: 'Un modelo de visión cuenta personas, mide tiempos de espera y revisa el stock en góndola, todo el día.' },
  { t: 'Recibís alertas', d: 'Mirás todo en un panel desde el celular o la compu, con alertas cuando algo necesita atención.' },
];

// Cifras reales de /api/stats (mismo dato que consume el dashboard) para la
// prueba social. No comparte props con AppShell a propósito: esta página no
// depende de su árbol, así que consulta por su cuenta.
function useLandingStats(intervalMs = 30000) {
  const [stats, setStats] = useState(null);
  const [heat, setHeat] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetch("/api/stats").then((r) => r.json())
        .then((d) => { if (!cancelled) setStats(d); })
        .catch(() => {});
      fetch("/api/heatmap/camara/4").then((r) => r.json())
        .then((d) => { if (!cancelled && d?.imagen_url) setHeat(d.imagen_url); })
        .catch(() => {});
    };
    load();
    const id = setInterval(load, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [intervalMs]);
  return { stats, heat };
}

// Puerta de entrada de OptiFull (ruta "/"). Hoy funciona como landing del
// experimento de validación: un visitante nuevo entiende la propuesta y pide
// una demo (formulario -> POST /api/leads). Los clientes que ya usan el
// sistema entran por el link "Ya soy cliente" hacia "/dashboard".
export function LandingPage({ onEnter }) {
  const { stats, heat } = useLandingStats();
  const [vista, setVista] = useState('deteccion');
  // Rotación automática de las vistas: se detiene al elegir una pestaña a mano o
  // mientras el cursor / el foco está sobre el panel, y no corre con
  // prefers-reduced-motion.
  const [auto, setAuto] = useState(true);
  const [pausa, setPausa] = useState(false);
  useEffect(() => {
    if (!auto || pausa) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    const id = setInterval(() => {
      setVista((v) => VISTAS[(VISTAS.findIndex((x) => x.id === v) + 1) % VISTAS.length].id);
    }, 6000);
    return () => clearInterval(id);
  }, [auto, pausa]);
  const [envio, setEnvio] = useState('idle');   // idle | enviando | ok | error
  const [problema, setProblema] = useState('');
  const formRef = useRef(null);

  const irAlFormulario = () => {
    const reducido = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    formRef.current?.scrollIntoView({ behavior: reducido ? 'auto' : 'smooth', block: 'start' });
    formRef.current?.querySelector('input')?.focus({ preventScroll: true });
  };
  const pedirDemo = () => { track('cta_demo'); irAlFormulario(); };

  const enviar = (e) => {
    e.preventDefault();
    if (!problema) { setEnvio('error'); return; }
    const f = new FormData(e.currentTarget);
    setEnvio('enviando');
    fetch('/api/leads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nombre: f.get('nombre'), rol: f.get('rol'), contacto: f.get('contacto'),
        estacion: f.get('estacion'), camaras: f.get('camaras'), problema, ...leerUtm(),
      }),
    })
      .then((r) => { if (!r.ok) throw new Error('lead'); track('demo_enviada'); setEnvio('ok'); })
      .catch(() => setEnvio('error'));
  };

  return (
    <div className="landing">
      <div className="landing-frame">
        <header className="landing-head landing-in" style={{ animationDelay: '0ms' }}>
          <Logo className="landing-logo" />
          <nav className="landing-nav" aria-label="Secciones">
            <a href="#problemas">Qué resuelve</a>
            <a href="#como">Cómo funciona</a>
            <button type="button" className="landing-client-link" onClick={onEnter}>Ya soy cliente</button>
            <button type="button" className="btn-primary btn-compact" onClick={pedirDemo}>Pedir demo</button>
            <ThemeToggle />
          </nav>
        </header>

        <div className="landing-main">
          <main className="landing-body">
            {stats && (
              <div className="landing-preview landing-in" style={{ animationDelay: '40ms' }}>
                <span className="landing-preview-dot" />
                <span className="landing-preview-text">Ya funcionando en una YPF Full de Córdoba</span>
              </div>
            )}

            <h1 className="landing-title landing-in" style={{ animationDelay: '100ms' }}>
              Control operativo de su tienda YPF Full con las cámaras ya instaladas.
            </h1>

            <p className="landing-desc landing-in" style={{ animationDelay: '160ms' }}>
              OptiFull convierte las imágenes de sus cámaras en indicadores de atención en caja y
              disponibilidad de productos, para decidir con datos. <b>Sin inversión en hardware.</b>
            </p>

            <div className="landing-actions landing-in" style={{ animationDelay: '220ms' }}>
              <button type="button" className="btn-primary" onClick={pedirDemo}>
                Quiero una demo en mi tienda
                <span className="btn-primary-arrow"><IcoChev size={14} stroke={2.2} /></span>
              </button>
            </div>
          </main>

          <aside className="landing-visual landing-in" style={{ animationDelay: '200ms' }} aria-label="Demostración del sistema"
            onMouseEnter={() => setPausa(true)} onMouseLeave={() => setPausa(false)}
            onFocus={() => setPausa(true)} onBlur={() => setPausa(false)}>
            <div className="landing-tabs" role="tablist" aria-label="Vista de la demostración">
              {VISTAS.map((v) => (
                <button
                  key={v.id} type="button" role="tab" id={`tab-${v.id}`}
                  aria-selected={vista === v.id} aria-controls="landing-panel"
                  className={`landing-tab${vista === v.id ? ' on' : ''}`}
                  onClick={() => { setAuto(false); setVista(v.id); }}
                >{v.t}</button>
              ))}
            </div>

            <div className="landing-visual-frame" id="landing-panel" role="tabpanel" aria-labelledby={`tab-${vista}`}>
              {vista === 'deteccion' && (
                <img className="landing-shot" src={imgDeteccion}
                  alt="Cámara de la zona de cajas con dos personas detectadas y marcadas con un recuadro verde" />
              )}
              {vista === 'calor' && (heat
                ? <div className="landing-plan">
                    <svg viewBox="0 0 640 360" preserveAspectRatio="none" aria-hidden="true">
                      <defs>
                        <pattern id="plan-grid" width="20" height="20" patternUnits="userSpaceOnUse">
                          <path d="M20 0H0V20" fill="none" stroke="#dcd8c6" strokeWidth="0.6" />
                        </pattern>
                      </defs>
                      <rect width="640" height="360" fill="#f6f3e6" />
                      <rect width="640" height="360" fill="url(#plan-grid)" />
                      <g fill="#fffdf6" stroke="#8c8a7e" strokeWidth="1.4">
                        <rect x="14" y="14" width="612" height="332" rx="4" fill="none" strokeWidth="2.2" />
                        <rect x="150" y="190" width="150" height="26" rx="3" />
                        <rect x="150" y="150" width="30" height="40" rx="3" />
                        <rect x="360" y="56" width="140" height="16" rx="2" />
                        <rect x="360" y="86" width="140" height="16" rx="2" />
                        <rect x="360" y="116" width="140" height="16" rx="2" />
                        <rect x="360" y="226" width="140" height="16" rx="2" />
                        <rect x="360" y="256" width="140" height="16" rx="2" />
                        <rect x="586" y="40" width="26" height="280" rx="2" />
                        <rect x="40" y="250" width="70" height="44" rx="3" />
                        <rect x="130" y="270" width="70" height="44" rx="3" />
                        <rect x="40" y="60" width="90" height="20" rx="3" />
                      </g>
                      <rect x="10" y="150" width="8" height="60" fill="#f6f3e6" />
                      <g fontFamily="var(--font-metric)" fontSize="10" fill="#6b695f" letterSpacing="0.06em">
                        <text x="24" y="184">ENTRADA</text>
                        <text x="166" y="208">CAJAS</text>
                        <text x="372" y="48">GÓNDOLAS</text>
                        <text x="372" y="300">GÓNDOLAS</text>
                        <text x="46" y="52">CAFÉ</text>
                        <text x="44" y="310">MESAS</text>
                        <text x="560" y="336" textAnchor="end">HELADERAS</text>
                      </g>
                    </svg>
                    <img className="landing-plan-heat" src={heat}
                      alt="Mapa de calor de la zona de cajas sobre un croquis de la tienda: las zonas más cálidas concentran más presencia" />
                  </div>
                : <p className="landing-empty">El mapa de calor todavía no está disponible.</p>)}
              {vista === 'metricas' && (stats
                ? <div className="landing-kpis">
                    <div><b className="mono">{stats.personas_unicas}</b><span>personas detectadas</span></div>
                    <div><b className="mono">{stats.permanencia_promedio_min} min</b><span>permanencia promedio</span></div>
                    {Array.isArray(stats.distribucion) && (() => {
                      const max = Math.max(1, ...stats.distribucion.map((d) => d.count));
                      return (
                        <ul className="landing-bars" aria-label="Distribución de la permanencia">
                          {stats.distribucion.map((d) => (
                            <li key={d.rango}>
                              <span>{d.rango}</span>
                              <i style={{ width: `${(d.count / max) * 100}%` }} />
                              <b className="mono">{d.count}</b>
                            </li>
                          ))}
                        </ul>
                      );
                    })()}
                  </div>
                : <p className="landing-empty">Las métricas todavía no están disponibles.</p>)}
            </div>
            <p className="landing-visual-caption">{VISTAS.find((v) => v.id === vista).cap}</p>
          </aside>
        </div>

        <section id="problemas" className="landing-sec" aria-labelledby="problemas-t">
          <h2 id="problemas-t" className="landing-sec-title">Tres cosas que hoy te enterás tarde.</h2>
          <div className="landing-cards">
            {RESUELVE.map((r) => (
              <article key={r.t} className="landing-card">
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--brand)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{r.ico}</svg>
                <h3>{r.t}</h3>
                <p>{r.d}</p>
              </article>
            ))}
          </div>
        </section>

        <section id="como" className="landing-sec" aria-labelledby="como-t">
          <h2 id="como-t" className="landing-sec-title">Usás tus cámaras. Nosotros hacemos el resto.</h2>
          <ol className="landing-steps">
            {PASOS.map((p, i) => (
              <li key={p.t}>
                <span className="landing-step-n" aria-hidden="true">{i + 1}</span>
                <h3>{p.t}</h3>
                <p>{p.d}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="demo" className="landing-demo" aria-labelledby="demo-titulo">
          <div className="landing-demo-copy">
            <h2 id="demo-titulo" className="landing-demo-title">Probalo en tu tienda.</h2>
            <p className="landing-demo-sub">
              Te mostramos OptiFull funcionando con tus propias cámaras. Sin costo y sin compromiso.
              Te contactamos en menos de 48 h.
            </p>
          </div>

          {envio === 'ok' ? (
            <p className="landing-demo-ok" role="status">
              Recibimos tu pedido. Te escribimos en menos de 48 h para coordinar la demo en tu tienda.
            </p>
          ) : (
            <form className="landing-form" ref={formRef} onSubmit={enviar}>
              <label className="landing-field">
                <span>Nombre y apellido</span>
                <input name="nombre" required autoComplete="name" placeholder="Ej.: Laura Gómez" />
              </label>
              <label className="landing-field">
                <span>Tu rol</span>
                <select name="rol" required defaultValue="">
                  <option value="" disabled>Elegí una opción</option>
                  {ROLES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label className="landing-field">
                <span>Estación y localidad</span>
                <input name="estacion" required placeholder="Ej.: YPF Full Av. Colón, Córdoba" />
              </label>
              <label className="landing-field">
                <span>¿Cuántas cámaras tiene la tienda?</span>
                <select name="camaras" required defaultValue="">
                  <option value="" disabled>Elegí una opción</option>
                  {CAMARAS.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>

              <fieldset className="landing-field landing-field-wide">
                <legend>¿Qué te gustaría resolver primero?</legend>
                <div className="landing-chips">
                  {PROBLEMAS.map((p) => (
                    <label key={p.v} className={`landing-chip${problema === p.v ? ' on' : ''}`}>
                      <input
                        type="radio" name="problema" value={p.v}
                        checked={problema === p.v} onChange={() => setProblema(p.v)}
                      />
                      {p.t}
                    </label>
                  ))}
                </div>
              </fieldset>

              <label className="landing-field landing-field-wide">
                <span>WhatsApp o email</span>
                <input name="contacto" required autoComplete="email" placeholder="Para coordinar la demo" />
              </label>

              <div className="landing-form-foot landing-field-wide">
                <button type="submit" className="btn-primary" disabled={envio === 'enviando'}>
                  {envio === 'enviando' ? 'Enviando…' : 'Pedir demo'}
                </button>
                <small className="landing-form-note">Solo usamos tus datos para coordinar la demo.</small>
                {envio === 'error' && (
                  <span className="landing-form-error" role="alert">
                    {problema ? 'No se pudo enviar. Probá de nuevo en un momento.' : 'Elegí qué te gustaría resolver primero.'}
                  </span>
                )}
              </div>
            </form>
          )}
        </section>

        <footer className="landing-foot landing-in" style={{ animationDelay: '320ms' }}>
          <span>OptiFull — auditoría y monitoreo YPF Full</span>
          <span>© {new Date().getFullYear()} OptiFull. Todos los derechos reservados.</span>
        </footer>
      </div>
    </div>
  )
}

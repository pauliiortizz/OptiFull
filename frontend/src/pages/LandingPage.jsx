import { useEffect, useState } from 'react'
import logoCompleto from '../assets/optifull-logo.png'
import fotoEstacion from '../assets/landing-ypf-estacion.jpg'
import fotoAcceso from '../assets/landing-ypf-acceso.jpg'
import fotoLocal from '../assets/landing-ypf-local.jpg'
import { IcoChev } from '../components/Icons'
import './LandingPage.css'

// Fotos reales de estación/tienda YPF Full (no capturas de cámara del
// sistema: son referencia de fachada/acceso, por eso el pie las etiqueta
// como fotografía y no como "vista en vivo").
const SLIDES = [
  { src: fotoLocal,    alt: 'Fachada nocturna de una tienda Full con frente vidriado', caption: 'Tienda Full — fachada nocturna' },
  { src: fotoEstacion, alt: 'Fachada de una estación YPF Full al atardecer', caption: 'Estación YPF Full — fachada' },
  { src: fotoAcceso,   alt: 'Cartel de acceso a tienda Full con cámara de seguridad instalada', caption: 'Acceso a tienda — cámara instalada' },
]

// Carrusel simple por intervalo; respeta prefers-reduced-motion quedándose
// fija en la primera imagen en vez de animar.
function useCarousel(count, intervalMs = 5200) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (count < 2) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    const id = setInterval(() => setI((v) => (v + 1) % count), intervalMs);
    return () => clearInterval(id);
  }, [count, intervalMs]);
  return [i, setI];
}

// Mismo puente de datos reales que usa el shell operativo (useSystemHealth
// en App.jsx): /api/health para el badge de estado y /api/stats para el
// mini-preview con cifras reales. No son props compartidas a propósito --
// esta página no depende del árbol de AppShell, así que reconsulta por su
// cuenta con el mismo criterio.
function useLandingLive(intervalMs = 30000) {
  const [health, setHealth] = useState({ ok: true, checking: true });
  const [stats, setStats]   = useState(null);
  useEffect(() => {
    let cancelled = false;
    const check = () => {
      fetch("/api/health").then((r) => r.json())
        .then((d) => { if (!cancelled) setHealth({ ok: d?.db === "ok", checking: false }); })
        .catch(() => { if (!cancelled) setHealth({ ok: false, checking: false }); });
      fetch("/api/stats").then((r) => r.json())
        .then((d) => { if (!cancelled) setStats(d); })
        .catch(() => {});
    };
    check();
    const id = setInterval(check, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [intervalMs]);
  return { health, stats };
}

// Puerta de acceso de OptiFull (ruta "/"). No es el dashboard: es la
// pantalla de bienvenida orientada a estaciones YPF Full que presenta el
// sistema y deriva al operativo real ("/dashboard", ver App.jsx). Registro
// deliberado de placa técnica / hoja de auditoría -- ver LandingPage.css.
export function LandingPage({ onEnter }) {
  const [active, setActive] = useCarousel(SLIDES.length);
  const { health, stats } = useLandingLive();

  return (
    <div className="landing">
      <div className="landing-frame">
        <header className="landing-head landing-in" style={{ animationDelay: '0ms' }}>
          <img className="landing-logo" src={logoCompleto} alt="OptiFull" />
          <div className={`landing-status${!health.checking && !health.ok ? ' down' : ''}`} role="status">
            <span className="landing-status-dot" />
            <span className="landing-status-text">
              <span className="landing-status-main">
                {health.checking ? 'Conectando…' : health.ok ? 'Sistema activo' : 'Reconectando…'}
              </span>
              <span className="landing-status-sub">Monitoreo en línea</span>
            </span>
          </div>
        </header>

        <div className="landing-main">
          <main className="landing-body">
            <div className="landing-eyebrow-rule landing-in" style={{ animationDelay: '60ms' }} />

            <h1 className="landing-title landing-in" style={{ animationDelay: '100ms' }}>
              Auditoría visual continua para tiendas YPF Full.
            </h1>

            <p className="landing-desc landing-in" style={{ animationDelay: '160ms' }}>
              OptiFull controla y hace seguimiento inteligente del <b>flujo de personas</b> y
              del <b>stock de productos</b> a partir de las cámaras instaladas en cada local,
              convirtiendo esas grabaciones en datos operativos verificables.
            </p>

            <div className="landing-actions landing-in" style={{ animationDelay: '220ms' }}>
              <button type="button" className="btn-primary" onClick={onEnter}>
                Ingresar al Dashboard
                <span className="btn-primary-arrow"><IcoChev size={14} stroke={2.2} /></span>
              </button>
              <span className="landing-actions-note">Acceso operativo · sucursal Strumia, Mendoza</span>
            </div>

            {/* Puente hacia el operativo: mismas cifras que consume el
                dashboard (/api/stats), no una maqueta -- si no hay datos
                todavía, no se muestra (nunca un número inventado). */}
            {stats && (
              <div className="landing-preview landing-in" style={{ animationDelay: '250ms' }} role="status" aria-live="polite">
                <span className="landing-preview-dot" />
                <span className="landing-preview-text">
                  <b className="mono">{stats.personas_unicas}</b> personas detectadas
                  <span className="landing-preview-sep">·</span>
                  <b className="mono">{stats.permanencia_promedio_min}</b> min permanencia prom.
                  <span className="landing-preview-sep">·</span>
                  <b className="mono">4</b> cámaras sincronizadas
                </span>
              </div>
            )}
          </main>

          <aside className="landing-visual landing-in" style={{ animationDelay: '200ms' }} aria-label="Estación YPF Full">
            <div className="landing-visual-frame">
              {SLIDES.map((s, idx) => (
                <img
                  key={s.src}
                  src={s.src}
                  alt={s.alt}
                  className={`landing-visual-img${idx === active ? ' on' : ''}`}
                />
              ))}
            </div>
            <div className="landing-visual-foot">
              <span className="landing-visual-caption">{SLIDES[active].caption}</span>
              <div className="landing-visual-dots" role="tablist" aria-label="Seleccionar imagen">
                {SLIDES.map((s, idx) => (
                  <button
                    key={s.src}
                    type="button"
                    role="tab"
                    aria-selected={idx === active}
                    aria-label={`Imagen ${idx + 1} de ${SLIDES.length}`}
                    className={`landing-visual-dot${idx === active ? ' on' : ''}`}
                    onClick={() => setActive(idx)}
                  />
                ))}
              </div>
            </div>
          </aside>
        </div>

        <section className="landing-plate landing-in" style={{ animationDelay: '280ms' }} aria-label="Estado del sistema">
          <div className="landing-plate-item">
            <div className="landing-plate-label">Sucursal</div>
            <div className="landing-plate-value">Strumia — Mendoza</div>
          </div>
          <div className="landing-plate-item">
            <div className="landing-plate-label">Cámaras</div>
            <div className="landing-plate-value">4 activas</div>
          </div>
          <div className="landing-plate-item">
            <div className="landing-plate-label">Cobertura</div>
            <div className="landing-plate-value">Flujo de personas + stock en góndola</div>
          </div>
          <div className="landing-plate-item">
            <div className="landing-plate-label">Registro</div>
            <div className="landing-plate-value">Grabación continua</div>
          </div>
        </section>

        <footer className="landing-foot landing-in" style={{ animationDelay: '320ms' }}>
          <span>OptiFull — auditoría y monitoreo YPF Full</span>
          <span>Datos desde grabaciones · modo offline</span>
        </footer>
      </div>
    </div>
  )
}

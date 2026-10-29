import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Logo } from './Logo'
import {
  IcoHome, IcoReport,
  IcoAlert, IcoSettings, IcoExit, IcoBox, IcoReceipt
} from './Icons'
import { paginasPermitidas } from './permisos'

const SECTIONS = [
  {
    label: "Monitoreo",
    items: [
      { id: "dashboard", label: "Dashboard",    Ico: IcoHome },
      { id: "productos", label: "Productos",     Ico: IcoBox },
      { id: "ventas",    label: "Ventas",        Ico: IcoReceipt },
    ],
  },
  {
    label: "Análisis",
    items: [
      { id: "reports", label: "Reportes", Ico: IcoReport },
      { id: "alerts",  label: "Alertas",  Ico: IcoAlert  },
    ],
  },
  {
    label: "Sistema",
    items: [
      { id: "settings", label: "Configuración", Ico: IcoSettings },
    ],
  },
];

// true mientras la pantalla cumple la media query (se actualiza si se gira el dispositivo o se redimensiona la ventana)
function useMedia(query) {
  const [coincide, setCoincide] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const actualizar = () => setCoincide(mq.matches);
    actualizar();
    mq.addEventListener('change', actualizar);
    return () => mq.removeEventListener('change', actualizar);
  }, [query]);
  return coincide;
}

// Adaptacion a la pantalla: en celular (<= 760 px) el menu es un cajon que se abre con el boton de la barra
// superior (mobileOpen / onClose) y siempre se muestra expandido; en tablet (<= 1100 px) arranca compacto
// (solo iconos) para dejarle el ancho al contenido; en pantallas grandes arranca expandido. En tablet y
// escritorio el boton de la flecha sigue pudiendo expandirlo o colapsarlo a mano.
// Iniciales (hasta dos) para el avatar.
function iniciales(nombre) {
  const p = (nombre || "").trim().split(/\s+/).filter(Boolean);
  return ((p[0]?.[0] || "") + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase() || "?";
}
// "Dueño" / "Gerente" para los administradores, "Empleado" para el usuario común.
function etiquetaCargo(u) {
  if (!u) return "";
  const cargo = { dueno: "Dueño", gerente: "Gerente", empleado: "Empleado" }[u.cargo];
  return cargo || (u.rol === "administrador" ? "Administrador" : "Usuario");
}

// Solo el primer nombre: con nombre y apellido completos el pie del menu lo cortaba ("Arnon Da...").
function primerNombre(nombre) {
  return (nombre || "").trim().split(/\s+/)[0] || "Usuario";
}

// Ventana "¿Deseás cerrar sesión?" en el medio de la pantalla, para que un toque sin querer no saque a nadie.
// Va en un portal al <body>: el vidrio del sidebar (backdrop-filter) hace que position:fixed quede adentro de él.
function ConfirmarSalida({ onSi, onNo }) {
  const noRef = useRef(null);
  useEffect(() => {
    noRef.current?.focus();   // la opcion segura queda elegida: Enter sin mirar no cierra la sesion
    const onKey = (e) => { if (e.key === "Escape") onNo(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onNo]);
  return createPortal(
    <div className="vm-overlay confirm-overlay" onClick={onNo}>
      <div className="confirm-modal" role="alertdialog" aria-modal="true"
        aria-labelledby="confirmar-salida-titulo" onClick={(e) => e.stopPropagation()}>
        <h2 id="confirmar-salida-titulo" className="confirm-modal-title">¿Deseás cerrar sesión?</h2>
        <p className="confirm-modal-text">Vas a tener que volver a ingresar con tu usuario y contraseña.</p>
        <div className="confirm-modal-actions">
          <button ref={noRef} type="button" className="glass-btn-sec" onClick={onNo}>No</button>
          <button type="button" className="glass-btn" onClick={onSi}>Sí, cerrar sesión</button>
        </div>
      </div>
    </div>,
    document.body
  );
}

export function Sidebar({ active = "dashboard", alertCount = 0, onNavigate = () => {}, mobileOpen = false, onClose = () => {}, onLogout = () => {}, usuario = null }) {
  // Solo las secciones que el rol puede ver (ver permisos.js); una seccion sin items se oculta entera.
  const permitidas = paginasPermitidas(usuario?.rol);
  const secciones = SECTIONS
    .map((sec) => ({ ...sec, items: sec.items.filter((it) => permitidas.includes(it.id)) }))
    .filter((sec) => sec.items.length > 0);
  const esCelular = useMedia('(max-width: 760px)');
  const esTablet  = useMedia('(max-width: 1100px)');
  const [manual, setManual] = useState(null);                 // null = automatico segun el tamano de pantalla
  const collapsed = esCelular ? false : (manual ?? esTablet);
  const go = (id) => (e) => { e.preventDefault?.(); onNavigate(id); onClose(); };
  const [confirmarSalida, setConfirmarSalida] = useState(false);   // el boton de salir pide confirmacion

  // Indicador activo deslizante: en vez de que cada fila prenda/apague su
  // propio fondo (parpadeo), un unico "pill" se traslada a la fila activa.
  // JS solo mide la posicion VERTICAL (las filas viven en <nav> distintos por
  // seccion); el ancho y la posicion horizontal salen del CSS (.side-active-pill
  // en index.css): toda la fila expandido, 42px centrados colapsado. Antes se
  // median tambien con getBoundingClientRect, y como colapsar/expandir anima el
  // ancho del sidebar, la medida salia a mitad de la animacion: colapsado la
  // pildora quedaba fuera de la columna y al expandir, del tamaño del icono.
  const scrollRef = useRef(null);
  const itemRefs  = useRef({});
  const [pill, setPill] = useState(null);

  useLayoutEffect(() => {
    const wrap = scrollRef.current;
    const el   = itemRefs.current[active];
    if (!wrap || !el) { setPill(null); return; }
    setPill({
      top:    el.getBoundingClientRect().top - wrap.getBoundingClientRect().top + wrap.scrollTop,
      height: el.getBoundingClientRect().height,
    });
  }, [active, collapsed, mobileOpen]);

  return (
    <aside className={`side${collapsed ? " collapsed" : ""}${mobileOpen ? " mobile-open" : ""}`}>

      <div className="side-brand">
        {collapsed
          ? <Logo className="side-logo side-logo-icon" icono />
          : <Logo className="side-logo" />}
        <button
          className="side-toggle"
          onClick={() => setManual(!collapsed)}
          title={collapsed ? "Expandir" : "Colapsar"}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d={collapsed ? "M4.5 2L8.5 6L4.5 10" : "M7.5 2L3.5 6L7.5 10"}
              stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>

      <div className="side-scroll" ref={scrollRef}>
        {pill && (
          <div
            className="side-active-pill"
            aria-hidden="true"
            style={{
              transform: `translateY(${pill.top}px)`,
              height: pill.height,
            }}
          />
        )}
        {secciones.map(sec => (
          <div key={sec.label}>
            {!collapsed
              ? <div className="side-sec-label">{sec.label}</div>
              : <div style={{ height: 8 }} />
            }
            <nav className="side-nav">
              {sec.items.map(it => {
                const badge = it.id === "alerts" ? alertCount : 0;
                return (
                  <a
                    key={it.id}
                    href={`#${it.id}`}
                    ref={(el) => { itemRefs.current[it.id] = el; }}
                    className={`side-nav-item${active === it.id ? " active" : ""}`}
                    onClick={go(it.id)}
                    title={collapsed ? it.label : undefined}
                    aria-current={active === it.id ? "page" : undefined}
                  >
                    <span className="side-nav-ico"><it.Ico /></span>
                    {!collapsed && <span className="side-nav-label">{it.label}</span>}
                    {!collapsed && badge > 0 && <span className="badge">{badge}</span>}
                    {!collapsed && it.tag && <span className="side-nav-tag">{it.tag}</span>}
                  </a>
                );
              })}
            </nav>
          </div>
        ))}
      </div>

      <div className="side-foot">
        <div className="avatar">{iniciales(usuario?.nombre)}</div>
        {!collapsed && (
          <>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div title={usuario?.nombre} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 15, fontWeight: 600, color: "var(--fg-0)" }}>
                {primerNombre(usuario?.nombre)}
              </div>
              <small style={{ fontSize: 12, color: "var(--fg-3)" }}>{etiquetaCargo(usuario)}</small>
            </div>
            <button className="iconbtn" title="Cerrar sesión" aria-label="Cerrar sesión" onClick={() => setConfirmarSalida(true)}><IcoExit /></button>
          </>
        )}
      </div>

      {confirmarSalida && (
        <ConfirmarSalida onSi={() => { setConfirmarSalida(false); onLogout(); }} onNo={() => setConfirmarSalida(false)} />
      )}

    </aside>
  );
}

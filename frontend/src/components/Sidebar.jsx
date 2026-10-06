import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import logoCompleto from '../assets/optifull-logo.png'
import logoIcono from '../assets/optifull-icon.png'
import {
  IcoHome, IcoStock, IcoReport,
  IcoAlert, IcoSettings, IcoExit
} from './Icons'

const SECTIONS = [
  {
    label: "Monitoreo",
    items: [
      { id: "dashboard", label: "Dashboard",    Ico: IcoHome },
      { id: "stock",     label: "Stock",         Ico: IcoStock },
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
      { id: "settings", label: "Config",   Ico: IcoSettings },
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
export function Sidebar({ active = "dashboard", alertCount = 0, onNavigate = () => {}, mobileOpen = false, onClose = () => {} }) {
  const esCelular = useMedia('(max-width: 760px)');
  const esTablet  = useMedia('(max-width: 1100px)');
  const [manual, setManual] = useState(null);                 // null = automatico segun el tamano de pantalla
  const collapsed = esCelular ? false : (manual ?? esTablet);
  const go = (id) => (e) => { e.preventDefault?.(); onNavigate(id); onClose(); };

  // Indicador activo deslizante: en vez de que cada fila prenda/apague su
  // propio fondo (parpadeo), un unico "pill" mide la posicion real de la
  // fila activa (getBoundingClientRect, no valores fijos -- las filas viven
  // en <nav> distintos por seccion) y se traslada ahi con transform. Se
  // remide en cada cambio de pagina o de collapsed (el ancho de fila cambia).
  const scrollRef = useRef(null);
  const itemRefs  = useRef({});
  const [pill, setPill] = useState(null);

  useLayoutEffect(() => {
    const wrap = scrollRef.current;
    const el   = itemRefs.current[active];
    if (!wrap || !el) { setPill(null); return; }
    const wrapRect = wrap.getBoundingClientRect();
    const elRect   = el.getBoundingClientRect();
    setPill({
      top:    elRect.top  - wrapRect.top  + wrap.scrollTop,
      left:   elRect.left - wrapRect.left + wrap.scrollLeft,
      width:  elRect.width,
      height: elRect.height,
    });
  }, [active, collapsed, mobileOpen]);

  return (
    <aside className={`side${collapsed ? " collapsed" : ""}${mobileOpen ? " mobile-open" : ""}`}>

      <div className="side-brand">
        {collapsed
          ? <img className="side-logo side-logo-icon" src={logoIcono} alt="Optifull" />
          : <img className="side-logo" src={logoCompleto} alt="Optifull" />}
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
              transform: `translate(${pill.left}px, ${pill.top}px)`,
              width: pill.width,
              height: pill.height,
            }}
          />
        )}
        {SECTIONS.map(sec => (
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
        <div className="avatar">AB</div>
        {!collapsed && (
          <>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 15, fontWeight: 600, color: "#000" }}>
                Agostina B.
              </div>
              <small style={{ fontSize: 12, color: "var(--fg-3)" }}>Encargada · Strumia</small>
            </div>
            <button className="iconbtn" title="Salir"><IcoExit /></button>
          </>
        )}
      </div>

    </aside>
  );
}

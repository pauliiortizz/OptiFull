import { createContext, useContext, useState, useCallback, useRef, useLayoutEffect } from 'react'
import { IcoCheck2, IcoAlert, IcoSparkle } from './Icons'

export const ToastCtx = createContext(() => {});

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((msg, opts = {}) => {
    const id = Date.now() + Math.random();
    const toast = { id, msg, kind: opts.kind || "info", ttl: opts.ttl || 3000 };
    setToasts((t) => [...t, toast]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), toast.ttl);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-stack">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            <span className="toast-ico">
              {t.kind === "success" ? <IcoCheck2 /> : t.kind === "warn" ? <IcoAlert /> : <IcoSparkle />}
            </span>
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

// Barra flotante "en qué sección estoy" -- mismo patrón que la pildora
// "Reportes 2.0" de ReportsV2Page (título centrado, vidrio, sticky), acá
// como componente compartido para que Cámaras, Mapa de calor, Tracking,
// Stock, Alertas y Config la reciban gratis en vez de reimplementarla cada
// una. Ver .section-nav en index.css.
export function PageHeader({ title, subtitle, right, tag, stacked = false }) {
  const navRef = useRef(null);
  const tituloRef = useRef(null);
  const derechaRef = useRef(null);
  const [apilado, setApilado] = useState(false);
  // stacked: fuerza las dos filas siempre (p. ej. el dashboard, cuyos controles cambian de ancho segun el periodo
  // y no deben mover la barra de lugar al elegir Hoy / 7 dias / 30 dias / Personalizado).

  // El titulo va centrado en absoluto, asi que no "sabe" cuanto ocupan los controles de la derecha: con muchos
  // (p. ej. Personalizado + dos fechas) se pisaban. Se mide el espacio real y, si no entran, la barra pasa a dos
  // filas (titulo arriba, controles abajo: el mismo diseno que ya se usa en celular). Las medidas no dependen del
  // layout actual (ancho de la barra, texto del titulo y suma de los hijos), asi que no oscila al apilarse.
  useLayoutEffect(() => {
    const nav = navRef.current, titulo = tituloRef.current, derecha = derechaRef.current;
    if (stacked || !nav || !titulo || !derecha) return;
    const medir = () => {
      const hijos = [...derecha.children];
      const necesario = hijos.reduce((t, el) => t + el.getBoundingClientRect().width, 0) + 8 * Math.max(0, hijos.length - 1);
      if (!necesario) { setApilado(false); return; }
      const r = document.createRange(); r.selectNodeContents(titulo);
      const anchoTitulo = r.getBoundingClientRect().width;
      const ancho = nav.getBoundingClientRect().width;
      const bordeTitulo = ancho / 2 + anchoTitulo / 2 + 16;     // 16px de aire entre titulo y controles
      const inicioControles = ancho - 18 - necesario;           // 18px = padding lateral de la barra
      setApilado(bordeTitulo > inicioControles);
    };
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(nav);
    const mo = new MutationObserver(medir);
    mo.observe(derecha, { childList: true, subtree: true });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [title, tag, right, stacked]);

  return (
    <>
      <header ref={navRef} className={`section-nav${stacked || apilado ? " is-stacked" : ""}`}>
        <span className="section-nav-side" />
        <h1 ref={tituloRef} className="section-nav-title">
          {title}
          {tag && <span className="section-tag">{tag}</span>}
        </h1>
        <span className="section-nav-side section-nav-right">
          {right && <div ref={derechaRef} style={{ display: "flex", gap: 8, alignItems: "center" }}>{right}</div>}
        </span>
      </header>
      {subtitle && <p className="section-intro">{subtitle}</p>}
    </>
  );
}

export function WipBanner({ children }) {
  return (
    <div className="wip-banner">
      <span className="wip-tag">EN PROGRESO</span>
      <span>{children}</span>
    </div>
  );
}

import { createContext, useContext, useState, useCallback } from 'react'
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
export function PageHeader({ title, subtitle, right, tag }) {
  return (
    <>
      <header className="section-nav">
        <span className="section-nav-side" />
        <h1 className="section-nav-title">
          {title}
          {tag && <span className="section-tag">{tag}</span>}
        </h1>
        <span className="section-nav-side section-nav-right">
          {right && <div style={{ display: "flex", gap: 8, alignItems: "center" }}>{right}</div>}
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

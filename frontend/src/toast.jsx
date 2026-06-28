// Toast notification system — global queue, fade in/out
const ToastCtx = React.createContext(() => {});

function ToastProvider({ children }) {
  const [toasts, setToasts] = React.useState([]);
  const push = React.useCallback((msg, opts = {}) => {
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

const useToast = () => React.useContext(ToastCtx);

// ── Generic page header ─────────────────────────────────────────
function PageHeader({ title, subtitle, right }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {right && <div style={{ display: "flex", gap: 8, alignItems: "center" }}>{right}</div>}
    </div>
  );
}

// Empty / WIP banner
function WipBanner({ children }) {
  return (
    <div className="wip-banner">
      <span className="wip-tag">EN PROGRESO</span>
      <span>{children}</span>
    </div>
  );
}

window.ToastCtx = ToastCtx;
window.ToastProvider = ToastProvider;
window.useToast = useToast;
window.PageHeader = PageHeader;
window.WipBanner = WipBanner;

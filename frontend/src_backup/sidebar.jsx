function Sidebar({ active = "dashboard", alertCount = 3, onNavigate = () => {} }) {
  const items = [
    { id: "dashboard", label: "Dashboard", Ico: IcoDashboard },
    { id: "heatmap", label: "Mapa de calor", Ico: IcoHeat },
    { id: "tracking", label: "Tracking de personas", Ico: IcoTrack },
    { id: "stock", label: "Control de stock", Ico: IcoStock },
    { id: "reports", label: "Reportes", Ico: IcoReport },
    { id: "alerts", label: "Alertas", Ico: IcoAlert, badge: alertCount },
  ];
  const handle = (id) => (e) => { e.preventDefault?.(); onNavigate(id); };
  return (
    <aside className="side">
      <div className="brand">
        <div className="brand-mark" />
        <div>
          <div className="brand-name">OptiFull</div>
          <div className="brand-sub">Vision Ops</div>
        </div>
      </div>

      <div className="side-section">
        <h4>Monitoreo</h4>
        <nav className="nav">
          {items.slice(0, 4).map((it) => (
            <a key={it.id} className={active === it.id ? "active" : ""} onClick={handle(it.id)}>
              <span className="ico"><it.Ico /></span>
              <span>{it.label}</span>
              {it.badge ? <span className="badge">{it.badge}</span> : null}
            </a>
          ))}
        </nav>
      </div>

      <div className="side-section">
        <h4>Análisis</h4>
        <nav className="nav">
          {items.slice(4).map((it) => (
            <a key={it.id} className={active === it.id ? "active" : ""} onClick={handle(it.id)}>
              <span className="ico"><it.Ico /></span>
              <span>{it.label}</span>
              {it.badge ? <span className="badge">{it.badge}</span> : null}
            </a>
          ))}
        </nav>
      </div>

      <div className="side-section">
        <h4>Sistema</h4>
        <nav className="nav">
          <a className={active === "cameras" ? "active" : ""} onClick={handle("cameras")}>
            <span className="ico"><IcoCam /></span><span>Cámaras</span>
            <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--pos-soft)" }} className="mono">8/8</span>
          </a>
          <a className={active === "docs" ? "active" : ""} onClick={handle("docs")}>
            <span className="ico"><IcoDocs /></span><span>Documentación de Diseño</span>
          </a>
          <a className={active === "claude" ? "active" : ""} onClick={handle("claude")}>
            <span className="ico"><IcoSparkle /></span><span>Asistente IA</span>
            <span style={{ marginLeft: "auto", fontSize: 9, color: "var(--brand-soft)", padding: "1px 5px", borderRadius: 4, background: "rgba(37,99,168,.12)", border: "1px solid rgba(37,99,168,.2)", fontWeight: 600, letterSpacing: ".05em" }}>NEW</span>
          </a>
          <a className={active === "settings" ? "active" : ""} onClick={handle("settings")}>
            <span className="ico"><IcoSettings /></span><span>Configuración</span>
          </a>
        </nav>
      </div>

      <div className="side-foot">
        <div className="avatar">AB</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--fg-0)" }}>Agostina B.</div>
          <small>Encargada · Strumia</small>
        </div>
        <button className="iconbtn" title="Salir"><IcoExit /></button>
      </div>
    </aside>
  );
}

window.Sidebar = Sidebar;

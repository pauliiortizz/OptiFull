import { useState } from 'react'
import {
  IcoDashboard, IcoHeat, IcoTrack, IcoStock, IcoReport,
  IcoAlert, IcoSettings, IcoExit
} from './Icons'

const SECTIONS = [
  {
    label: "Monitoreo",
    items: [
      { id: "dashboard", label: "Dashboard",    Ico: IcoDashboard },
      { id: "heatmap",   label: "Mapa de calor", Ico: IcoHeat },
      { id: "tracking",  label: "Tracking",      Ico: IcoTrack },
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

export function Sidebar({ active = "dashboard", alertCount = 0, onNavigate = () => {} }) {
  const [collapsed, setCollapsed] = useState(false);
  const go = (id) => (e) => { e.preventDefault?.(); onNavigate(id); };

  return (
    <aside className={`side${collapsed ? " collapsed" : ""}`}>

      <div className="side-brand">
        <div className="side-logo" />
        {!collapsed && (
          <div className="side-brand-text">
            <div className="side-brand-name">OptiFull</div>
            <div className="side-brand-sub">Vision Ops</div>
          </div>
        )}
        <button
          className="side-toggle"
          onClick={() => setCollapsed(c => !c)}
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

      <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
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
                    className={`side-nav-item${active === it.id ? " active" : ""}`}
                    onClick={go(it.id)}
                    title={collapsed ? it.label : undefined}
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
              <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 14.5, color: "var(--fg-0)" }}>
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

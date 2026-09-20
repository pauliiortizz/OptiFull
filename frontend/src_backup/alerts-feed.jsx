// Alerts feed — live-ish list with severity, zone, time
const ALERT_TEMPLATES = [
  { sev: "critical", title: "Trayectoria sospechosa detectada",   desc: "Movimiento hacia salida sin pasar por caja", zone: "Salida", icon: "⚠" },
  { sev: "warn",     title: "Tiempo de espera elevado en caja 2",  desc: "5 personas en cola · espera estimada 4:30 min", zone: "Caja 2", icon: "◐" },
  { sev: "critical", title: "Stock crítico: Coca-Cola 500ml",       desc: "Detectados 2 unidades en góndola · esperado: 24", zone: "Góndola B3", icon: "▽" },
  { sev: "info",     title: "Pico de circulación detectado",        desc: "31 personas simultáneas — récord del día", zone: "Tienda", icon: "↑" },
  { sev: "warn",     title: "Cámara playa-2 con baja confianza",    desc: "Confianza promedio 47% · revisar lente", zone: "Playa", icon: "◉" },
  { sev: "info",     title: "Reposición de góndola completada",     desc: "Stock actualizado en góndola A1 (snacks)", zone: "Góndola A1", icon: "✓" },
  { sev: "warn",     title: "Permanencia prolongada",               desc: "Persona en zona de heladera por 4:12 min", zone: "Heladera", icon: "◐" },
  { sev: "critical", title: "Aglomeración en cafetería",            desc: "Densidad > 1.8 pers/m² durante 3 min", zone: "Cafetería", icon: "⚠" },
];

function formatRelative(secsAgo) {
  if (secsAgo < 60) return `${secsAgo}s`;
  if (secsAgo < 3600) return `${Math.floor(secsAgo / 60)}m`;
  return `${Math.floor(secsAgo / 3600)}h ${Math.floor((secsAgo % 3600) / 60)}m`;
}

function AlertsFeed({ alerts }) {
  const [, force] = React.useReducer((x) => x + 1, 0);
  // Re-render every 5s so "hace Xs" advances
  React.useEffect(() => {
    const id = setInterval(force, 5000);
    return () => clearInterval(id);
  }, []);
  const now = Date.now();

  return (
    <div className="alerts-list">
      {alerts.map((a, i) => {
        const secsAgo = Math.max(1, Math.floor((now - a.ts) / 1000));
        return (
          <div key={a.id} className="alert-item">
            <div className={`alert-dot ${a.sev}`} />
            <div style={{ minWidth: 0 }}>
              <div className="alert-title">{a.title}</div>
              <div className="alert-desc">{a.desc}</div>
              <div className="alert-meta">
                <span style={{ color: "var(--fg-2)" }}>· {a.zone}</span>
                {a.cam && <span>cam-{a.cam}</span>}
              </div>
            </div>
            <div className="alert-time mono">hace {formatRelative(secsAgo)}</div>
          </div>
        );
      })}
    </div>
  );
}

// Hook to generate + stream alerts
function useLiveAlerts(seed = 8) {
  const [alerts, setAlerts] = React.useState(() => {
    const now = Date.now();
    // Seed with `seed` alerts spread over last 45 min
    return Array.from({ length: seed }, (_, i) => {
      const t = ALERT_TEMPLATES[(i * 3) % ALERT_TEMPLATES.length];
      return {
        id: `a-${i}-${now}`,
        ...t,
        cam: 1 + (i % 8),
        ts: now - (i * 4 + 1) * 60 * 1000 - Math.random() * 60000,
      };
    }).sort((a, b) => b.ts - a.ts);
  });

  React.useEffect(() => {
    const id = setInterval(() => {
      // ~30% chance every 12s to inject a new alert
      if (Math.random() > 0.3) return;
      const t = ALERT_TEMPLATES[Math.floor(Math.random() * ALERT_TEMPLATES.length)];
      setAlerts((prev) => [
        { id: `a-${Date.now()}`, ...t, cam: 1 + Math.floor(Math.random() * 8), ts: Date.now() },
        ...prev,
      ].slice(0, 12));
    }, 12000);
    return () => clearInterval(id);
  }, []);

  return alerts;
}

window.AlertsFeed = AlertsFeed;
window.useLiveAlerts = useLiveAlerts;
window.ALERT_TEMPLATES = ALERT_TEMPLATES;

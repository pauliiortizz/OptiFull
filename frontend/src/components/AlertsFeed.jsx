import { useReducer, useEffect, useState } from 'react'

export const ALERT_TEMPLATES = [
  { sev: "critical", title: "Trayectoria sospechosa detectada",   desc: "Movimiento hacia salida sin pasar por caja", zone: "Salida" },
  { sev: "warn",     title: "Tiempo de espera elevado en caja 2",  desc: "5 personas en cola · espera estimada 4:30 min", zone: "Caja 2" },
  { sev: "critical", title: "Stock crítico: Coca-Cola 500ml",       desc: "Detectados 2 unidades en góndola · esperado: 24", zone: "Góndola B3" },
  { sev: "info",     title: "Pico de circulación detectado",        desc: "31 personas simultáneas — récord del día", zone: "Tienda" },
  { sev: "warn",     title: "Cámara playa-2 con baja confianza",    desc: "Confianza promedio 47% · revisar lente", zone: "Playa" },
  { sev: "info",     title: "Reposición de góndola completada",     desc: "Stock actualizado en góndola A1 (snacks)", zone: "Góndola A1" },
  { sev: "warn",     title: "Permanencia prolongada",               desc: "Persona en zona de heladera por 4:12 min", zone: "Heladera" },
  { sev: "critical", title: "Aglomeración en cafetería",            desc: "Densidad > 1.8 pers/m² durante 3 min", zone: "Cafetería" },
];

function formatRelative(secsAgo) {
  if (secsAgo < 60) return `${secsAgo}s`;
  if (secsAgo < 3600) return `${Math.floor(secsAgo / 60)}m`;
  return `${Math.floor(secsAgo / 3600)}h ${Math.floor((secsAgo % 3600) / 60)}m`;
}

export function AlertsFeed({ alerts }) {
  const [, force] = useReducer((x) => x + 1, 0);
  useEffect(() => {
    const id = setInterval(force, 5000);
    return () => clearInterval(id);
  }, []);
  const now = Date.now();

  return (
    <div className="alerts-list">
      {alerts.map((a) => {
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

export function useLiveAlerts(seed = 8) {
  const [alerts, setAlerts] = useState(() => {
    const now = Date.now();
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

  useEffect(() => {
    const id = setInterval(() => {
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

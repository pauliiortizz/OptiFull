import React from 'react'
import { useToast, PageHeader } from '../components/Toast'
import { IcoMore } from '../components/Icons'
import { useTheme } from '../components/useTheme'

// SETTINGS page (las paginas de Mapa de calor, Tracking y Stock se eliminaron)

// Umbrales de alerta: solo los que el sistema puede medir hoy (cola y espera en caja).
// La espera se maneja en MINUTOS en toda la app (igual que el reporte de espera en caja).
export const LIMITES_UMBRALES = {
  queue: { min: 1, max: 20, step: 1 },     // personas en la cola de una caja
  wait:  { min: 1, max: 15, step: 0.5 },   // minutos de espera
};
const UMBRALES_INICIALES = { queue: 4, wait: 4 };

// Un umbral es valido si es un numero dentro de su rango y respeta el paso.
export function umbralValido(clave, v) {
  const { min, max, step } = LIMITES_UMBRALES[clave];
  if (typeof v !== 'number' || !Number.isFinite(v) || v < min || v > max) return false;
  return Math.abs((v - min) / step - Math.round((v - min) / step)) < 1e-9;
}

// ═════════════════════════════════════════════════════════════
// SETTINGS PAGE
// ═════════════════════════════════════════════════════════════
function SettingsPage() {
  const toast = useToast();
  const { tema: apariencia, setTema } = useTheme();
  const [tab, setTab] = React.useState("general");
  const [thresholds, setThresholds] = React.useState(UMBRALES_INICIALES);
  const [push, setPush] = React.useState(true);

  const guardar = () => {
    const invalido = Object.keys(LIMITES_UMBRALES).find((k) => !umbralValido(k, thresholds[k]));
    if (invalido) {
      const { min, max } = LIMITES_UMBRALES[invalido];
      const nombre = invalido === "queue" ? "La cola máxima" : "La espera máxima";
      toast(`${nombre} debe estar entre ${min} y ${max}`, { kind: "warn" });
      setTab("thresholds");
      return;
    }
    toast("Cambios guardados", { kind: "success" });
  };

  return (
    <main className="content docs">
      <PageHeader
        title="Configuración"
        subtitle="Ajustes del sistema y umbrales de alertas."
        right={<button className="btn-pri" onClick={guardar}>Guardar cambios</button>}
      />

      <div className="settings-layout">
        <nav className="settings-nav">
          {[
            ["general","General"],
            ["thresholds","Umbrales de alertas"],
            ["cameras","Cámaras"],
            ["notif","Notificaciones"],
            ["users","Usuarios y roles"],
          ].map(([k,l]) => (
            <a key={k} className={tab===k?"active":""} onClick={() => setTab(k)}>{l}</a>
          ))}
        </nav>

        <div>
          {tab === "general" && (
            <div className="panel">
              <h3 className="docs-h3">Apariencia</h3>
              <p style={{ fontSize: 14, color: "var(--fg-2)", margin: "0 0 12px" }}>
                Elegí el modo Día o Noche para el dashboard.
              </p>
              <div className="seg" role="radiogroup" aria-label="Apariencia" style={{ display: "inline-flex", marginBottom: 24 }}>
                {[["light", "Día"], ["dark", "Noche"]].map(([k, l]) => (
                  <button key={k} type="button" role="radio" aria-checked={apariencia === k}
                    className={apariencia === k ? "on" : ""} onClick={() => setTema(k)}>{l}</button>
                ))}
              </div>
              <h3 className="docs-h3">Sucursal</h3>
              <div className="form-grid">
                <Field label="Nombre" value="Strumia — Mendoza" />
                <Field label="Dirección" value="Av. San Martín 1234" />
                <Field label="Zona horaria" value="America/Argentina/Mendoza" readonly />
                <Field label="Horario operativo" value="06:00 – 22:00" />
              </div>
              <h3 className="docs-h3" style={{ marginTop: 24 }}>Sistema</h3>
              <div className="form-grid">
                <Field label="Modelo de detección" value="YOLOv8m" readonly mono />
                <Field label="Tracker" value="ByteTrack" readonly mono />
                <Field label="Frame skip" value="3" mono />
                <Field label="Versión" value="OptiFull v0.3.0" readonly mono />
              </div>
            </div>
          )}

          {tab === "thresholds" && (
            <div className="panel">
              <h3 className="docs-h3">Umbrales que generan alertas</h3>
              <p style={{ fontSize: 14, color: "var(--fg-2)", margin: "0 0 18px" }}>
                Define cuándo el sistema dispara cada tipo de alerta. Valores conservadores reducen falsos positivos.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <Slider label="Cola máxima por caja" v={thresholds.queue} {...LIMITES_UMBRALES.queue} unit="personas"
                  ayuda="Cantidad de personas en la cola de una caja a partir de la cual se avisa."
                  onChange={(v) => setThresholds({...thresholds, queue: v})} />
                <Slider label="Espera máxima" v={thresholds.wait} {...LIMITES_UMBRALES.wait} unit="min"
                  ayuda="Minutos de espera en caja a partir de los cuales se avisa."
                  onChange={(v) => setThresholds({...thresholds, wait: v})} />
              </div>
            </div>
          )}

          {tab === "cameras" && (
            <div className="panel">
              <h3 className="docs-h3">Configuración global de cámaras</h3>
              <p style={{ fontSize: 14, color: "var(--fg-2)", margin: "0 0 12px" }}>
                Solo lectura: estos parámetros se definen en la instalación y no se pueden modificar desde el dashboard.
              </p>
              <div className="form-grid">
                <Field label="Protocolo" value="RTSP" readonly mono />
                <Field label="NVR" value="nvr.local:554" readonly mono />
                <Field label="Codec" value="H.264" readonly mono />
                <Field label="Resolución" value="1280×720" readonly mono />
              </div>
            </div>
          )}

          {tab === "notif" && (
            <div className="panel">
              <h3 className="docs-h3">Canales de notificación</h3>
              <div style={{
                padding: "12px 14px", background: "var(--bg-3)", border: "1px solid var(--line)", borderRadius: 'var(--radius-lg)',
                display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14
              }}>
                <div>
                  <div style={{ fontSize: 15, color: "var(--fg-0)", fontWeight: 500 }}>Notificaciones push</div>
                  <div style={{ fontSize: 13, color: "var(--fg-2)", marginTop: 3 }}>Push al navegador cuando el dashboard está abierto</div>
                </div>
                <Switch on={push} label="Notificaciones push" onClick={() => setPush(!push)} />
              </div>
            </div>
          )}

          {tab === "users" && (
            <div className="panel">
              <h3 className="docs-h3">Usuarios con acceso</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  ["Agostina Blasón", "Encargada", "AB", "owner"],
                  ["Arnon Daniel Nahmias", "Operador", "AN", "admin"],
                  ["Paulina Ortiz", "Operadora", "PO", "admin"],
                  ["Henry Martinez", "Visualizador YPF", "HM", "viewer"],
                ].map(([name, role, init, level]) => (
                  <div key={name} style={{
                    display: "grid", gridTemplateColumns: "auto 1fr auto auto", alignItems: "center", gap: 12,
                    padding: "10px 14px", background: "var(--bg-3)", border: "1px solid var(--line)", borderRadius: 'var(--radius-lg)'
                  }}>
                    <div className="avatar">{init}</div>
                    <div>
                      <div style={{ fontSize: 15, color: "var(--fg-0)" }}>{name}</div>
                      <div style={{ fontSize: 13, color: "var(--fg-3)" }}>{role}</div>
                    </div>
                    <span style={{
                      fontSize: 12, padding: "2px 8px", borderRadius: 99,
                      background: level === "owner" ? "rgba(37,99,168,.15)" : "var(--bg-2)",
                      color: level === "owner" ? "var(--brand-soft)" : "var(--fg-2)",
                      border: `1px solid ${level === "owner" ? "rgba(37,99,168,.3)" : "var(--line)"}`,
                      textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 500
                    }}>{level}</span>
                    <button className="iconbtn" onClick={() => toast(`Editando permisos de ${name}`)}><IcoMore /></button>
                  </div>
                ))}
              </div>
              <button className="btn-sec" style={{ marginTop: 14 }} onClick={() => toast("Invitar usuario · próximamente")}>+ Invitar usuario</button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

// Los campos de solo lectura van deshabilitados: no se pueden enfocar, escribir ni seleccionar con el
// mouse, y se ven distintos de los editables (ver .form-field.ro en index.css).
function Field({ label, value, readonly, mono }) {
  return (
    <div className={readonly ? "form-field ro" : "form-field"} title={readonly ? "Solo lectura" : undefined}>
      <label>{label}</label>
      <input type="text" defaultValue={value} readOnly={readonly} disabled={readonly}
        className={mono ? "mono" : ""} />
    </div>
  );
}

// Rango + campo numerico sincronizados. El campo deja escribir libremente; al salir de el se
// ajusta al rango y al paso, asi nunca queda un valor fuera de limites.
function Slider({ label, v, min, max, step = 1, unit, ayuda, onChange }) {
  const ajustar = (x) => {
    if (!Number.isFinite(x)) return min;
    const enPaso = min + Math.round((x - min) / step) * step;
    return Math.min(max, Math.max(min, +enPaso.toFixed(2)));
  };
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6, gap: 12 }}>
        <span style={{ fontSize: 14.5, color: "var(--fg-1)" }}>{label}</span>
        <span className="mono" style={{ fontSize: 14, color: "var(--fg-0)", fontWeight: 500, display: "inline-flex", alignItems: "center", gap: 6 }}>
          <input type="number" min={min} max={max} step={step} value={Number.isFinite(v) ? v : ""}
            aria-label={`${label} (${unit})`}
            onChange={(e) => onChange(e.target.value === "" ? NaN : +e.target.value)}
            onBlur={() => onChange(ajustar(v))}
            className="mono"
            style={{ width: 64, padding: "2px 6px", textAlign: "right", background: "var(--bg-2)", color: "var(--fg-0)", border: "1px solid var(--line)", borderRadius: 6 }} />
          <span style={{ color: "var(--fg-3)", fontWeight: 400 }}>{unit}</span>
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={Number.isFinite(v) ? v : min}
        aria-label={label}
        onChange={(e) => onChange(+e.target.value)}
        style={{ width: "100%", accentColor: "var(--brand-soft)" }} />
      {ayuda && <div style={{ fontSize: 12.5, color: "var(--fg-3)", marginTop: 4 }}>{ayuda}</div>}
    </div>
  );
}

function Switch({ on, label, onClick }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} onClick={onClick} style={{
      appearance: "none", border: 0, padding: 0, width: 36, height: 20, borderRadius: 3,
      background: on ? "var(--pos-soft)" : "var(--bg-1)", border: `1px solid ${on ? "var(--pos-soft)" : "var(--line)"}`,
      cursor: "default", position: "relative", transition: "background .1s, border-color .1s"
    }}>
      <span style={{
        position: "absolute", top: 1, left: on ? 17 : 1, width: 16, height: 16, borderRadius: 2,
        background: on ? "#0b0d13" : "var(--fg-3)", transition: "left .1s, background .1s"
      }} />
    </button>
  );
}

export { SettingsPage }

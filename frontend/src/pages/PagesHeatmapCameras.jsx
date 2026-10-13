import React from 'react'
import { useToast, PageHeader } from '../components/Toast'
import { IcoMore } from '../components/Icons'
import { useTheme } from '../components/useTheme'

// SETTINGS page (las paginas de Mapa de calor, Tracking y Stock se eliminaron)

// ═════════════════════════════════════════════════════════════
// SETTINGS PAGE
// ═════════════════════════════════════════════════════════════
function SettingsPage() {
  const toast = useToast();
  const { preferencia: apariencia, setTema } = useTheme();
  const [tab, setTab] = React.useState("general");
  const [thresholds, setThresholds] = React.useState({
    queue: 4, wait: 240, density: 1.8, conf: 60, stockMin: 5,
  });
  const [notif, setNotif] = React.useState({ email: true, push: true, telegram: false });

  return (
    <main className="content docs">
      <PageHeader
        title="Configuración"
        subtitle="Ajustes del sistema y umbrales de alertas."
        right={<button className="btn-pri" onClick={() => toast("Cambios guardados", { kind: "success" })}>Guardar cambios</button>}
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
                Automático sigue la configuración de tu dispositivo y cambia solo al atardecer.
              </p>
              <div className="seg" role="radiogroup" aria-label="Apariencia" style={{ display: "inline-flex", marginBottom: 24 }}>
                {[["auto", "Automático"], ["light", "Día"], ["dark", "Noche"]].map(([k, l]) => (
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
                <Slider label="Cola máxima por caja" v={thresholds.queue} min={2} max={10} unit="personas" onChange={(v) => setThresholds({...thresholds, queue: v})} />
                <Slider label="Espera máxima" v={thresholds.wait} min={60} max={600} step={15} unit="seg" onChange={(v) => setThresholds({...thresholds, wait: v})} />
                <Slider label="Densidad máxima" v={thresholds.density} min={0.5} max={3} step={0.1} unit="pers/m²" onChange={(v) => setThresholds({...thresholds, density: v})} />
                <Slider label="Confianza mínima del modelo" v={thresholds.conf} min={30} max={95} unit="%" onChange={(v) => setThresholds({...thresholds, conf: v})} />
                <Slider label="Stock mínimo en góndola" v={thresholds.stockMin} min={1} max={30} unit="unidades" onChange={(v) => setThresholds({...thresholds, stockMin: v})} />
              </div>
            </div>
          )}

          {tab === "cameras" && (
            <div className="panel">
              <h3 className="docs-h3">Configuración global de cámaras</h3>
              <div className="form-grid">
                <Field label="Protocolo" value="RTSP" readonly mono />
                <Field label="NVR" value="nvr.local:554" mono />
                <Field label="Codec" value="H.264" readonly mono />
                <Field label="Resolución" value="1280×720" mono />
              </div>
              <p style={{ fontSize: 14, color: "var(--fg-3)", marginTop: 16 }}>
                Para configuración individual de cada cámara, ir a la sección <a style={{ color: "var(--brand-soft)", cursor: "default" }}>Cámaras</a>.
              </p>
            </div>
          )}

          {tab === "notif" && (
            <div className="panel">
              <h3 className="docs-h3">Canales de notificación</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {[
                  ["email", "Email", "Enviar alertas críticas a agostina.b@strumia.ypf"],
                  ["push", "Notificaciones push", "Push al navegador cuando el dashboard está abierto"],
                  ["telegram", "Telegram", "Canal de equipo @strumia-ops (próximamente)"],
                ].map(([k, name, desc]) => (
                  <div key={k} style={{
                    padding: "12px 14px", background: "var(--bg-3)", border: "1px solid var(--line)", borderRadius: 'var(--radius-lg)',
                    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14
                  }}>
                    <div>
                      <div style={{ fontSize: 15, color: "var(--fg-0)", fontWeight: 500 }}>{name}</div>
                      <div style={{ fontSize: 13, color: "var(--fg-2)", marginTop: 3 }}>{desc}</div>
                    </div>
                    <Switch on={notif[k]} onClick={() => setNotif({ ...notif, [k]: !notif[k] })} />
                  </div>
                ))}
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

function Field({ label, value, readonly, mono }) {
  return (
    <div className="form-field">
      <label>{label}</label>
      <input type="text" defaultValue={value} readOnly={readonly}
        className={mono ? "mono" : ""}
        style={{ opacity: readonly ? .7 : 1 }} />
    </div>
  );
}

function Slider({ label, v, min, max, step = 1, unit, onChange }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 14.5, color: "var(--fg-1)" }}>{label}</span>
        <span className="mono" style={{ fontSize: 14, color: "var(--fg-0)", fontWeight: 500 }}>
          {v} <span style={{ color: "var(--fg-3)", fontWeight: 400 }}>{unit}</span>
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={v}
        onChange={(e) => onChange(+e.target.value)}
        style={{ width: "100%", accentColor: "var(--brand-soft)" }} />
    </div>
  );
}

function Switch({ on, onClick }) {
  return (
    <button onClick={onClick} style={{
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

import React from 'react'
import { useToast, PageHeader } from '../components/Toast'
import { IcoMore } from '../components/Icons'
import { useTheme } from '../components/useTheme'

// SETTINGS page (las paginas de Mapa de calor, Tracking y Stock se eliminaron)

// Umbral de alerta: la espera maxima en caja. Se guarda en el servidor (/api/configuracion) y /api/alertas lo usa
// para levantar la alerta "Espera larga en caja".
// La espera se maneja en MINUTOS en toda la app (igual que el reporte de espera en caja).
export const LIMITES_UMBRALES = {
  wait:  { min: 1, max: 15, step: 0.5 },   // minutos de espera
};
// Valores por defecto mientras carga /api/configuracion (los mismos que POR_DEFECTO en frontend/api/configuracion.py)
export const CONFIG_INICIAL = {
  umbrales: { wait: 4 },
  sucursal: { nombre: "Strumia — Mendoza", direccion: "Av. San Martín 1234", horario: "06:00 – 22:00" },
  push: true,
};

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
  const [thresholds, setThresholds] = React.useState(CONFIG_INICIAL.umbrales);
  const [sucursal, setSucursal] = React.useState(CONFIG_INICIAL.sucursal);
  const [push, setPush] = React.useState(CONFIG_INICIAL.push);
  const [guardando, setGuardando] = React.useState(false);

  // Lo guardado en el servidor; si no responde quedan los valores por defecto.
  React.useEffect(() => {
    let vivo = true;
    fetch("/api/configuracion")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!vivo || !d || d.error) return;
        if (d.umbrales) setThresholds({ ...CONFIG_INICIAL.umbrales, ...d.umbrales });
        if (d.sucursal) setSucursal({ ...CONFIG_INICIAL.sucursal, ...d.sucursal });
        if (typeof d.push === "boolean") setPush(d.push);
      })
      .catch(() => {});
    return () => { vivo = false; };
  }, []);

  const guardar = () => {
    const invalido = Object.keys(LIMITES_UMBRALES).find((k) => !umbralValido(k, thresholds[k]));
    if (invalido) {
      const { min, max } = LIMITES_UMBRALES[invalido];
      toast(`La espera máxima debe estar entre ${min} y ${max}`, { kind: "warn" });
      setTab("thresholds");
      return;
    }
    const vacio = [["nombre", "El nombre"], ["direccion", "La dirección"], ["horario", "El horario operativo"]]
      .find(([k]) => !String(sucursal[k] || "").trim());
    if (vacio) {
      toast(`${vacio[1]} de la sucursal no puede quedar vacío`, { kind: "warn" });
      setTab("general");
      return;
    }
    setGuardando(true);
    fetch("/api/configuracion", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ umbrales: thresholds, sucursal, push }),
    })
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!ok || d.error) { toast(`No se pudieron guardar los cambios${d.error ? `: ${d.error}` : ""}`, { kind: "warn" }); return; }
        toast("Cambios guardados", { kind: "success" });
      })
      .catch(() => toast("No se pudieron guardar los cambios: el servidor no responde", { kind: "warn" }))
      .finally(() => setGuardando(false));
  };
  const campoSucursal = (k) => ({ value: sucursal[k], onChange: (v) => setSucursal({ ...sucursal, [k]: v }) });

  return (
    <main className="content docs">
      <PageHeader
        title="Configuración"
        subtitle="Ajustes del sistema y umbrales de alertas."
        right={<button className="btn-pri" onClick={guardar} disabled={guardando}>{guardando ? "Guardando…" : "Guardar cambios"}</button>}
      />

      <div className="settings-layout">
        <nav className="settings-nav">
          {[
            ["general","General"],
            ["thresholds","Umbrales de alertas"],
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
                <Field label="Nombre" {...campoSucursal("nombre")} />
                <Field label="Dirección" {...campoSucursal("direccion")} />
                <Field label="Zona horaria" value="America/Argentina/Mendoza" readonly />
                <Field label="Horario operativo" {...campoSucursal("horario")} />
              </div>
              <h3 className="docs-h3" style={{ marginTop: 24 }}>Sistema</h3>
              <div className="form-grid">
                <Field label="Modelo de detección" value="YOLOv8m" readonly mono />
                <Field label="Tracker" value="ByteTrack" readonly mono />
                <Field label="Frame skip" value="3" readonly mono />
                <Field label="Versión" value="OptiFull v0.3.0" readonly mono />
              </div>
            </div>
          )}

          {tab === "thresholds" && (
            <div className="panel">
              <h3 className="docs-h3">Umbrales que generan alertas</h3>
              <p style={{ fontSize: 14, color: "var(--fg-2)", margin: "0 0 18px" }}>
                Define cuándo el sistema dispara cada tipo de alerta. Los cambios se aplican a la lista de Alertas al guardar.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <Slider label="Espera máxima" v={thresholds.wait} {...LIMITES_UMBRALES.wait} unit="min"
                  ayuda="Minutos que espera un cliente en la caja a partir de los cuales se levanta la alerta “Espera larga en caja”."
                  onChange={(v) => setThresholds({...thresholds, wait: v})} />
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
// mouse, y se ven distintos de los editables (ver .form-field.ro en index.css). Los editables son controlados
// (onChange) para que "Guardar cambios" mande lo que se escribio.
function Field({ label, value, onChange, readonly, mono }) {
  const id = React.useId();
  return (
    <div className={readonly ? "form-field ro" : "form-field"} title={readonly ? "Solo lectura" : undefined}>
      <label htmlFor={id}>{label}</label>
      <input id={id} type="text" value={value} readOnly={readonly} disabled={readonly} maxLength={120}
        onChange={readonly ? undefined : (e) => onChange(e.target.value)}
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

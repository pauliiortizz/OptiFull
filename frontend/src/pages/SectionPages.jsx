import React, { useState, useEffect, useRef, useReducer, useMemo, useCallback, createContext, useContext } from 'react'
import { useToast, ToastCtx, PageHeader, WipBanner } from '../components/Toast'
import { IcoPlay, IcoChev, IcoCheck2 } from '../components/Icons'
import { useAlertas } from '../components/useAlertas'

// Relativo para eventos recientes (legible de un vistazo); a partir de las
// 24h el "hace Nh" deja de ser útil (puede acumular cientos de horas con
// datos de prueba viejos) -- se muestra la fecha y hora exacta, que es lo
// que pide un timestamp de auditoría real.
function formatTiempoAlerta(ts) {
  const secs = Math.floor((Date.now() - ts) / 1000);
  if (secs < 60) return { texto: `hace ${secs}s`, exacto: new Date(ts).toLocaleString("es-AR") };
  if (secs < 3600) return { texto: `hace ${Math.floor(secs / 60)}m`, exacto: new Date(ts).toLocaleString("es-AR") };
  if (secs < 86400) return { texto: `hace ${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`, exacto: new Date(ts).toLocaleString("es-AR") };
  const d = new Date(ts);
  return {
    texto: d.toLocaleDateString("es-AR", { day: "2-digit", month: "short" }) + " " + d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hour12: false }),
    exacto: d.toLocaleString("es-AR"),
  };
}

// All section pages — Alerts, Reports, Heatmap, Tracking, Stock, Cameras, Settings

// ═════════════════════════════════════════════════════════════
// VIDEO MODAL
// ═════════════════════════════════════════════════════════════
function VideoModal({ alert, onClose }) {
  const [sessions, setSessions]   = React.useState([]);
  const [localVids, setLocalVids] = React.useState([]);
  const [src, setSrc]             = React.useState(null);
  const [loading, setLoading]     = React.useState(true);
  const [videoError, setVideoError] = React.useState(false);
  const videoRef = React.useRef(null);

  React.useEffect(() => {
    Promise.all([
      fetch('/api/sessions').then(r => r.json()).catch(() => []),
      fetch('/api/videos').then(r => r.json()).catch(() => []),
    ]).then(([sess, vids]) => {
      setSessions(sess);
      setLocalVids(vids);

      // Alertas reales ya traen la sesion y el offset EXACTOS del momento
      // detectado (ver /api/alertas) -- eso siempre le gana a buscar "alguna"
      // sesion de esa camara, que solo era una aproximacion para las alertas
      // mock (sin sesion_id propio).
      if (alert.sesion_id) {
        setSrc(`/api/sessions/${alert.sesion_id}/clip?t=${alert.offset_seg || 0}&dur=50`);
        setLoading(false);
        return;
      }

      const available = sess.filter(s => s.disponible);
      const match     = available.find(s => s.camara_id === alert.cam);
      const first     = available[0];

      if (match) {
        setSrc(`/api/sessions/${match.id}/clip?t=${match.offset_seg || 0}&dur=50`);
      } else if (first) {
        setSrc(`/api/sessions/${first.id}/clip?t=${first.offset_seg || 0}&dur=50`);
      } else if (vids.length > 0) {
        setSrc(`/api/video/${vids[(alert.cam - 1) % vids.length]}`);
      }
      setLoading(false);
    });
  }, [alert.cam, alert.sesion_id, alert.offset_seg]);

  React.useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Resetear error al cambiar de fuente
  const handleSrcChange = (url) => { setVideoError(false); setSrc(url); };

  const allSources = [
    ...sessions.filter(s => s.disponible).map(s => {
      const offset  = s.offset_seg || 0;
      const mm      = String(Math.floor(offset / 60)).padStart(2, '0');
      const ss      = String(offset % 60).padStart(2, '0');
      const clipUrl = `/api/sessions/${s.id}/clip?t=${offset}&dur=50`;
      return {
        key:      `sess-${s.id}`,
        label:    s.nombre,
        sub:      `cam-${s.camara_id} · desde ${mm}:${ss}`,
        url:      clipUrl,
        download: `/api/sessions/${s.id}/video`,
      };
    }),
    ...localVids.map(v => ({
      key:      `local-${v}`,
      label:    v,
      sub:      'carpeta videos/',
      url:      `/api/video/${v}`,
      download: `/api/video/${v}`,
    })),
  ];

  const currentSource = allSources.find(s => s.url === src);

  return (
    <div className="vm-overlay" onClick={onClose}>
      <div className="vm-modal" onClick={e => e.stopPropagation()}>

        <div className="vm-header">
          <div className="vm-header-info">
            <div className="vm-title">{alert.title}</div>
            <div className="vm-meta">
              <span className={`alert-dot ${alert.sev}`} style={{ marginTop: 0, flexShrink: 0 }} />
              <span className="mono">cam-{alert.cam}</span>
              <span style={{ color: 'var(--fg-3)' }}>·</span>
              <span>{alert.zone}</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {src && (
              <a
                href={src}
                download
                className="vm-download"
                title="Descargar video"
                onClick={e => e.stopPropagation()}
              >
                ⬇ Descargar
              </a>
            )}
            <button className="vm-close" onClick={onClose}>✕</button>
          </div>
        </div>

        <div className="vm-player">
          {loading ? (
            <div className="vm-placeholder">Buscando video…</div>
          ) : src && !videoError ? (
            <video
              ref={videoRef}
              key={src}
              controls
              autoPlay
              className="vm-video"
              onError={() => setVideoError(true)}
            >
              <source src={src} />
            </video>
          ) : src && videoError ? (
            <div className="vm-placeholder">
              <div style={{ fontSize: 27.5, marginBottom: 10 }}>⚠️</div>
              <div style={{ color: 'var(--fg-1)', fontWeight: 500 }}>El navegador no puede reproducir este video</div>
              <div style={{ fontSize: 13, color: 'var(--fg-3)', marginTop: 6, marginBottom: 14 }}>
                El archivo puede estar codificado en H.265/HEVC. Descargalo para verlo en VLC u otro reproductor.
              </div>
              <a href={src} download className="btn-pri" style={{ textDecoration: 'none', padding: '8px 18px', borderRadius: 4 }}>
                ⬇ Descargar video
              </a>
            </div>
          ) : (
            <div className="vm-placeholder">
              <div style={{ fontSize: 27.5, marginBottom: 8 }}>📹</div>
              <div>No se encontró video en disco</div>
              <div style={{ fontSize: 12.5, color: 'var(--fg-3)', marginTop: 4 }}>
                Verificá que el archivo de video esté accesible
              </div>
            </div>
          )}
        </div>

        {allSources.length > 0 && (
          <div className="vm-sources">
            <div className="vm-sources-lbl">Videos disponibles</div>
            <div className="vm-sources-list">
              {allSources.map(s => (
                <button
                  key={s.key}
                  className={`vm-source-btn${src === s.url ? ' active' : ''}`}
                  onClick={() => handleSrcChange(s.url)}
                >
                  <span className="vm-source-name">{s.label}</span>
                  <span className="vm-source-sub">{s.sub}</span>
                </button>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// EVIDENCIA DE LA ALERTA (frames + clip del momento detectado)
// ═══════════════════════════════════════════════════════

// Hora (HH:MM:SS) de un timestamp ISO de la evidencia
const horaDe = (iso) => (iso ? new Date(iso).toLocaleTimeString("es-AR", { hour12: false }) : "");

// Tira de miniaturas de los frames clave; al tocar una se abre la evidencia con ese frame.
function EvidenciaFrames({ evidencia, onElegir }) {
  return (
    <div className="ev-strip">
      {evidencia.frames.map((f, i) => (
        <button key={f.url} type="button" className="ev-thumb" title={f.etiqueta}
          onClick={(e) => { e.stopPropagation(); onElegir(i); }}>
          <img src={f.url} alt={f.etiqueta} loading="lazy" />
          <span className="ev-thumb-lbl">{f.etiqueta}</span>
          <span className="ev-thumb-ts mono">{horaDe(f.ts)}</span>
        </button>
      ))}
    </div>
  );
}

// Ventana con la evidencia de un posible hurto: el clip del momento y los frames donde se detecto. 'inicial' es el
// frame que se abre primero (null = el clip, o el primer frame si no hay clip).
function EvidenciaModal({ alert, inicial = null, onClose }) {
  const ev = alert.evidencia;
  const [indice, setIndice] = React.useState(inicial ?? (ev.video ? null : 0));   // null = mostrando el clip
  const [errorVideo, setErrorVideo] = React.useState(false);

  React.useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setIndice((i) => Math.min(ev.frames.length - 1, (i ?? -1) + 1));
      if (e.key === "ArrowLeft")  setIndice((i) => (i === null ? null : i === 0 && ev.video ? null : Math.max(0, i - 1)));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, ev]);

  const frame = indice === null ? null : ev.frames[indice];
  return (
    <div className="vm-overlay" onClick={onClose}>
      <div className="vm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="vm-header">
          <div className="vm-header-info">
            <div className="vm-title">{alert.title}</div>
            <div className="vm-meta">
              <span className={`alert-dot ${alert.sev}`} style={{ marginTop: 0, flexShrink: 0 }} />
              <span className="mono">cam-{alert.cam}</span>
              <span style={{ color: "var(--fg-3)" }}>·</span>
              <span>{alert.zone}</span>
              <span style={{ color: "var(--fg-3)" }}>·</span>
              <span className="mono">{new Date(alert.ts).toLocaleString("es-AR")}</span>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {ev.video && indice === null && <a href={ev.video} download className="vm-download" title="Descargar clip" onClick={(e) => e.stopPropagation()}>⬇ Descargar</a>}
            {frame && <a href={frame.url} download className="vm-download" title="Descargar frame" onClick={(e) => e.stopPropagation()}>⬇ Frame</a>}
            <button className="vm-close" onClick={onClose}>✕</button>
          </div>
        </div>

        <div className="vm-player">
          {indice === null && ev.video && !errorVideo ? (
            <video key={ev.video} controls autoPlay muted loop className="vm-video" onError={() => setErrorVideo(true)}>
              <source src={ev.video} type="video/mp4" />
            </video>
          ) : indice === null ? (
            <div className="vm-placeholder">No se pudo reproducir el clip. Usá los frames de abajo o descargalo.</div>
          ) : (
            <img className="vm-video ev-main-img" src={frame.url} alt={frame.etiqueta} />
          )}
          {frame && <div className="ev-caption">{frame.etiqueta} · <span className="mono">{horaDe(frame.ts)}</span></div>}
        </div>

        <div className="vm-sources">
          <div className="vm-sources-lbl">
            Frames donde se detectó ({ev.frames.length}){ev.video && (
              <button type="button" className={`ev-clip-btn${indice === null ? " on" : ""}`} onClick={() => { setIndice(null); setErrorVideo(false); }}>▶ Ver clip</button>
            )}
          </div>
          <div className="ev-strip">
            {ev.frames.map((f, i) => (
              <button key={f.url} type="button" className={`ev-thumb${indice === i ? " on" : ""}`} onClick={() => setIndice(i)}>
                <img src={f.url} alt={f.etiqueta} loading="lazy" />
                <span className="ev-thumb-lbl">{f.etiqueta}</span>
                <span className="ev-thumb-ts mono">{horaDe(f.ts)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// PERSONA POSIBLEMENTE EMPLEADA (foto + decision)
// ═══════════════════════════════════════════════════════

// Foto de la persona detectada y los dos botones para decidir. Si es empleada se la excluye de las métricas.
function FotoModal({ alert, decidiendo, onDecidir, onClose }) {
  React.useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const resuelta = alert.status === "resolved";
  return (
    <div className="vm-overlay" onClick={onClose}>
      <div className="vm-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={alert.title}>
        <div className="vm-header">
          <div className="vm-header-info">
            <div className="vm-title">{alert.title}</div>
            <div className="vm-meta">
              <span className="mono">cam-{alert.cam}</span>
              <span style={{ color: "var(--fg-3)" }}>·</span>
              <span className="mono">Persona #{alert.persona_id}</span>
              <span style={{ color: "var(--fg-3)" }}>·</span>
              <span className="mono">{new Date(alert.ts).toLocaleString("es-AR")}</span>
            </div>
          </div>
          <button className="vm-close" onClick={onClose} aria-label="Cerrar">✕</button>
        </div>
        <div className="vm-player">
          {alert.foto
            ? <img className="vm-video foto-persona" src={alert.foto} alt={`Foto de la persona #${alert.persona_id}`} />
            : <div className="vm-placeholder">Todavía no hay una foto de esta persona.</div>}
        </div>
        <div className="vm-sources">
          <div className="dt-expand-val" style={{ marginBottom: 12 }}>{alert.desc}</div>
          {!resuelta && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button className="btn-pri" disabled={decidiendo} onClick={() => onDecidir(alert, true)}>Es empleado</button>
              <button className="btn-sec" disabled={decidiendo} onClick={() => onDecidir(alert, false)}>No es empleado</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════
// ALERTS PAGE
// ═══════════════════════════════════════════════════════

function AlertsPage() {
  const toast = useToast();
  const { alertas, loading: loadingAlertas, refresh: refreshAlertas } = useAlertas();
  const [sevFilter, setSevFilter] = React.useState("all");
  const [statusFilter, setStatusFilter] = React.useState("all");
  const [zone, setZone] = React.useState("all");
  const [expanded, setExpanded] = React.useState(null);
  const [videoAlert, setVideoAlert] = React.useState(null);
  const [frameInicial, setFrameInicial] = React.useState(null);   // frame con el que abre la evidencia (null = el clip)
  const verAlerta = (a, frame = null) => { setFrameInicial(frame); setVideoAlert(a); };
  const [resolviendo, setResolviendo] = React.useState(null);
  const [fotoAlert, setFotoAlert] = React.useState(null);   // alerta de posible empleado con su foto abierta
  const [, force] = React.useReducer((x) => x + 1, 0);

  React.useEffect(() => { const id = setInterval(force, 10000); return () => clearInterval(id); }, []);

  const zones = ["all", ...Array.from(new Set(alertas.map(a => a.zone)))];

  const filtered = alertas.filter(a =>
    (sevFilter === "all" || a.sev === sevFilter) &&
    (statusFilter === "all" || a.status === statusFilter) &&
    (zone === "all" || a.zone === zone)
  );

  const stats = {
    total: alertas.length,
    critical: alertas.filter(a => a.sev === "critical").length,
    open: alertas.filter(a => a.status === "open").length,
    resolved: alertas.filter(a => a.status === "resolved").length,
  };
  const pctResueltas = stats.total ? Math.round((stats.resolved / stats.total) * 100) : 0;

  const resolve = (id) => {
    setResolviendo(id);
    fetch(`/api/alertas/${id}/resolver`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resuelta: true }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) { toast(d.error, { kind: "warn" }); return; }
        toast(`Alerta #${id} resuelta`, { kind: "success" });
        refreshAlertas();
      })
      .catch(() => toast("No se pudo resolver la alerta", { kind: "warn" }))
      .finally(() => setResolviendo(null));
  };

  // Decisión del usuario sobre una persona posiblemente empleada: si es empleada se excluye de las métricas; si no, sigue
  // contando como cliente. En ambos casos la persona deja de sugerirse.
  const decidirEmpleado = (a, esEmpleado) => {
    setResolviendo(a.id);
    fetch(`/api/personas/${a.persona_id}/empleado`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ es_empleado: esEmpleado, revisado: true }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) { toast(d.error, { kind: "warn" }); return; }
        toast(esEmpleado
          ? `Persona #${a.persona_id} marcada como empleada — excluida de las métricas`
          : `Persona #${a.persona_id} confirmada como cliente`, { kind: "success" });
        setFotoAlert(null);
        refreshAlertas();
      })
      .catch(() => toast("No se pudo guardar la decisión", { kind: "warn" }))
      .finally(() => setResolviendo(null));
  };
  const esEmpleadoAlert = (a) => a.tipo === "posible_empleado";

  return (
    <main className="content docs">
      <PageHeader
        title="Alertas"
        subtitle="Eventos críticos y operativos detectados por el sistema de visión."
      />

      {/* Stats row */}
      <div className="stat-row stat-row-4">
        <div className="stat-mini"><span className="stat-mini-lbl">Total</span><span className="stat-mini-val mono">{stats.total}</span></div>
        <div className="stat-mini" data-tone="alert"><span className="stat-mini-lbl">Críticas</span><span className="stat-mini-val mono">{stats.critical}</span></div>
        <div className="stat-mini" data-tone="warn"><span className="stat-mini-lbl">Abiertas</span><span className="stat-mini-val mono">{stats.open}</span></div>
        <div className="stat-mini" data-tone="pos"><span className="stat-mini-lbl">Resueltas</span>
          <span className="stat-mini-val mono">{stats.resolved}</span>
          {stats.total > 0 && <span className="stat-mini-sub">{pctResueltas}% del total</span>}
        </div>
      </div>

      {/* Filters */}
      <div className="filter-bar">
        <div className="filter-grp">
          <span className="filter-lbl">Severidad</span>
          <div className="seg">
            {[["all","Todas"],["critical","Crítica"],["warn","Warning"],["info","Info"]].map(([k,l]) => (
              <button key={k} className={sevFilter===k?"on":""} onClick={() => setSevFilter(k)}>{l}</button>
            ))}
          </div>
        </div>
        <div className="filter-grp">
          <span className="filter-lbl">Estado</span>
          <div className="seg">
            {[["all","Todos"],["open","Abierta"],["resolved","Resuelta"]].map(([k,l]) => (
              <button key={k} className={statusFilter===k?"on":""} onClick={() => setStatusFilter(k)}>{l}</button>
            ))}
          </div>
        </div>
        <div className="filter-grp">
          <span className="filter-lbl">Zona</span>
          <select className="select-input" value={zone} onChange={(e) => setZone(e.target.value)}>
            {zones.map(z => <option key={z} value={z}>{z === "all" ? "Todas las zonas" : z}</option>)}
          </select>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 13, color: "var(--fg-3)" }} className="mono">
          {filtered.length} / {alertas.length} eventos
        </div>
      </div>

      {/* Table */}
      <div className="data-table">
        <div className="dt-head dt-row dt-alerts">
          <div></div>
          <div>Evento</div>
          <div>Zona</div>
          <div>Cámara</div>
          <div>Tiempo</div>
          <div>Estado</div>
          <div></div>
          <div></div>
        </div>
        {loadingAlertas && (
          <div style={{ padding: 40, textAlign: "center", color: "var(--fg-3)", fontSize: 15 }}>
            Cargando alertas…
          </div>
        )}
        {!loadingAlertas && filtered.length === 0 && (
          <div style={{ padding: 40, textAlign: "center", color: "var(--fg-3)", fontSize: 15 }}>
            No hay alertas con los filtros aplicados.
          </div>
        )}
        {filtered.map(a => {
          const isOpen = expanded === a.id;
          const tiempo = formatTiempoAlerta(a.ts);
          return (
            <div key={a.id}>
              <div className={`dt-row dt-alerts ${isOpen ? "expanded" : ""}`} onClick={() => setExpanded(isOpen ? null : a.id)}>
                <div><span className={`alert-dot ${a.sev}`} style={{ marginTop: 0 }} /></div>
                <div style={esEmpleadoAlert(a) ? { display: "flex", gap: 12, alignItems: "center", minWidth: 0 } : undefined}>
                  {esEmpleadoAlert(a) && (a.foto
                    ? <img className="alert-foto" src={a.foto} alt={`Persona #${a.persona_id}`} loading="lazy" />
                    : <span className="alert-foto alert-foto-vacia" aria-hidden="true">?</span>)}
                  <div style={{ minWidth: 0 }}>
                    <div style={{ color: "var(--fg-0)", fontWeight: 500, fontSize: 14.5 }}>
                      {a.title}{a.evidencia && <span className="ev-pill" title="Esta alerta tiene el clip y los frames del momento">▶ Evidencia</span>}
                    </div>
                    <div style={{ color: "var(--fg-2)", fontSize: 13, marginTop: 2 }}>{a.desc}</div>
                  </div>
                </div>
                <div style={{ color: "var(--fg-1)", fontSize: 14 }}>{a.zone}</div>
                <div className="mono" style={{ color: "var(--fg-2)", fontSize: 13 }}>cam-{a.cam}</div>
                <div className="mono" style={{ color: "var(--fg-2)", fontSize: 13 }} title={tiempo.exacto}>{tiempo.texto}</div>
                <div>{statusBadge(a.status)}</div>
                <div className="dt-quick-actions">
                  <button className="dt-quick-btn" title={esEmpleadoAlert(a) ? "Ver foto" : a.evidencia ? "Ver evidencia" : "Ver clip"}
                    onClick={(e) => { e.stopPropagation(); if (esEmpleadoAlert(a)) setFotoAlert(a); else verAlerta(a); }}>
                    <IcoPlay style={{ width: 11, height: 11 }} />
                  </button>
                  {a.status !== "resolved" && !esEmpleadoAlert(a) && (
                    <button className="dt-quick-btn" title="Resolver" disabled={resolviendo === a.id}
                      onClick={(e) => { e.stopPropagation(); resolve(a.id); }}>
                      <IcoCheck2 style={{ width: 11, height: 11 }} />
                    </button>
                  )}
                </div>
                <div style={{ color: "var(--fg-3)" }}><IcoChev style={{ transform: isOpen ? "rotate(90deg)" : "none", transition: "transform .15s" }} /></div>
              </div>
              {isOpen && (
                <div className="dt-expand">
                  <div className="dt-expand-grid">
                    <div>
                      <div className="dt-expand-lbl">{esEmpleadoAlert(a) ? "Tiempo en la tienda" : "Secuencia de zonas"}</div>
                      <div className="dt-expand-val">{esEmpleadoAlert(a)
                        ? `${Math.floor(a.minutos / 60)} h ${String(a.minutos % 60).padStart(2, "0")} min`
                        : (a.secuencia?.length ? a.secuencia.join(" → ") : "—")}</div>
                    </div>
                    <div>
                      <div className="dt-expand-lbl">Persona</div>
                      <div className="dt-expand-val mono">#{a.persona_id}</div>
                    </div>
                    <div>
                      <div className="dt-expand-lbl">Detectado a las</div>
                      <div className="dt-expand-val mono">{new Date(a.ts).toLocaleTimeString("es-AR")}</div>
                    </div>
                    <div>
                      <div className="dt-expand-lbl">Acciones</div>
                      <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                        {esEmpleadoAlert(a) ? (
                          <>
                            {a.status !== "resolved" && (
                              <>
                                <button className="btn-pri" disabled={resolviendo === a.id}
                                  onClick={(e) => {e.stopPropagation(); decidirEmpleado(a, true);}}>Es empleado</button>
                                <button className="btn-sec" disabled={resolviendo === a.id}
                                  onClick={(e) => {e.stopPropagation(); decidirEmpleado(a, false);}}>No es empleado</button>
                              </>
                            )}
                            <button className="btn-sec" onClick={(e) => {e.stopPropagation(); setFotoAlert(a);}}><IcoPlay style={{ marginRight: 4 }} />Ver foto</button>
                          </>
                        ) : (
                          <>
                            {a.status !== "resolved" && (
                              <button className="btn-pri" disabled={resolviendo === a.id}
                                onClick={(e) => {e.stopPropagation(); resolve(a.id);}}>
                                {resolviendo === a.id ? "Resolviendo…" : "Resolver"}
                              </button>
                            )}
                            <button className="btn-sec" onClick={(e) => {e.stopPropagation(); verAlerta(a);}}><IcoPlay style={{ marginRight: 4 }} />{a.evidencia ? "Ver evidencia" : "Ver video"}</button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  {esEmpleadoAlert(a) ? (
                    <div className="ev-block">
                      <div className="dt-expand-lbl">Foto de la persona</div>
                      {a.foto
                        ? <img className="foto-persona-mini" src={a.foto} alt={`Persona #${a.persona_id}`} loading="lazy"
                            onClick={(e) => { e.stopPropagation(); setFotoAlert(a); }} />
                        : <div className="dt-expand-val" style={{ color: "var(--fg-3)" }}>Todavía no hay una foto de esta persona (se guarda cuando lleva un rato en cámara).</div>}
                    </div>
                  ) : a.evidencia ? (
                    <div className="ev-block">
                      <div className="dt-expand-lbl">Frames donde se detectó ({a.evidencia.frames.length}){a.evidencia.video ? " · clip disponible" : ""}</div>
                      <EvidenciaFrames evidencia={a.evidencia} onElegir={(i) => verAlerta(a, i)} />
                    </div>
                  ) : (Date.now() - a.ts < 180000 && (
                    <div className="ev-block"><div className="dt-expand-lbl">Evidencia</div><div className="dt-expand-val" style={{ color: "var(--fg-3)" }}>Preparando el clip y los frames…</div></div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {fotoAlert && (
        <FotoModal alert={alertas.find(x => x.id === fotoAlert.id) || fotoAlert} decidiendo={resolviendo === fotoAlert.id}
          onDecidir={decidirEmpleado} onClose={() => setFotoAlert(null)} />
      )}
      {videoAlert && (videoAlert.evidencia
        ? <EvidenciaModal key={`${videoAlert.id}-${frameInicial}`} alert={videoAlert} inicial={frameInicial} onClose={() => setVideoAlert(null)} />
        : <VideoModal alert={videoAlert} onClose={() => setVideoAlert(null)} />)}
    </main>
  );
}

function statusBadge(s) {
  const map = {
    open:     { label: "Abierta",  color: "var(--alert-soft)", bg: "rgba(192,57,43,.12)",  border: "rgba(226,92,78,.25)" },
    resolved: { label: "Resuelta", color: "var(--pos-soft)",    bg: "rgba(46,163,79,.1)",   border: "rgba(46,163,79,.22)" },
  };
  const x = map[s];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 99,
      fontSize: 12.5, fontWeight: 500, color: x.color, background: x.bg, border: `1px solid ${x.border}`, whiteSpace: "nowrap"
    }}>
      {x.label}
    </span>
  );
}

export { AlertsPage }

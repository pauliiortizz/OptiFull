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
  }, [alert.cam]);

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
              <div style={{ fontSize: 24, marginBottom: 10 }}>⚠️</div>
              <div style={{ color: 'var(--fg-1)', fontWeight: 500 }}>El navegador no puede reproducir este video</div>
              <div style={{ fontSize: 11.5, color: 'var(--fg-3)', marginTop: 6, marginBottom: 14 }}>
                El archivo puede estar codificado en H.265/HEVC. Descargalo para verlo en VLC u otro reproductor.
              </div>
              <a href={src} download className="btn-pri" style={{ textDecoration: 'none', padding: '8px 18px', borderRadius: 8 }}>
                ⬇ Descargar video
              </a>
            </div>
          ) : (
            <div className="vm-placeholder">
              <div style={{ fontSize: 24, marginBottom: 8 }}>📹</div>
              <div>No se encontró video en disco</div>
              <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 4 }}>
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

// ═════════════════════════════════════════════════════════════
// ALERTS PAGE
// ═════════════════════════════════════════════════════════════
const ALERTS_FULL = [
  { id:1,  sev:"critical", title:"Trayectoria sospechosa detectada",      desc:"Persona se dirige a salida sin pasar por caja",    zone:"Salida",     cam:5, ts:Date.now()-32*1000,           status:"open" },
  { id:2,  sev:"warn",     title:"Tiempo de espera elevado en Caja 2",     desc:"5 personas en cola · espera estimada 4:30 min",     zone:"Caja 2",     cam:7, ts:Date.now()-2*60*1000,         status:"open" },
  { id:3,  sev:"critical", title:"Stock crítico: Coca-Cola 500ml",         desc:"Detectados 2 unidades · esperado: 24",              zone:"Góndola B3", cam:3, ts:Date.now()-8*60*1000,         status:"open" },
  { id:4,  sev:"info",     title:"Pico de circulación detectado",          desc:"31 personas simultáneas — récord del día",          zone:"Tienda",     cam:1, ts:Date.now()-14*60*1000,        status:"ack" },
  { id:5,  sev:"warn",     title:"Cámara playa-2 con baja confianza",      desc:"Confianza promedio 47% durante 15 min",             zone:"Playa",      cam:2, ts:Date.now()-22*60*1000,        status:"ack" },
  { id:6,  sev:"warn",     title:"Permanencia prolongada",                 desc:"Persona en zona de heladera por 4:12 min",          zone:"Heladera",   cam:4, ts:Date.now()-38*60*1000,        status:"open" },
  { id:7,  sev:"critical", title:"Aglomeración en cafetería",              desc:"Densidad > 1.8 pers/m² durante 3 min",              zone:"Cafetería",  cam:6, ts:Date.now()-52*60*1000,        status:"resolved" },
  { id:8,  sev:"info",     title:"Reposición de góndola completada",       desc:"Stock actualizado en góndola A1 (snacks)",          zone:"Góndola A1", cam:3, ts:Date.now()-72*60*1000,        status:"resolved" },
  { id:9,  sev:"warn",     title:"Cola formándose en Caja 1",              desc:"3 personas · tendencia creciente",                  zone:"Caja 1",     cam:7, ts:Date.now()-92*60*1000,        status:"resolved" },
  { id:10, sev:"info",     title:"Cambio de turno detectado",              desc:"Personal rotó en caja registradora",                zone:"Caja 1",     cam:7, ts:Date.now()-105*60*1000,       status:"resolved" },
  { id:11, sev:"critical", title:"Objeto abandonado",                      desc:"Mochila sin dueño detectada por 5 min",             zone:"Entrada",    cam:1, ts:Date.now()-140*60*1000,       status:"resolved" },
  { id:12, sev:"warn",     title:"Stock medio: Agua mineral 1.5L",         desc:"Detectados 6 unidades · umbral: 10",                zone:"Góndola C2", cam:4, ts:Date.now()-180*60*1000,       status:"resolved" },
];

function AlertsPage() {
  const toast = useToast();
  const [sevFilter, setSevFilter] = React.useState("all");
  const [statusFilter, setStatusFilter] = React.useState("all");
  const [zone, setZone] = React.useState("all");
  const [expanded, setExpanded] = React.useState(null);
  const [videoAlert, setVideoAlert] = React.useState(null);
  const [, force] = React.useReducer((x) => x + 1, 0);

  React.useEffect(() => { const id = setInterval(force, 10000); return () => clearInterval(id); }, []);

  const zones = ["all", ...Array.from(new Set(ALERTS_FULL.map(a => a.zone)))];

  const filtered = ALERTS_FULL.filter(a =>
    (sevFilter === "all" || a.sev === sevFilter) &&
    (statusFilter === "all" || a.status === statusFilter) &&
    (zone === "all" || a.zone === zone)
  );

  const stats = {
    total: ALERTS_FULL.length,
    critical: ALERTS_FULL.filter(a => a.sev === "critical").length,
    open: ALERTS_FULL.filter(a => a.status === "open").length,
    resolved: ALERTS_FULL.filter(a => a.status === "resolved").length,
  };

  const acknowledge = (id) => toast(`Alerta #${id} marcada como atendida`, { kind: "success" });
  const resolve = (id) => toast(`Alerta #${id} resuelta`, { kind: "success" });

  return (
    <main className="content docs">
      <PageHeader
        title="Alertas"
        subtitle="Eventos críticos y operativos detectados por el sistema de visión."
        right={
          <>
            <button className="btn-sec" onClick={() => toast("Exportando alertas a CSV…", { kind: "info" })}>
              <IcoDownload style={{ marginRight: 6 }} />Exportar
            </button>
            <button className="btn-pri" onClick={() => toast("Configuración de umbrales abierta")}>
              <IcoSettings style={{ marginRight: 6 }} />Configurar reglas
            </button>
          </>
        }
      />

      {/* Stats row */}
      <div className="stat-row">
        <div className="stat-mini"><span className="stat-mini-lbl">Total hoy</span><span className="stat-mini-val mono">{stats.total}</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">Críticas</span><span className="stat-mini-val mono" style={{ color: "var(--alert-soft)" }}>{stats.critical}</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">Abiertas</span><span className="stat-mini-val mono" style={{ color: "var(--warn)" }}>{stats.open}</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">Resueltas</span><span className="stat-mini-val mono" style={{ color: "var(--pos-soft)" }}>{stats.resolved}</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">T. resp. promedio</span><span className="stat-mini-val mono">3:42</span></div>
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
            {[["all","Todos"],["open","Abierta"],["ack","Atendida"],["resolved","Resuelta"]].map(([k,l]) => (
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
        <div style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--fg-3)" }} className="mono">
          {filtered.length} / {ALERTS_FULL.length} eventos
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
        </div>
        {filtered.length === 0 && (
          <div style={{ padding: 40, textAlign: "center", color: "var(--fg-3)", fontSize: 13 }}>
            No hay alertas con los filtros aplicados.
          </div>
        )}
        {filtered.map(a => {
          const isOpen = expanded === a.id;
          const secs = Math.floor((Date.now() - a.ts) / 1000);
          const rel = secs < 60 ? `${secs}s` : secs < 3600 ? `${Math.floor(secs/60)}m` : `${Math.floor(secs/3600)}h ${Math.floor((secs%3600)/60)}m`;
          return (
            <div key={a.id}>
              <div className={`dt-row dt-alerts ${isOpen ? "expanded" : ""}`} onClick={() => setExpanded(isOpen ? null : a.id)}>
                <div><span className={`alert-dot ${a.sev}`} style={{ marginTop: 0 }} /></div>
                <div>
                  <div style={{ color: "var(--fg-0)", fontWeight: 500, fontSize: 12.5 }}>{a.title}</div>
                  <div style={{ color: "var(--fg-2)", fontSize: 11.5, marginTop: 2 }}>{a.desc}</div>
                </div>
                <div style={{ color: "var(--fg-1)", fontSize: 12 }}>{a.zone}</div>
                <div className="mono" style={{ color: "var(--fg-2)", fontSize: 11.5 }}>cam-{a.cam}</div>
                <div className="mono" style={{ color: "var(--fg-2)", fontSize: 11.5 }}>hace {rel}</div>
                <div>{statusBadge(a.status)}</div>
                <div style={{ color: "var(--fg-3)" }}><IcoChev style={{ transform: isOpen ? "rotate(90deg)" : "none", transition: "transform .15s" }} /></div>
              </div>
              {isOpen && (
                <div className="dt-expand">
                  <div className="dt-expand-grid">
                    <div>
                      <div className="dt-expand-lbl">Detección</div>
                      <div className="dt-expand-val">YOLOv8 + ByteTrack · conf {Math.round(80 + Math.random()*15)}%</div>
                    </div>
                    <div>
                      <div className="dt-expand-lbl">Track ID</div>
                      <div className="dt-expand-val mono">#{a.id * 17 + 42}</div>
                    </div>
                    <div>
                      <div className="dt-expand-lbl">Frame</div>
                      <div className="dt-expand-val mono">{new Date(a.ts).toLocaleTimeString("es-AR")}</div>
                    </div>
                    <div>
                      <div className="dt-expand-lbl">Acciones</div>
                      <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                        {a.status === "open" && <button className="btn-sec" onClick={(e) => {e.stopPropagation(); acknowledge(a.id);}}>Marcar atendida</button>}
                        {a.status !== "resolved" && <button className="btn-pri" onClick={(e) => {e.stopPropagation(); resolve(a.id);}}>Resolver</button>}
                        <button className="btn-sec" onClick={(e) => {e.stopPropagation(); setVideoAlert(a);}}><IcoPlay style={{ marginRight: 4 }} />Ver video</button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {videoAlert && <VideoModal alert={videoAlert} onClose={() => setVideoAlert(null)} />}
    </main>
  );
}

function statusBadge(s) {
  const map = {
    open:     { label: "Abierta",  color: "var(--alert-soft)", bg: "rgba(192,57,43,.12)",  border: "rgba(226,92,78,.25)" },
    ack:      { label: "Atendida", color: "var(--warn)",        bg: "rgba(214,137,32,.12)", border: "rgba(214,137,32,.25)" },
    resolved: { label: "Resuelta", color: "var(--pos-soft)",    bg: "rgba(46,163,79,.1)",   border: "rgba(46,163,79,.22)" },
  };
  const x = map[s];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 99,
      fontSize: 11, fontWeight: 500, color: x.color, background: x.bg, border: `1px solid ${x.border}`, whiteSpace: "nowrap"
    }}>
      {x.label}
    </span>
  );
}

window.AlertsPage = AlertsPage;

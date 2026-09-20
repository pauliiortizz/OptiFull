import React, { useState, useEffect, useRef, useReducer, useMemo, useCallback, createContext, useContext } from 'react'
import { useToast, ToastCtx, PageHeader, WipBanner } from '../components/Toast'
import { IcoHeat, IcoDownload, IcoCam, IcoTrack, IcoUsers, IcoUser, IcoChip, IcoClock, IcoRewind, IcoPause, IcoPlay, IcoForward, IcoSpinner, IcoMore, IcoSend } from '../components/Icons'
import { KpiCard } from '../components/Sparkline'

// HEATMAP / TRACKING / STOCK / CAMERAS / SETTINGS pages

// Las 4 fotos fijas de frontend/fondos/camara_N.png traen un margen negro
// (pillarbox) identico e IGUAL en las 4 -- 141px de cada lado sobre 2532px
// de ancho total, medido con PIL sobre los 4 archivos (contenido real:
// 2250x1170, alto sin margen). Estas constantes describen ese recorte para
// poder "acercar" la imagen exactamente lo necesario y descartar el margen
// negro, sin distorsionar ni recortar contenido real.
const FONDO_FULL_W    = 2532;
const FONDO_CONTENT_W = 2250; // FONDO_FULL_W - 2*141
const FONDO_CONTENT_H = 1170; // sin margen vertical
const FONDO_ZOOM_PCT  = (FONDO_FULL_W / FONDO_CONTENT_W) * 100; // ~112.53%

// Estilo del <img> de fondo ya "des-pillarboxeado": lo escala para que el
// margen negro caiga fuera del contenedor (que debe tener position:relative
// + overflow:hidden) y lo centra, dejando solo el contenido real visible.
const fondoZoomStyle = (extra) => ({
  position: 'absolute', top: 0, left: '50%',
  width: `${FONDO_ZOOM_PCT}%`, height: '100%',
  transform: 'translateX(-50%)',
  ...extra,
});

// ═════════════════════════════════════════════════════════════
// HEATMAP PAGE — datos reales desde BD
// ═════════════════════════════════════════════════════════════
function useHeatmapData() {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    fetch('/api/heatmap/latest')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

// Mapa acumulado (todos los analisis combinados) de una camara puntual.
const CAMARAS = [
  { id: 1, nombre: 'Caja Derecha' },
  { id: 2, nombre: 'Esquina Full' },
  { id: 3, nombre: 'Caja Frente' },
  { id: 4, nombre: 'Caja Izquierda' },
];

function useHeatmapCamara(camaraId) {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    setLoading(true);
    fetch(`/api/heatmap/camara/${camaraId}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [camaraId]);
  return { data, loading };
}

// Todos los heatmaps INDIVIDUALES (uno por sesion/video analizado, ver
// guardar_heatmap() en deteccion/persistencia.py) de una camara que caigan
// en un mismo dia calendario, en orden cronologico -- ver
// /api/cameras/<id>/heatmaps. A medida que deteccion/main.py analiza mas
// videos y guarda mas heatmaps, este fetch los va trayendo automaticamente
// (no hay nada que actualizar a mano): cada vez que se pide este endpoint
// devuelve el estado actual de la BD para esa camara+dia.
function useCameraHeatmaps(camaraId, fecha) {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  React.useEffect(() => {
    if (!camaraId) { setData(null); return; }
    setLoading(true);
    const qs = fecha ? `?fecha=${fecha}` : '';
    fetch(`/api/cameras/${camaraId}/heatmaps${qs}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [camaraId, fecha]);
  return { data, loading };
}

// Polígonos ROI reales de una cámara (tabla 'zonas' en Postgres) + el ancho/
// alto de frame contra el que fueron calibrados esos polígonos. No hay un
// endpoint dedicado para esto: se reutiliza /api/cameras/<id>/tracking (el
// mismo que arma el mapa de trayectorias) y se descartan trayectorias/
// personas -- evita duplicar lógica de backend solo para esta vista.
function useCameraZonas(camaraId) {
  const [zonas, setZonas] = React.useState([]);
  const [frame, setFrame] = React.useState(null); // { w, h } en px de video
  React.useEffect(() => {
    if (!camaraId) { setZonas([]); setFrame(null); return; }
    fetch(`/api/cameras/${camaraId}/tracking`)
      .then(r => r.json())
      .then(d => {
        setZonas(d?.zonas || []);
        setFrame(d?.sesion?.frame_w && d?.sesion?.frame_h ? { w: d.sesion.frame_w, h: d.sesion.frame_h } : null);
      })
      .catch(() => { setZonas([]); setFrame(null); });
  }, [camaraId]);
  return { zonas, frame };
}

// Tinte por tipo de zona real -- mismo criterio de color que STORE_ZONES en
// FloorPlan.jsx (ambar = caja, azul = góndola, slate = resto).
const TINT_POR_TIPO = { caja: "217,119,6", gondola: "37,99,235", otro: "148,163,184" };

// Overlay vectorial de los ROI reales de la cámara, en el mismo sistema de
// coordenadas que la foto/heatmap ya renderizados debajo (viewBox = frame_w x
// frame_h reales, preserveAspectRatio="none" para estirar IGUAL que esas
// imágenes) -- así el polígono cae exactamente sobre el área real que
// delimita, sin reescalar a mano. Sin frame conocido no se dibuja nada (mejor
// nada que un polígono desalineado).
function ZonaRoiOverlay({ zonas, frame }) {
  if (!frame || !zonas?.length) return null;
  return (
    <svg viewBox={`0 0 ${frame.w} ${frame.h}`} preserveAspectRatio="none"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
      {zonas.map((z) => {
        const tint = TINT_POR_TIPO[z.tipo] || TINT_POR_TIPO.otro;
        const pts = (z.poligono || []).map(([x, y]) => `${x},${y}`).join(" ");
        const cx = (z.poligono || []).reduce((s, p) => s + p[0], 0) / (z.poligono?.length || 1);
        const cy = (z.poligono || []).reduce((s, p) => s + p[1], 0) / (z.poligono?.length || 1);
        return (
          <g key={z.id}>
            <polygon points={pts} fill={`rgba(${tint},0.06)`} stroke={`rgba(${tint},0.75)`}
              strokeWidth={frame.w / 320} strokeDasharray={`${frame.w / 160} ${frame.w / 120}`} />
            <text x={cx} y={cy} textAnchor="middle" fontFamily="var(--font-metric)"
              fontSize={frame.w / 45} fontWeight="700" fill={`rgb(${tint})`}
              stroke="rgba(0,0,0,.6)" strokeWidth={frame.w / 900} paintOrder="stroke">
              {z.nombre?.toUpperCase()}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function fmtDT(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('es-AR', { day: 'numeric', month: 'short', year: 'numeric' })
       + ' ' + d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
}

function HeatmapPage() {
  const toast = useToast();
  const [camaraId, setCamaraId] = React.useState(CAMARAS[0].id);
  const { data: hm, loading }   = useHeatmapCamara(camaraId);
  const [fondoOk, setFondoOk]   = React.useState(true);
  const { zonas: zonasRoi, frame: frameRoi } = useCameraZonas(camaraId);
  const [mostrarRoi, setMostrarRoi] = React.useState(false);

  const [fecha, setFecha] = React.useState(null);
  React.useEffect(() => { setFecha(null); }, [camaraId]);
  // Heatmaps INDIVIDUALES (uno por sesion/video analizado) de esta camara+dia,
  // en orden cronologico -- a medida que se analizan mas videos, este fetch
  // los va trayendo solo (no hay estado que "sumar" a mano en el frontend).
  const { data: evolucion, loading: loadingEvolucion } = useCameraHeatmaps(camaraId, fecha);
  const fechasDisponibles = evolucion?.fechas_disponibles || [];
  React.useEffect(() => {
    if (evolucion?.fecha) setFecha(evolucion.fecha);
  }, [evolucion?.fecha]);

  React.useEffect(() => { setFondoOk(true); }, [camaraId]);

  const heatmapsEvolucion = evolucion?.heatmaps || [];
  const totalDeteccionesEvolucion = heatmapsEvolucion.reduce((a, h) => a + (h.total_detecciones || 0), 0);

  const downloadPng = () => {
    if (!hm?.imagen_url) { toast("Sin imagen disponible"); return; }
    const a = document.createElement('a');
    a.href = hm.imagen_url;
    a.download = `heatmap_camara_${camaraId}.png`;
    a.click();
  };

  return (
    <main className="content docs">
      <PageHeader
        title="Mapa de calor"
        subtitle={hm
          ? `${hm.camara_nombre || 'Cámara ' + camaraId} · ${hm.sesiones_combinadas || 0} análisis combinados`
          : "Recorridos acumulados de circulación por cámara"}
        right={
          <button className="btn-sec" onClick={downloadPng}>
            <IcoDownload style={{ marginRight: 6 }} />PNG
          </button>
        }
      />

      <div className="range-tabs" style={{ marginBottom: 14 }}>
        {CAMARAS.map(c => (
          <button key={c.id} className={camaraId === c.id ? 'on' : ''} onClick={() => setCamaraId(c.id)}>
            {c.nombre}
          </button>
        ))}
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--fg-3)', fontSize: 15 }}>
          Cargando mapa de calor…
        </div>
      )}

      {!loading && !hm && (
        <div style={{
          textAlign: 'center', padding: 80, color: 'var(--fg-3)',
          background: 'var(--bg-2)', borderRadius: 4, margin: '20px 0',
          border: '1px solid var(--line)'
        }}>
          <IcoHeat style={{ width: 36, height: 36, opacity: .3, marginBottom: 12 }} />
          <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 6 }}>Sin datos de mapa de calor para esta cámara</div>
          <div style={{ fontSize: 14 }}>Ejecutá <span className="mono" style={{ color: 'var(--brand-soft)' }}>deteccion/main.py</span> sobre un video de esta cámara para generar el primer análisis.</div>
        </div>
      )}

      {!loading && hm && (
        <div className="main-grid" style={{ marginTop: 14 }}>

          {/* Panel izquierdo: imagen combinada sobre foto fija + métricas */}
          <div className="panel">
            <div className="panel-head">
              <div className="panel-title">
                <span className="ico"><IcoHeat /></span>Densidad acumulada de circulación
              </div>
              <span className="mono" style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>
                {hm.sesiones_combinadas || 0} análisis · act. {fmtDT(hm.actualizado_en)}
              </span>
            </div>

            {/* Foto fija del local + heatmap combinado superpuesto via CSS.
                El fondo se atenua (menos saturacion/brillo) para que los
                colores del heatmap resalten en vez de perderse contra una
                foto con mucho detalle (gondolas, productos, etc). */}
            <div style={{ aspectRatio: fondoOk ? `${FONDO_CONTENT_W} / ${FONDO_CONTENT_H}` : undefined, borderRadius: 4, overflow: 'hidden', border: '1px solid var(--line)', position: 'relative', background: '#0e1729' }}>
              {frameRoi && zonasRoi.length > 0 && (
                <div className="plan-layers" style={{ top: 8, left: 8 }}>
                  <button className={!mostrarRoi ? 'on' : ''} onClick={() => setMostrarRoi(false)}>Solo calor</button>
                  <button className={mostrarRoi ? 'on' : ''} onClick={() => setMostrarRoi(true)}>+ Zonas (ROI)</button>
                </div>
              )}
              {fondoOk && (
                <img src={`/api/heatmap/fondo/${camaraId}`} alt="Vista de la cámara (fondo)"
                  onError={() => setFondoOk(false)}
                  style={fondoZoomStyle({ filter: 'saturate(.45) brightness(.7)' })} />
              )}
              {hm.imagen_url ? (
                <img src={hm.imagen_url} alt="Mapa de calor combinado"
                  style={fondoOk
                    ? { position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'fill',
                        filter: 'saturate(1.7) contrast(1.25) brightness(1.1)' }
                    : { width: '100%', height: 'auto', display: 'block' }} />
              ) : !fondoOk && (
                <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center',
                              color: 'var(--fg-3)', background: 'var(--bg-3)', fontSize: 14 }}>
                  Sin imagen guardada
                </div>
              )}
              {mostrarRoi && fondoOk && <ZonaRoiOverlay zonas={zonasRoi} frame={frameRoi} />}
              {hm.punto_max_x != null && (
                <div style={{
                  position: 'absolute', bottom: 8, right: 8,
                  background: 'rgba(0,0,0,0.65)', borderRadius: 4, padding: '3px 8px',
                  fontSize: 11.5, color: 'var(--fg-2)', fontFamily: 'var(--font-metric)'
                }}>
                  pico ({hm.punto_max_x}, {hm.punto_max_y})
                </div>
              )}
            </div>

            <div className="heat-legend" style={{ marginTop: 10 }}>
              <span>Baja</span><div className="heat-bar" /><span>Alta</span>
            </div>

            {/* Métricas */}
            <div style={{ marginTop: 14, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              {[
                { label: 'Área activa',    value: hm.area_activa_pct != null ? `${hm.area_activa_pct.toFixed(1)}%`   : '—' },
                { label: 'Concentración',  value: hm.concentracion   != null ? `${(hm.concentracion * 100).toFixed(0)}%` : '—' },
                { label: 'Detecciones',    value: hm.total_detecciones != null ? hm.total_detecciones.toLocaleString() : '—' },
              ].map(m => (
                <div key={m.label} style={{
                  padding: '10px 12px', background: 'var(--bg-3)', borderRadius: 4,
                  border: '1px solid var(--line)', textAlign: 'center'
                }}>
                  <div style={{ fontSize: 11.5, color: 'var(--fg-3)', textTransform: 'uppercase',
                                letterSpacing: '.08em', marginBottom: 4 }}>{m.label}</div>
                  <div className="mono" style={{ fontSize: 20.5, fontWeight: 600, color: 'var(--fg-0)' }}>{m.value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Panel derecho: info del acumulado */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

            <div className="panel">
              <div className="panel-head">
                <div className="panel-title"><span className="ico"><IcoClock /></span>Información del acumulado</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 14 }}>
                {[
                  ['Cámara',               hm.camara_nombre || `Cam ${camaraId}`],
                  ['Análisis combinados',  hm.sesiones_combinadas ?? '—'],
                  ['Última actualización', fmtDT(hm.actualizado_en)],
                  ['Frames procesados',    hm.frames_procesados != null ? hm.frames_procesados.toLocaleString() : '—'],
                  ['Total detecciones',    hm.total_detecciones != null ? hm.total_detecciones.toLocaleString() : '—'],
                  ['Zona más caliente',    hm.zona_mas_caliente || '—'],
                ].map(([label, value]) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <span style={{ color: 'var(--fg-3)' }}>{label}</span>
                    <span className="mono" style={{ color: 'var(--fg-0)', textAlign: 'right' }}>{value}</span>
                  </div>
                ))}
              </div>
            </div>

            {!fondoOk && (
              <div className="panel" style={{ fontSize: 14, color: 'var(--fg-3)' }}>
                Sin foto de fondo para esta cámara. Subí una imagen fija del local vacío a
                <span className="mono" style={{ color: 'var(--brand-soft)' }}> frontend/fondos/camara_{camaraId}.jpg</span> para
                verla debajo del mapa de calor.
              </div>
            )}
          </div>

        </div>
      )}

      {/* Evolucion cronologica: reproductor de los heatmaps INDIVIDUALES ya
          guardados en Supabase para esta camara+dia (uno por sesion/video
          analizado, ver guardar_heatmap() en deteccion/persistencia.py),
          ordenados por periodo_inicio. Panel de info a la derecha, mismo
          criterio que "Informacion del acumulado" de arriba. */}
      <div className="main-grid" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="panel-head">
            <div>
              <div className="panel-title"><span className="ico"><IcoHeat /></span>Evolución del mapa de calor</div>
              <div style={{ fontSize: 13, color: 'var(--fg-3)', marginTop: 4 }}>
                Reproducción cronológica de cada análisis individual del día · datos reales
              </div>
            </div>
            <div className="filter-grp">
              <span className="filter-lbl">Día</span>
              <select className="select-input" value={fecha || ''}
                onChange={(e) => setFecha(e.target.value)}
                disabled={fechasDisponibles.length === 0}>
                {fechasDisponibles.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
          </div>

          {loadingEvolucion && (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--fg-3)', fontSize: 15 }}>
              Cargando evolución del mapa de calor…
            </div>
          )}

          {!loadingEvolucion && !heatmapsEvolucion.length && (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--fg-3)', fontSize: 14 }}>
              Sin análisis individuales guardados para esta cámara todavía.
            </div>
          )}

          {!loadingEvolucion && heatmapsEvolucion.length > 0 && (
            <HeatmapPlayer heatmaps={heatmapsEvolucion} camaraId={camaraId} zonas={zonasRoi} frame={frameRoi} />
          )}
        </div>

        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><span className="ico"><IcoClock /></span>Información de la evolución</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 14 }}>
            {[
              ['Cámara',              evolucion?.camara_nombre || `Cámara ${camaraId}`],
              ['Día',                 fecha || '—'],
              ['Análisis ese día',    loadingEvolucion ? '—' : heatmapsEvolucion.length],
              ['Total detecciones',   loadingEvolucion ? '—' : totalDeteccionesEvolucion.toLocaleString()],
            ].map(([label, value]) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ color: 'var(--fg-3)' }}>{label}</span>
                <span className="mono" style={{ color: 'var(--fg-0)', textAlign: 'right' }}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}

// Cuanto tarda en verse el dia COMPLETO reproducido a "camara rapida", en
// segundos reales de reloj, a velocidad 1x -- mismo criterio que
// RECORRIDO_DURACION_SEG del mapa de trayectorias.
const HEATMAP_RECORRIDO_DURACION_SEG = 40;
// Cada cuanto se avanza el reloj simulado mientras se reproduce.
const HEATMAP_RECORRIDO_TICK_MS = 150;
const HEATMAP_VELOCIDADES = [0.5, 1, 2, 4];

// Reproductor cronologico de los heatmaps individuales de un dia: mismo
// reloj simulado (arrancar/pausar, saltar, barra arrastrable) que
// TrajectoryMap, pero en vez de ir revelando puntos, en cada instante
// muestra la imagen del heatmap mas reciente cuyo periodo_inicio ya paso
// (funcion escalon) -- asi "sostiene" el ultimo analisis mientras no haya
// uno nuevo, en vez de interpolar entre imagenes que no tienen relacion
// pixel a pixel entre si.
function HeatmapPlayer({ heatmaps, camaraId, zonas = [], frame = null }) {
  const [fondoOk, setFondoOk]   = React.useState(true);
  const [playing, setPlaying]   = React.useState(true);
  const [velocidad, setVelocidad] = React.useState(1);
  const [simTime, setSimTime]   = React.useState(null);
  const [mostrarRoi, setMostrarRoi] = React.useState(false);

  React.useEffect(() => { setFondoOk(true); }, [camaraId]);

  const limites = React.useMemo(() => {
    if (!heatmaps?.length) return null;
    const inicio = new Date(heatmaps[0].periodo_inicio).getTime();
    const fin = Math.max(...heatmaps.map(h => new Date(h.periodo_fin || h.periodo_inicio).getTime()));
    return { inicio, fin: Math.max(fin, inicio + 1) };
  }, [heatmaps]);

  // Reinicia el reloj simulado al principio cada vez que cambia el conjunto
  // de heatmaps (dia o camara distinta -- 'limites' cambia de identidad).
  React.useEffect(() => {
    setSimTime(limites ? limites.inicio : null);
    setPlaying(true);
  }, [limites]);

  React.useEffect(() => {
    if (!playing || !limites) return;
    const rango  = (limites.fin - limites.inicio) || 1;
    const factor = rango / (HEATMAP_RECORRIDO_DURACION_SEG * 1000 / velocidad);
    const id = setInterval(() => {
      setSimTime(t => {
        const next = (t ?? limites.inicio) + HEATMAP_RECORRIDO_TICK_MS * factor;
        return next >= limites.fin ? limites.inicio : next; // loop continuo
      });
    }, HEATMAP_RECORRIDO_TICK_MS);
    return () => clearInterval(id);
  }, [playing, limites, velocidad]);

  // Heatmap activo = el ultimo cuyo periodo_inicio ya paso el reloj simulado.
  const indiceActivo = React.useMemo(() => {
    if (simTime == null || !heatmaps?.length) return 0;
    let idx = 0;
    for (let i = 0; i < heatmaps.length; i++) {
      if (new Date(heatmaps[i].periodo_inicio).getTime() <= simTime) idx = i; else break;
    }
    return idx;
  }, [heatmaps, simTime]);
  const activo = heatmaps[indiceActivo];

  const fmtReloj = (ms) => {
    if (ms == null) return '--/--/---- --:--:--';
    const d = new Date(ms);
    const fecha = d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const hora  = d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    return `${fecha}  ${hora}`;
  };

  const progreso = limites ? Math.min(1, Math.max(0, (simTime - limites.inicio) / ((limites.fin - limites.inicio) || 1))) : 0;

  const barRef = React.useRef(null);
  const [arrastrando, setArrastrando] = React.useState(false);

  const seekDesdeClientX = React.useCallback((clientX) => {
    if (!barRef.current || !limites) return;
    const rect = barRef.current.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    setSimTime(limites.inicio + frac * (limites.fin - limites.inicio));
  }, [limites]);

  React.useEffect(() => {
    if (!arrastrando) return;
    const mover  = (e) => seekDesdeClientX(e.clientX);
    const soltar = () => setArrastrando(false);
    window.addEventListener('pointermove', mover);
    window.addEventListener('pointerup', soltar);
    return () => {
      window.removeEventListener('pointermove', mover);
      window.removeEventListener('pointerup', soltar);
    };
  }, [arrastrando, seekDesdeClientX]);

  // Salta al analisis anterior/siguiente de la lista (paso discreto -- tiene
  // mas sentido para imagenes que un salto por fraccion de tiempo, que podia
  // no cruzar ningun cambio de heatmap si los analisis estan muy espaciados).
  const saltar = (signo) => {
    if (!heatmaps?.length) return;
    const nuevo = Math.min(heatmaps.length - 1, Math.max(0, indiceActivo + signo));
    setSimTime(new Date(heatmaps[nuevo].periodo_inicio).getTime());
  };

  return (
    <div style={{ aspectRatio: `${FONDO_CONTENT_W} / ${FONDO_CONTENT_H}`, borderRadius: 4, overflow: 'hidden', border: '1px solid var(--line)', position: 'relative', background: '#0e1729' }}>
      {fondoOk && (
        <img src={`/api/heatmap/fondo/${camaraId}`} alt="Vista de la cámara (fondo)"
          onError={() => setFondoOk(false)}
          style={fondoZoomStyle({ filter: 'saturate(.45) brightness(.7)' })} />
      )}
      {activo?.imagen_url ? (
        <img src={activo.imagen_url} alt="Mapa de calor de este análisis"
          style={fondoOk
            ? { position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'fill',
                filter: 'saturate(1.7) contrast(1.25) brightness(1.1)' }
            : { width: '100%', height: 'auto', display: 'block' }} />
      ) : (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: 'var(--fg-3)', fontSize: 14 }}>
          Sin imagen guardada para este análisis
        </div>
      )}
      {mostrarRoi && fondoOk && <ZonaRoiOverlay zonas={zonas} frame={frame} />}

      <div className="mono" style={{
        position: 'absolute', top: 8, left: 8, padding: '3px 8px', borderRadius: 4,
        background: 'rgba(0,0,0,.55)', color: '#e2e8f0', fontSize: 13, letterSpacing: .3,
      }}>
        {fmtReloj(simTime)}
      </div>
      {frame && zonas.length > 0 && (
        <div className="plan-layers" style={{ top: 38, left: 8 }}>
          <button className={!mostrarRoi ? 'on' : ''} onClick={() => setMostrarRoi(false)}>Solo calor</button>
          <button className={mostrarRoi ? 'on' : ''} onClick={() => setMostrarRoi(true)}>+ ROI</button>
        </div>
      )}
      <div className="mono" style={{
        position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)',
        padding: '3px 8px', borderRadius: 4, background: 'rgba(0,0,0,.55)', color: 'var(--fg-2)', fontSize: 12.5,
      }}>
        Análisis {indiceActivo + 1} / {heatmaps.length}
        {activo?.total_detecciones != null && ` · ${activo.total_detecciones.toLocaleString()} detecciones`}
      </div>

      <div style={{ position: 'absolute', top: 8, right: 8, display: 'flex', gap: 4 }}>
        {HEATMAP_VELOCIDADES.map(v => (
          <button key={v} onClick={() => setVelocidad(v)} aria-label={`Velocidad ${v}x`} style={{
            minWidth: 26, height: 22, padding: '0 5px', borderRadius: 4,
            background: velocidad === v ? 'var(--brand-soft)' : 'rgba(0,0,0,.55)',
            border: 'none', color: velocidad === v ? '#0b1524' : '#e2e8f0',
            fontSize: 12, fontFamily: 'var(--font-metric)', fontWeight: 600, cursor: 'pointer',
          }}>
            {v}x
          </button>
        ))}
      </div>

      <div style={{ position: 'absolute', top: 38, right: 8, display: 'flex', gap: 4 }}>
        {[
          { onClick: () => saltar(-1), label: 'Análisis anterior', Icono: IcoRewind },
          { onClick: () => setPlaying(p => !p), label: playing ? 'Pausar' : 'Reanudar', Icono: playing ? IcoPause : IcoPlay },
          { onClick: () => saltar(1), label: 'Análisis siguiente', Icono: IcoForward },
        ].map(({ onClick, label, Icono }, idx) => (
          <button key={idx} onClick={onClick} aria-label={label} style={{
            width: 26, height: 26, borderRadius: 4,
            background: 'rgba(0,0,0,.55)', border: 'none', color: '#e2e8f0',
            display: 'grid', placeItems: 'center', cursor: 'pointer',
          }}>
            <Icono style={{ width: 12, height: 12 }} />
          </button>
        ))}
      </div>

      <div
        ref={barRef}
        onPointerDown={(e) => { setArrastrando(true); seekDesdeClientX(e.clientX); }}
        style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 7, background: 'rgba(255,255,255,.1)', cursor: 'pointer' }}
      >
        <div style={{ width: `${progreso * 100}%`, height: '100%', background: 'var(--brand-soft)', transition: arrastrando ? 'none' : 'width 140ms linear' }} />
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// TRACKING PAGE — trayectorias reales de un video ya analizado
// ═════════════════════════════════════════════════════════════
function useSessionsList() {
  const [sessions, setSessions] = React.useState([]);
  const [loading, setLoading]   = React.useState(true);
  React.useEffect(() => {
    fetch('/api/sessions')
      .then(r => r.json())
      .then(d => { setSessions(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { sessions, loading };
}

// Junta TODOS los videos analizados de una camara que caigan en un mismo
// dia calendario (ver /api/cameras/<id>/tracking) -- asi el mapa de
// trayectorias se puede reproducir por CAMARA, en orden cronologico real,
// en vez de video por video. 'fecha' en null pide el dia mas reciente con
// datos; el backend devuelve la fecha realmente usada en 'sesion.fecha'.
function useCameraTracking(camaraId, fecha) {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  React.useEffect(() => {
    if (!camaraId) { setData(null); return; }
    setLoading(true);
    const qs = fecha ? `?fecha=${fecha}` : '';
    fetch(`/api/cameras/${camaraId}/tracking${qs}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [camaraId, fecha]);
  return { data, loading };
}

function fmtDur(seg) {
  if (seg == null) return '—';
  const s = Math.max(0, Math.round(seg));
  return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
}

const METODO_REID_LABEL = {
  nuevo: 'Nuevo', posicion: 'Posición', apariencia: 'Apariencia', gemini: 'Gemini', groq: 'Groq',
};

function TrackingPage() {
  const { sessions, loading: loadingSessions } = useSessionsList();
  const camaras = React.useMemo(
    () => [...new Set(sessions.map(s => s.camara_id))].sort((a, b) => a - b),
    [sessions]
  );
  const [camaraId, setCamaraId] = React.useState(null);
  const [fecha, setFecha]       = React.useState(null);

  // Selecciona automaticamente la primera camara apenas se conoce la lista.
  React.useEffect(() => {
    if (!camaraId && camaras.length > 0) setCamaraId(camaras[0]);
  }, [camaras, camaraId]);

  const { data, loading: loadingTracking } = useCameraTracking(camaraId, fecha);
  const fechasDisponibles = data?.fechas_disponibles || [];

  // Sincroniza el selector de dia con la fecha que realmente devolvio el
  // backend (la mas reciente, mientras no se elija una explicitamente) --
  // sin esto el <select> de dia queda vacio o desincronizado la primera vez
  // que se carga cada camara.
  React.useEffect(() => {
    if (data?.sesion?.fecha) setFecha(data.sesion.fecha);
  }, [data?.sesion?.fecha]);

  const personas      = data?.personas || [];
  const personasUnicas = new Set(personas.map(p => p.cliente_id)).size;
  // Dedupear por cliente_id, igual que personasUnicas -- un mismo empleado
  // genera muchas filas de 'personas' a lo largo del dia (una por cada vez
  // que el tracking lo pierde y lo vuelve a confirmar), asi que contar filas
  // en vez de identidades distintas inflaba este numero muy por encima de
  // los empleados reales que hay.
  const empleados = new Set(personas.filter(p => p.es_empleado).map(p => p.cliente_id)).size;
  const duraciones     = personas.map(p => p.duracion_seg).filter(d => d != null);
  const duracionProm   = duraciones.length ? duraciones.reduce((a, b) => a + b, 0) / duraciones.length : null;

  // Zona mas frecuente en la trayectoria de cada persona (para la lista).
  const zonaPorPersona = React.useMemo(() => {
    const map = {};
    for (const t of data?.trayectorias || []) {
      if (!t.zona_nombre) continue;
      const cuentas = map[t.persona_id] || (map[t.persona_id] = {});
      cuentas[t.zona_nombre] = (cuentas[t.zona_nombre] || 0) + 1;
    }
    const top = {};
    for (const pid in map) {
      top[pid] = Object.entries(map[pid]).sort((a, b) => b[1] - a[1])[0][0];
    }
    return top;
  }, [data]);

  return (
    <main className="content docs">
      <PageHeader
        title="Tracking de personas"
        subtitle="Trayectorias y conteo reales por cámara, combinando todos los videos analizados de un mismo día en orden cronológico."
      />
      <WipBanner>
        El tracking EN VIVO todavía no está disponible (pipeline RTSP funcional, visualización prevista para ago. 2026) — lo de abajo es el recorrido real de lo ya analizado, elegí la cámara y el día en el selector.
      </WipBanner>

      <div className="filter-bar">
        <div className="filter-grp">
          <span className="filter-lbl">Cámara</span>
          <select className="select-input" value={camaraId || ''}
            onChange={(e) => { setCamaraId(Number(e.target.value)); setFecha(null); }}
            disabled={loadingSessions || camaras.length === 0}>
            {camaras.length === 0 && <option value="">Sin cámaras analizadas</option>}
            {camaras.map(c => <option key={c} value={c}>Cámara {c}</option>)}
          </select>
        </div>
        <div className="filter-grp">
          <span className="filter-lbl">Día</span>
          <select className="select-input" value={fecha || ''}
            onChange={(e) => setFecha(e.target.value)}
            disabled={fechasDisponibles.length === 0}>
            {fechasDisponibles.map(f => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
      </div>

      {loadingTracking && (
        <div style={{ textAlign: 'center', padding: 80, color: 'var(--fg-3)', fontSize: 15 }}>
          Cargando tracking de la cámara…
        </div>
      )}

      {!loadingTracking && data && (
        <React.Fragment>
          <div className="kpi-grid">
            <KpiCard label="Personas detectadas" value={personas.length} unit="ese día" delta={`${(data.trayectorias || []).length} puntos de trayectoria`} trend="neutral" Ico={IcoUsers} color="var(--brand-soft)" />
            <KpiCard label="Personas únicas" value={personasUnicas} unit="clientes reales" delta="reidentificadas vía Re-ID" trend="neutral" Ico={IcoUser} iconClass="pos" color="var(--pos-soft)" />
            <KpiCard label="Empleados detectados" value={empleados} unit="por uniforme" delta="heurística automática" trend="neutral" Ico={IcoChip} color="var(--brand-soft)" />
            <KpiCard label="Duración promedio" value={fmtDur(duracionProm)} unit="por persona" delta={`máx. ${fmtDur(Math.max(0, ...duraciones))}`} trend="neutral" Ico={IcoClock} color="#e6a83b" />
          </div>

          <div className="main-grid" style={{ marginTop: 14 }}>
            <div className="panel">
              <div className="panel-head">
                <div className="panel-title"><span className="ico"><IcoTrack /></span>Mapa de trayectorias</div>
                <span className="cam-status">
                  <IcoCam style={{ width: 14, height: 14 }} />
                  <b>{data.sesion.nombre}</b>
                  <span className="mono" style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{data.sesion.n_videos} video{data.sesion.n_videos === 1 ? '' : 's'}</span>
                  <span className="live" style={{ background: 'var(--bg-3)', color: 'var(--fg-3)' }}>ANALIZADO</span>
                </span>
              </div>
              <TrajectoryMap trayectorias={data.trayectorias} personas={data.personas} zonas={data.zonas} bounds={data.bounds} camaraId={data.sesion.camara_id} frameW={data.sesion.frame_w} frameH={data.sesion.frame_h} />
            </div>
            <div className="panel">
              <div className="panel-head">
                <div className="panel-title"><span className="ico"><IcoUsers /></span>Personas detectadas</div>
                <span className="mono" style={{ fontSize: 12.5, color: "var(--fg-3)" }}>{personas.length} en total</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 480, overflowY: "auto" }}>
                {personas.length === 0 && (
                  <div style={{ padding: 20, textAlign: 'center', color: 'var(--fg-3)', fontSize: 14 }}>
                    Nadie detectado ese día.
                  </div>
                )}
                {personas.map(p => (
                  <div key={p.id} style={{
                    display: "grid", gridTemplateColumns: "auto 1fr auto auto", gap: 10, alignItems: "center",
                    padding: "9px 10px", background: "var(--bg-3)", border: "1px solid var(--line)", borderRadius: 4
                  }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: p.es_empleado ? "var(--warn)" : "var(--pos-soft)" }} />
                    <div>
                      <div className="mono" style={{ fontSize: 13, color: "var(--fg-0)", fontWeight: 500 }}>
                        #{p.id}{p.cliente_id !== p.id && <span style={{ color: 'var(--fg-3)' }}> (cliente #{p.cliente_id})</span>}
                        {p.es_empleado && <span style={{ marginLeft: 6, fontSize: 10.5, color: 'var(--warn)', border: '1px solid var(--warn)', borderRadius: 4, padding: '1px 4px' }}>EMPLEADO</span>}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--fg-3)" }}>{zonaPorPersona[p.id] || '—'}</div>
                    </div>
                    <div className="mono" style={{ fontSize: 12.5, color: "var(--fg-1)" }}>{fmtDur(p.duracion_seg)}</div>
                    <div className="mono" style={{ fontSize: 12, color: "var(--fg-2)", textAlign: "right" }}>{METODO_REID_LABEL[p.metodo_reid] || p.metodo_reid || '—'}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </React.Fragment>
      )}

      {!loadingTracking && !data && !loadingSessions && sessions.length === 0 && (
        <div style={{
          textAlign: 'center', padding: 80, color: 'var(--fg-3)',
          background: 'var(--bg-2)', borderRadius: 4, margin: '20px 0',
          border: '1px solid var(--line)'
        }}>
          <IcoTrack style={{ width: 36, height: 36, opacity: .3, marginBottom: 12 }} />
          <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 6 }}>Todavía no hay videos analizados</div>
          <div style={{ fontSize: 14 }}>Ejecutá <span className="mono" style={{ color: 'var(--brand-soft)' }}>deteccion/main.py</span> sobre un video para generar el primer tracking.</div>
        </div>
      )}
    </main>
  );
}

// Cuanto tarda en verse la sesion COMPLETA reproducida a "camara rapida",
// en segundos reales de reloj -- independiente de cuanto haya durado el
// video real (una sesion de 5 min o de 1h30 se ven igual de "rapido").
const RECORRIDO_DURACION_SEG = 50;
// Cada cuanto se avanza el reloj simulado mientras se reproduce.
const RECORRIDO_TICK_MS = 100;
// Cuanto salta cada click de retroceder/adelantar, como fraccion del
// recorrido total (5% -- ni un salto imperceptible ni uno que se pase de largo).
const SALTO_FRACCION = 0.05;

// Empleados = circulo blanco (mas grande, para distinguirlos de un vistazo).
// Clientes = cuadrado, en rosa/verde/violeta/amarillo/rojo -- cada cliente
// nuevo (en orden de aparicion) toma el siguiente color de la lista, y
// vuelve a empezar si hay mas clientes que colores.
const COLORES_EMPLEADO = ['#ffffff'];
const COLORES_CLIENTE  = ['#e0559b', '#33a854', '#8b5fd6', '#e0c72b', '#e0473f']; // rosa, verde, violeta, amarillo, rojo
const RADIO_EMPLEADO_FACTOR = 1.7; // circulo de empleado vs. cuadrado de cliente

function TrajectoryMap({ trayectorias, personas, zonas, bounds, camaraId, frameW, frameH }) {
  const [fondoOk, setFondoOk] = React.useState(true);
  const [playing, setPlaying] = React.useState(true);
  const [simTime, setSimTime] = React.useState(null); // reloj simulado (ms epoch)

  // La foto de fondo es por camara -- al cambiar de video analizado puede
  // cambiar la camara, asi que hay que reintentar cargarla.
  React.useEffect(() => { setFondoOk(true); }, [camaraId]);

  // Solo se muestra la foto de fondo cuando se conoce la resolucion REAL del
  // video analizado (sesion.frame_w/h, guardada por deteccion/main.py al
  // abrir el video -- ver actualizar_resolucion_sesion). Las coordenadas de
  // 'trayectorias' estan en esos pixeles, que NO tienen por que coincidir
  // con la resolucion de la foto en frontend/fondos/ (ej. fotos guardadas a
  // 1280x589 pero videos grabados a 1920x1080) -- usar la resolucion de la
  // foto a ciegas desalineaba las trayectorias. Sin frame_w/h conocido, se
  // cae al recuadro fijo 320x200 normalizado por el bounding box de los
  // puntos detectados, como antes.
  const usaFondo = fondoOk && frameW && frameH;
  const W = usaFondo ? frameW : 320;
  const H = usaFondo ? frameH : 200;
  const PAD = usaFondo ? 0 : 20;

  const norm = React.useCallback((cx, cy) => {
    if (usaFondo) return [cx, cy];
    if (!bounds) return [W / 2, H / 2];
    const spanX = (bounds.max_x - bounds.min_x) || 1;
    const spanY = (bounds.max_y - bounds.min_y) || 1;
    return [
      PAD + ((cx - bounds.min_x) / spanX) * (W - PAD * 2),
      PAD + ((cy - bounds.min_y) / spanY) * (H - PAD * 2),
    ];
  }, [usaFondo, bounds, W, H, PAD]);

  // Agrupa por persona, con cada punto ya con su timestamp en ms y su
  // posicion normalizada -- ordenados por horario de aparicion (tanto los
  // puntos dentro de cada persona, como las personas entre si), asi el
  // recorrido las va "descubriendo" en el mismo orden en que entraron.
  const porPersona = React.useMemo(() => {
    const map = {};
    for (const t of trayectorias || []) {
      const ts = t.timestamp ? new Date(t.timestamp).getTime() : null;
      if (ts == null || !Number.isFinite(ts)) continue;
      (map[t.persona_id] || (map[t.persona_id] = [])).push({ ts, xy: norm(t.cx, t.cy) });
    }
    return Object.entries(map)
      .map(([personaId, puntos]) => ({ personaId: Number(personaId), puntos: puntos.sort((a, b) => a.ts - b.ts) }))
      .sort((a, b) => a.puntos[0].ts - b.puntos[0].ts);
  }, [trayectorias, norm]);

  const limites = React.useMemo(() => {
    if (!porPersona.length) return null;
    let inicio = Infinity, fin = -Infinity;
    for (const { puntos } of porPersona) {
      inicio = Math.min(inicio, puntos[0].ts);
      fin    = Math.max(fin, puntos[puntos.length - 1].ts);
    }
    return { inicio, fin };
  }, [porPersona]);

  // Color y forma fijos por persona (no cambian mientras dura el
  // recorrido): empleado -> circulo en COLORES_EMPLEADO, cliente -> cuadrado
  // en COLORES_CLIENTE, ciclando cada lista por separado en el orden de
  // aparicion de cada categoria.
  const estiloPorPersona = React.useMemo(() => {
    const esEmpleado = {};
    for (const p of personas || []) esEmpleado[p.id] = !!p.es_empleado;
    const estilo = {};
    let iEmp = 0, iCli = 0;
    for (const { personaId } of porPersona) {
      if (esEmpleado[personaId]) {
        estilo[personaId] = { color: COLORES_EMPLEADO[iEmp % COLORES_EMPLEADO.length], forma: 'circulo' };
        iEmp++;
      } else {
        estilo[personaId] = { color: COLORES_CLIENTE[iCli % COLORES_CLIENTE.length], forma: 'cuadrado' };
        iCli++;
      }
    }
    return estilo;
  }, [porPersona, personas]);

  // Reinicia el reloj simulado al principio cada vez que cambia el video
  // (sesion distinta -> 'limites' cambia de identidad).
  React.useEffect(() => {
    setSimTime(limites ? limites.inicio : null);
    setPlaying(true);
  }, [limites]);

  React.useEffect(() => {
    if (!playing || !limites) return;
    const rango  = (limites.fin - limites.inicio) || 1;
    const factor = rango / (RECORRIDO_DURACION_SEG * 1000);
    const id = setInterval(() => {
      setSimTime(t => {
        const next = (t ?? limites.inicio) + RECORRIDO_TICK_MS * factor;
        return next >= limites.fin ? limites.inicio : next; // loop continuo
      });
    }, RECORRIDO_TICK_MS);
    return () => clearInterval(id);
  }, [playing, limites]);

  // Solo las personas PRESENTES ahora mismo segun el reloj simulado --
  // entre su primera y su ultima deteccion real -- y solo con los puntos
  // vistos hasta el momento (el trazo se va "dibujando" mientras esta, en
  // vez de mostrarse completo de entrada). En cuanto el reloj pasa su
  // ultima deteccion (la persona salio de cuadro), deja de devolverse y el
  // punto/trazo desaparece del mapa -- sin esto, las trayectorias de todo
  // el dia quedaban dibujadas para siempre y se superponian todas juntas.
  const activos = React.useMemo(() => {
    if (simTime == null) return [];
    return porPersona
      .map(({ personaId, puntos }) => {
        const inicio = puntos[0].ts;
        const fin    = puntos[puntos.length - 1].ts;
        if (simTime < inicio || simTime > fin) return null;
        const estilo = estiloPorPersona[personaId] || { color: '#8899aa', forma: 'circulo' };
        return { ...estilo, puntos: puntos.filter(p => p.ts <= simTime) };
      })
      .filter(Boolean);
  }, [porPersona, simTime, estiloPorPersona]);

  const fmtReloj = (ms) => {
    if (ms == null) return '--/--/---- --:--:--';
    const d = new Date(ms);
    const fecha = d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const hora  = d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    return `${fecha}  ${hora}`;
  };

  const progreso = limites ? Math.min(1, Math.max(0, (simTime - limites.inicio) / ((limites.fin - limites.inicio) || 1))) : 0;

  // Barra de progreso arrastrable/clickeable para retroceder o adelantar el
  // recorrido a cualquier punto, ademas de los botones de salto fijo.
  const barRef = React.useRef(null);
  const [arrastrando, setArrastrando] = React.useState(false);

  const seekDesdeClientX = React.useCallback((clientX) => {
    if (!barRef.current || !limites) return;
    const rect = barRef.current.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    setSimTime(limites.inicio + frac * (limites.fin - limites.inicio));
  }, [limites]);

  React.useEffect(() => {
    if (!arrastrando) return;
    const mover  = (e) => seekDesdeClientX(e.clientX);
    const soltar = () => setArrastrando(false);
    window.addEventListener('pointermove', mover);
    window.addEventListener('pointerup', soltar);
    return () => {
      window.removeEventListener('pointermove', mover);
      window.removeEventListener('pointerup', soltar);
    };
  }, [arrastrando, seekDesdeClientX]);

  const saltar = (signo) => {
    if (!limites) return;
    const delta = (limites.fin - limites.inicio) * SALTO_FRACCION * signo;
    setSimTime(t => Math.min(limites.fin, Math.max(limites.inicio, (t ?? limites.inicio) + delta)));
  };

  return (
    // El cuadro sigue la proporcion REAL del video (frameW/frameH) en vez de
    // una altura fija -- con altura fija la foto de fondo y las trayectorias
    // se estiraban o comprimian segun cuanto se alejara esa proporcion de la
    // del video, dando sensacion de zoom incorrecto.
    <div style={{ aspectRatio: `${W} / ${H}`, maxHeight: 420, borderRadius: 4, overflow: "hidden", border: "1px solid var(--line)", position: "relative", background: "#0e1729" }}>
      {usaFondo && (
        <React.Fragment>
          <img
            src={`/api/heatmap/fondo/${camaraId}`}
            alt="Vista de la cámara (fondo)"
            onError={() => setFondoOk(false)}
            style={fondoZoomStyle({ filter: "saturate(.5) brightness(.65)" })}
          />
          {/* Velo azul semitransparente sobre el fondo -- sin esto los
              cuadrados/circulos de colores se perdian contra la foto de la
              camara; el azul, al no usarse en ningun color de cliente ni de
              empleado, no compite con la paleta de las trayectorias. */}
          <div style={{ position: "absolute", inset: 0, background: "rgba(23, 60, 130, .38)", pointerEvents: "none" }} />
        </React.Fragment>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%"
        preserveAspectRatio="none"
        style={usaFondo ? { position: "absolute", inset: 0 } : {}}>
        {!usaFondo && (
          <React.Fragment>
            <defs>
              <pattern id="tgrid" width="20" height="20" patternUnits="userSpaceOnUse">
                <path d="M20 0H0V20" stroke="rgba(255,255,255,0.025)" fill="none" />
              </pattern>
            </defs>
            <rect width={W} height={H} fill="url(#tgrid)" />
          </React.Fragment>
        )}
        {/* Zonas reales de la camara (si estan definidas) */}
        {(zonas || []).length > 0 && (
          <g stroke="rgba(140,165,210,0.28)" strokeWidth="1" fill="rgba(140,165,210,0.06)">
            {zonas.map(z => (
              <polygon key={z.id} points={(z.poligono || []).map(([x, y]) => norm(x, y).join(',')).join(' ')} />
            ))}
          </g>
        )}
        {/* Trayectorias, reveladas en orden de aparicion segun el reloj simulado.
            Empleados = circulo blanco (mas grande); clientes = cuadrado
            (rosa/verde/violeta/amarillo/rojo) -- ver estiloPorPersona. */}
        {activos.map((g, i) => {
          const d = g.puntos.reduce((acc, p, j) => acc + (j === 0 ? `M ${p.xy[0]} ${p.xy[1]}` : ` L ${p.xy[0]} ${p.xy[1]}`), '');
          const [cx, cy] = g.puntos[g.puntos.length - 1].xy;
          const rBase = usaFondo ? W / 320 * 3 : 3;
          const r = g.forma === 'circulo' ? rBase * RADIO_EMPLEADO_FACTOR : rBase;
          return (
            <g key={i}>
              <path d={d} stroke={g.color} strokeWidth={usaFondo ? W / 320 * 1.5 : 1.5} fill="none" opacity=".7"
                strokeDasharray={usaFondo ? `${W / 320 * 2} ${W / 320 * 3}` : "2 3"} />
              {g.forma === 'circulo'
                ? <circle cx={cx} cy={cy} r={r} fill={g.color} />
                : <rect x={cx - r} y={cy - r} width={r * 2} height={r * 2} fill={g.color} />}
            </g>
          );
        })}
        {!trayectorias?.length && (
          <text x={W / 2} y={H / 2} textAnchor="middle" fill="var(--fg-3)" fontSize={usaFondo ? W / 320 * 9 : 9}>
            Sin puntos de trayectoria guardados para este video
          </text>
        )}
      </svg>
      {limites && (
        <React.Fragment>
          <div className="mono" style={{
            position: "absolute", top: 8, left: 8, padding: "3px 8px", borderRadius: 4,
            background: "rgba(0,0,0,.55)", color: "#e2e8f0", fontSize: 13, letterSpacing: .3,
          }}>
            {fmtReloj(simTime)}
          </div>
          <div style={{ position: "absolute", top: 8, right: 8, display: "flex", gap: 4 }}>
            {[
              { onClick: () => saltar(-1), label: "Retroceder", Icono: IcoRewind },
              { onClick: () => setPlaying(p => !p), label: playing ? "Pausar recorrido" : "Reanudar recorrido", Icono: playing ? IcoPause : IcoPlay },
              { onClick: () => saltar(1), label: "Adelantar", Icono: IcoForward },
            ].map(({ onClick, label, Icono }, idx) => (
              <button key={idx} onClick={onClick} aria-label={label} style={{
                width: 26, height: 26, borderRadius: 4,
                background: "rgba(0,0,0,.55)", border: "none", color: "#e2e8f0",
                display: "grid", placeItems: "center", cursor: "pointer",
              }}>
                <Icono style={{ width: 12, height: 12 }} />
              </button>
            ))}
          </div>
          <div
            ref={barRef}
            onPointerDown={(e) => { setArrastrando(true); seekDesdeClientX(e.clientX); }}
            style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 7, background: "rgba(255,255,255,.1)", cursor: "pointer" }}
          >
            <div style={{ width: `${progreso * 100}%`, height: "100%", background: "var(--brand-soft)", transition: arrastrando ? "none" : "width 90ms linear" }} />
          </div>
        </React.Fragment>
      )}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// STOCK PAGE
// ═════════════════════════════════════════════════════════════
const STOCK_DATA = [
  { sku:"BEB-001", name:"Coca-Cola 500ml",        cat:"Bebidas",   zone:"B3", detected:2,  expected:24, conf:91, status:"critical" },
  { sku:"BEB-002", name:"Agua mineral 1.5L",       cat:"Bebidas",   zone:"C2", detected:6,  expected:18, conf:88, status:"low"      },
  { sku:"SNK-014", name:"Papas Lays clásicas",     cat:"Snacks",    zone:"A1", detected:18, expected:20, conf:94, status:"ok"       },
  { sku:"SNK-027", name:"Doritos queso",           cat:"Snacks",    zone:"A1", detected:12, expected:15, conf:87, status:"ok"       },
  { sku:"GLO-005", name:"Chocolatines surtidos",    cat:"Golosinas", zone:"A2", detected:0,  expected:30, conf:82, status:"critical" },
  { sku:"GLO-011", name:"Caramelos masticables",    cat:"Golosinas", zone:"A2", detected:24, expected:24, conf:96, status:"ok"       },
  { sku:"LAC-003", name:"Yogurt Yogurísimo 200g",  cat:"Lácteos",   zone:"H1", detected:4,  expected:12, conf:79, status:"low"      },
  { sku:"LAC-008", name:"Leche entera 1L",          cat:"Lácteos",   zone:"H1", detected:8,  expected:10, conf:85, status:"ok"       },
  { sku:"CIG-002", name:"Marlboro Rojo 20u",        cat:"Cigarrillos",zone:"R1",detected:6,  expected:30, conf:72, status:"low"      },
  { sku:"PAN-001", name:"Pan de hamburguesa x4",   cat:"Panadería", zone:"P1", detected:5,  expected:8,  conf:88, status:"ok"       },
];

function StockPage() {
  const toast = useToast();
  const [cat, setCat] = React.useState("all");
  const [statusFil, setStatusFil] = React.useState("all");

  const categories = ["all", ...Array.from(new Set(STOCK_DATA.map(s => s.cat)))];
  const filtered = STOCK_DATA.filter(s =>
    (cat === "all" || s.cat === cat) &&
    (statusFil === "all" || s.status === statusFil)
  );

  return (
    <main className="content docs">
      <PageHeader
        title="Control de stock"
        subtitle="Productos detectados en góndola vs stock esperado · alertas de faltantes."
        right={
          <>
            <button className="btn-sec" onClick={() => toast("Re-analizando góndolas…", { kind:"info" })}>
              <IcoSpinner style={{ marginRight: 6 }} />Re-escanear
            </button>
            <button className="btn-pri" onClick={() => toast("Reporte enviado a depósito", { kind:"success" })}>
              <IcoSend style={{ marginRight: 6 }} />Pedir reposición
            </button>
          </>
        }
      />
      <WipBanner>
        Modelo de detección de productos en entrenamiento · datos mostrados son simulados sobre 10 SKUs piloto.
      </WipBanner>

      <div className="stat-row">
        <div className="stat-mini"><span className="stat-mini-lbl">SKUs monitoreados</span><span className="stat-mini-val mono">10</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">Stock crítico</span><span className="stat-mini-val mono" style={{ color: "var(--alert-soft)" }}>2</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">Stock bajo</span><span className="stat-mini-val mono" style={{ color: "var(--warn)" }}>3</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">OK</span><span className="stat-mini-val mono" style={{ color: "var(--pos-soft)" }}>5</span></div>
        <div className="stat-mini"><span className="stat-mini-lbl">Confianza promedio</span><span className="stat-mini-val mono">86%</span></div>
      </div>

      <div className="filter-bar">
        <div className="filter-grp">
          <span className="filter-lbl">Estado</span>
          <div className="seg">
            {[["all","Todos"],["critical","Crítico"],["low","Bajo"],["ok","OK"]].map(([k,l]) => (
              <button key={k} className={statusFil===k?"on":""} onClick={() => setStatusFil(k)}>{l}</button>
            ))}
          </div>
        </div>
        <div className="filter-grp">
          <span className="filter-lbl">Categoría</span>
          <select className="select-input" value={cat} onChange={(e) => setCat(e.target.value)}>
            {categories.map(c => <option key={c} value={c}>{c === "all" ? "Todas" : c}</option>)}
          </select>
        </div>
        <div style={{ marginLeft: "auto", fontSize: 13, color: "var(--fg-3)" }} className="mono">
          {filtered.length} / {STOCK_DATA.length} SKUs
        </div>
      </div>

      <div className="data-table">
        <div className="dt-head dt-row dt-stock">
          <div>SKU</div><div>Producto</div><div>Categoría</div><div>Zona</div>
          <div>Detectado / Esperado</div><div>Confianza</div><div>Estado</div>
        </div>
        {filtered.map(s => {
          const pct = (s.detected / s.expected) * 100;
          const barColor = s.status === "critical" ? "var(--alert-soft)" : s.status === "low" ? "var(--warn)" : "var(--pos-soft)";
          return (
            <div key={s.sku} className="dt-row dt-stock">
              <div className="mono" style={{ color: "var(--fg-2)", fontSize: 13 }}>{s.sku}</div>
              <div style={{ color: "var(--fg-0)", fontWeight: 500, fontSize: 14.5 }}>{s.name}</div>
              <div style={{ color: "var(--fg-2)", fontSize: 14 }}>{s.cat}</div>
              <div className="mono" style={{ color: "var(--fg-2)", fontSize: 13 }}>{s.zone}</div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="mono" style={{ fontSize: 13, color: "var(--fg-0)", minWidth: 50 }}>{s.detected} / {s.expected}</span>
                  <div style={{ flex: 1, height: 4, background: "var(--bg-1)", borderRadius: 99 }}>
                    <div style={{ width: `${Math.min(100, pct)}%`, height: "100%", background: barColor, borderRadius: 99 }} />
                  </div>
                </div>
              </div>
              <div className="mono" style={{ color: s.conf < 80 ? "var(--warn)" : "var(--fg-1)", fontSize: 13 }}>{s.conf}%</div>
              <div>{stockBadge(s.status)}</div>
            </div>
          );
        })}
      </div>
    </main>
  );
}

function stockBadge(s) {
  const map = {
    critical: { label: "Crítico", color: "var(--alert-soft)", bg: "rgba(192,57,43,.12)",  border: "rgba(226,92,78,.25)" },
    low:      { label: "Bajo",    color: "var(--warn)",        bg: "rgba(214,137,32,.12)", border: "rgba(214,137,32,.25)" },
    ok:       { label: "OK",      color: "var(--pos-soft)",    bg: "rgba(46,163,79,.1)",   border: "rgba(46,163,79,.22)" },
  };
  const x = map[s];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 99,
      fontSize: 12.5, fontWeight: 500, color: x.color, background: x.bg, border: `1px solid ${x.border}`, whiteSpace: "nowrap"
    }}>{x.label}</span>
  );
}

// ═════════════════════════════════════════════════════════════
// CAMERAS PAGE
// ═════════════════════════════════════════════════════════════
function CamerasPage() {
  const toast = useToast();
  const cams = ["Cafetería","Caja 1","Caja 2","Góndolas A"].map((name, i) => ({
    id: i + 1,
    name,
    fps: 25 + Math.floor(Math.random() * 5),
    conf: Math.floor(78 + Math.random() * 18),
    status: "ok",
    detections: Math.floor(2 + Math.random() * 8),
  }));

  return (
    <main className="content docs">
      <PageHeader
        title="Cámaras"
        subtitle="Estado del pipeline RTSP y detección en tiempo real por cámara."
        right={
          <>
            <button className="btn-sec" onClick={() => toast("Test de conectividad iniciado…")}>
              <IcoSpinner style={{ marginRight: 6 }} />Test conectividad
            </button>
            <button className="btn-pri" onClick={() => toast("Función disponible próximamente")}>
              <span style={{ marginRight: 4 }}>+</span>Agregar cámara
            </button>
          </>
        }
      />

      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        gap: 14
      }}>
        {cams.map(c => (
          <div key={c.id} className="panel" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{
              aspectRatio: "16/9", background:
                "radial-gradient(circle at 30% 40%, rgba(37,99,168,.18), transparent 60%), repeating-linear-gradient(45deg, transparent 0, transparent 10px, rgba(255,255,255,0.015) 10px, rgba(255,255,255,0.015) 11px), #0e1729",
              position: "relative", display: "grid", placeItems: "center", color: "var(--fg-3)"
            }}>
              <IcoCam style={{ width: 32, height: 32, opacity: .4 }} />
              <div style={{ position: "absolute", top: 8, left: 8, display: "flex", gap: 6, alignItems: "center", fontSize: 11.5 }}>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 5, padding: "2px 7px", borderRadius: 99,
                  background: "rgba(0,0,0,.5)", color: c.status === "warn" ? "var(--warn)" : "var(--pos-soft)",
                  border: `1px solid ${c.status === "warn" ? "var(--warn)" : "var(--pos-soft)"}33`
                }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: "currentColor", animation: "pulse 1.6s infinite" }} />
                  LIVE
                </span>
                <span className="mono" style={{ padding: "2px 7px", background: "rgba(0,0,0,.5)", borderRadius: 99, color: "#e2e8f0" }}>
                  cam-{c.id}
                </span>
              </div>
              <div style={{ position: "absolute", bottom: 8, right: 8, fontSize: 11.5, color: "var(--fg-3)" }} className="mono">
                {new Date().toLocaleTimeString("es-AR")}
              </div>
              {/* Mock bbox */}
              {c.detections > 0 && (
                <>
                  <div style={{ position: "absolute", top: "40%", left: "30%", width: 36, height: 60, border: "1.5px solid var(--pos-soft)", borderRadius: 2, opacity: .8 }}>
                    <span style={{ position: "absolute", top: -16, left: -1, background: "var(--pos-soft)", color: "#000", fontSize: 10.5, padding: "1px 4px", borderRadius: 2, fontFamily: "var(--font-metric)", fontWeight: 600 }}>person 0.{c.conf}</span>
                  </div>
                  {c.detections > 2 && (
                    <div style={{ position: "absolute", top: "35%", left: "60%", width: 32, height: 56, border: "1.5px solid var(--pos-soft)", borderRadius: 2, opacity: .7 }} />
                  )}
                </>
              )}
            </div>
            <div style={{ padding: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 15, color: "var(--fg-0)", fontWeight: 500 }}>{c.name}</div>
                  <div className="mono" style={{ fontSize: 12, color: "var(--fg-3)" }}>rtsp://nvr.local/ch{c.id}</div>
                </div>
                <button className="iconbtn" onClick={() => toast(`Cámara ${c.id} pausada`)}><IcoMore /></button>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, fontSize: 12.5 }}>
                <div>
                  <div style={{ color: "var(--fg-3)" }}>FPS</div>
                  <div className="mono" style={{ color: "var(--fg-0)", fontWeight: 500 }}>{c.fps}</div>
                </div>
                <div>
                  <div style={{ color: "var(--fg-3)" }}>Confianza</div>
                  <div className="mono" style={{ color: c.conf < 60 ? "var(--warn)" : "var(--fg-0)", fontWeight: 500 }}>{c.conf}%</div>
                </div>
                <div>
                  <div style={{ color: "var(--fg-3)" }}>Detec.</div>
                  <div className="mono" style={{ color: "var(--fg-0)", fontWeight: 500 }}>{c.detections}</div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}

// ═════════════════════════════════════════════════════════════
// SETTINGS PAGE
// ═════════════════════════════════════════════════════════════
function SettingsPage() {
  const toast = useToast();
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

      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 14 }}>
        <nav className="nav" style={{ position: "sticky", top: 0 }}>
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
                    padding: "12px 14px", background: "var(--bg-3)", border: "1px solid var(--line)", borderRadius: 4,
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
                    padding: "10px 14px", background: "var(--bg-3)", border: "1px solid var(--line)", borderRadius: 4
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

export { HeatmapPage, useHeatmapData, fmtDT, TrackingPage, StockPage, CamerasPage, SettingsPage }

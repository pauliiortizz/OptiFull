import { useState, useEffect, useCallback } from 'react'
import { PageHeader, WipBanner, useToast } from '../components/Toast'
import { StatTileRow } from '../components/Sparkline'
import {
  IcoCam, IcoBox, IcoCheck2, IcoSparkle, IcoX, IcoSend, IcoAlert,
} from '../components/Icons'

// ── Pipeline de caja (frontend/api/productos.py + deteccion_productos/) ──
// Este proceso (Flask) y deteccion_productos/main.py NO se importan entre
// sí: se comunican solo a través de la tabla 'caja_estado' en Postgres.
// El flujo acá es: POST /productos/iniciar (arranca el subproceso con la
// fuente elegida) -> polling a GET /productos/estado -> cuando aparece
// 'esperando_decision', se le muestra 'pendiente' a la cajera -> su
// respuesta se manda con POST /productos/accion -> se repite hasta que
// se apaga con POST /productos/detener. Ver db_cashier_agent.py para el
// shape exacto de 'pendiente' según su 'tipo' (confirmar/elegir/manual).
const POLL_MS = 250;

// Opción del selector de fuente para la cámara del celular (IP Camera
// Lite): el detector lee la URL directo; el navegador la ve a través de
// /api/productos/camara (ver productos.py, por qué hace falta).
const FUENTE_CELU = '__celular__';
const URL_CELU_DEFAULT = 'http://admin:admin@192.168.0.10:8081/video';

function leerUrlCelu() {
  try { return localStorage.getItem('optifull.urlCelu') || URL_CELU_DEFAULT; }
  catch { return URL_CELU_DEFAULT; }
}

function useProductosEstado(activo) {
  const [estado, setEstado] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!activo) { setEstado(null); return; }
    let cancelado = false;
    const tick = () => {
      fetch('/api/productos/estado')
        .then(r => r.json())
        .then(d => {
          if (cancelado) return;
          if (d.error) { setError(d.error); return; }
          setError(null);
          setEstado(d);
        })
        .catch(e => { if (!cancelado) setError(String(e)); });
    };
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => { cancelado = true; clearInterval(id); };
  }, [activo]);

  return { estado, error };
}

function useCatalogo() {
  const [productos, setProductos] = useState([]);
  const refresh = useCallback(() => {
    fetch('/api/productos/stock').then(r => r.json())
      .then(d => setProductos(d.productos || []))
      .catch(() => {});
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  return { productos, refresh };
}

function useMetricas(tick) {
  const [m, setM] = useState(null);
  useEffect(() => {
    fetch('/api/productos/metricas').then(r => r.json()).then(d => !d.error && setM(d)).catch(() => {});
  }, [tick]);
  return m;
}

function labelProducto(p) {
  if (!p) return "";
  const partes = [p.marca, p.nombre, p.variante].filter(Boolean);
  const tam = (p.tamano_valor && p.tamano_unidad) ? `${p.tamano_valor}${p.tamano_unidad}` : null;
  return [partes.join(" "), tam].filter(Boolean).join(" · ") || p.sku || "";
}

function QtyStepper({ value, onChange }) {
  return (
    <div className="qty-stepper">
      <button type="button" onClick={() => onChange(Math.max(1, value - 1))}>–</button>
      <input
        type="number" min={1} value={value}
        onChange={e => onChange(Math.max(1, parseInt(e.target.value, 10) || 1))}
      />
      <button type="button" onClick={() => onChange(value + 1)}>+</button>
    </div>
  );
}

export function ProductosPage() {
  const toast = useToast();

  const [activo, setActivo]           = useState(false);
  const [encendiendo, setEncendiendo] = useState(false);
  const [videos, setVideos]           = useState([]);
  const [fuente, setFuente]           = useState(FUENTE_CELU);
  const [urlCelu, setUrlCelu]         = useState(leerUrlCelu);
  const esCelu = fuente === FUENTE_CELU;
  const [ticket, setTicket]           = useState([]);
  const [cantidad, setCantidad]       = useState(1);
  const [indiceElegido, setIndiceElegido] = useState(0);
  const [skuManual, setSkuManual]     = useState("");
  const [enviando, setEnviando]       = useState(false);
  const [metricasTick, setMetricasTick] = useState(0);

  const { estado, error: errorEstado } = useProductosEstado(activo);
  const { productos: catalogo, refresh: refreshStock } = useCatalogo();
  const metricas = useMetricas(metricasTick);

  const pendiente = estado?.pendiente || null;
  const corriendo = !!estado?.corriendo;

  // Videos disponibles en la carpeta videos/ (servidos por /api/video/<nombre>)
  // -- quedan como alternativa a la cámara del celular, para probar con
  // una grabación. La opción por default es el celular.
  useEffect(() => {
    fetch('/api/videos').then(r => r.json()).then(lista => {
      if (Array.isArray(lista)) setVideos(lista);
    }).catch(() => {});
  }, []);

  // Al cambiar la decisión pendiente (no en cada poll -- solo cuando
  // cambia de verdad), resetear el formulario de la cajera.
  useEffect(() => {
    setCantidad(1);
    setIndiceElegido(0);
    setSkuManual("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendiente?.tipo, JSON.stringify(pendiente?.producto?.sku || pendiente?.candidatos?.map(c => c.sku))]);

  const encender = async () => {
    setEncendiendo(true);
    try {
      let body = {};
      if (esCelu) {
        body = { source: urlCelu.trim() };
        try { localStorage.setItem('optifull.urlCelu', urlCelu.trim()); } catch { /* sin storage: no pasa nada */ }
      } else if (fuente) {
        body = { source: `../videos/${fuente}` };
      }
      const r = await fetch('/api/productos/iniciar', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'no se pudo iniciar');
      setActivo(true);
      toast(`Cámara encendida · fuente: ${esCelu ? 'celular' : d.source}`, { kind: 'success' });
    } catch (e) {
      toast(`No se pudo encender la cámara: ${e.message}`, { kind: 'warn' });
    } finally {
      setEncendiendo(false);
    }
  };

  const apagar = async () => {
    setActivo(false);
    try {
      const r = await fetch('/api/productos/detener', { method: 'POST' });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'no se pudo detener');
      toast(d.aviso || 'Cámara apagada', { kind: 'info' });
    } catch (e) {
      toast(`Error al apagar: ${e.message}`, { kind: 'warn' });
    }
  };

  const enviarAccion = async (body) => {
    setEnviando(true);
    try {
      const r = await fetch('/api/productos/accion', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'no se pudo enviar la respuesta');
      return true;
    } catch (e) {
      toast(`Error: ${e.message}`, { kind: 'warn' });
      return false;
    } finally {
      setEnviando(false);
    }
  };

  const registrarEnTicket = (producto, cant) => {
    setTicket(t => [{ id: Date.now(), nombre: labelProducto(producto), cantidad: cant, hora: new Date() }, ...t].slice(0, 20));
    refreshStock();
    setMetricasTick(t => t + 1);
    toast(`Cargado: ${cant} × ${labelProducto(producto)}`, { kind: 'success' });
  };

  const confirmar = async (producto) => {
    if (await enviarAccion({ accion: 'confirmar', cantidad })) registrarEnTicket(producto, cantidad);
  };
  const elegir = async (candidatos) => {
    if (await enviarAccion({ accion: 'elegir', indice: indiceElegido, cantidad })) {
      registrarEnTicket(candidatos[indiceElegido], cantidad);
    }
  };
  const cargarManual = async () => {
    if (!skuManual) return;
    if (await enviarAccion({ accion: 'cargar', sku: skuManual, cantidad })) {
      registrarEnTicket(catalogo.find(p => p.sku === skuManual) || { sku: skuManual }, cantidad);
    }
  };
  const cancelar   = () => enviarAccion({ accion: 'cancelar' });
  const pedirManual = () => enviarAccion({ accion: 'manual' });

  const porEstado = metricas?.por_estado_matching || [];
  const totalMatching = porEstado.reduce((a, r) => a + Number(r.cantidad), 0);
  const reconocidosSolo = porEstado.find(r => r.estado_matching === 'reconocido')?.cantidad ?? 0;

  let decisionContent;
  if (!activo) {
    decisionContent = (
      <div className="pv-decision-empty">
        <IcoCam style={{ width: 26, height: 26, opacity: .35 }} />
        <span>Encendé la cámara para empezar a recibir productos.</span>
      </div>
    );
  } else if (errorEstado) {
    decisionContent = (
      <div className="pv-decision-empty">
        <IcoAlert style={{ width: 26, height: 26, color: 'var(--warn)' }} />
        <span>{errorEstado}</span>
      </div>
    );
  } else if (!pendiente) {
    decisionContent = (
      <div className="pv-decision-empty">
        <IcoSparkle style={{ width: 22, height: 22, opacity: .4 }} />
        <span>{corriendo ? 'Esperando que aparezca un producto…' : 'Iniciando la detección…'}</span>
      </div>
    );
  } else if (pendiente.tipo === 'confirmar') {
    const p = pendiente.producto;
    decisionContent = (
      <>
        <div className="pv-product-card">
          <div className="pv-product-name">{labelProducto(p)}</div>
          <div className="pv-product-meta">SKU {p.sku} · {p.categoria || 'sin categoría'}</div>
          <div className="pv-confidence">Confianza del modelo: {Math.round((pendiente.confianza || 0) * 100)}%</div>
        </div>
        <div className="pv-field">
          <label>Cantidad</label>
          <QtyStepper value={cantidad} onChange={setCantidad} />
        </div>
        <div className="pv-actions">
          <button className="btn-pri" disabled={enviando} onClick={() => confirmar(p)}><IcoCheck2 style={{ marginRight: 4 }} />Confirmar</button>
          <button className="btn-sec" disabled={enviando} onClick={pedirManual}>Corregir manualmente</button>
          <button className="btn-sec" disabled={enviando} onClick={cancelar}><IcoX style={{ marginRight: 4 }} />Cancelar</button>
        </div>
      </>
    );
  } else if (pendiente.tipo === 'elegir') {
    const candidatos = pendiente.candidatos || [];
    decisionContent = (
      <>
        <div className="pv-candidates">
          {candidatos.map((c, i) => (
            <div key={c.sku} className={`pv-candidate${i === indiceElegido ? ' on' : ''}`} onClick={() => setIndiceElegido(i)}>
              <input type="radio" checked={i === indiceElegido} onChange={() => setIndiceElegido(i)} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="pv-product-name" style={{ fontSize: 13 }}>{labelProducto(c)}</div>
                <div className="pv-product-meta">SKU {c.sku}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="pv-field">
          <label>Cantidad</label>
          <QtyStepper value={cantidad} onChange={setCantidad} />
        </div>
        <div className="pv-actions">
          <button className="btn-pri" disabled={enviando || candidatos.length === 0} onClick={() => elegir(candidatos)}><IcoCheck2 style={{ marginRight: 4 }} />Confirmar elección</button>
          <button className="btn-sec" disabled={enviando} onClick={pedirManual}>Cargar manualmente</button>
          <button className="btn-sec" disabled={enviando} onClick={cancelar}><IcoX style={{ marginRight: 4 }} />Cancelar</button>
        </div>
      </>
    );
  } else if (pendiente.tipo === 'manual') {
    decisionContent = (
      <>
        <div className="pv-field">
          <label>Producto (catálogo)</label>
          <select value={skuManual} onChange={e => setSkuManual(e.target.value)}>
            <option value="">— elegir producto —</option>
            {catalogo.map(p => (
              <option key={p.sku} value={p.sku}>{labelProducto(p)} ({p.sku})</option>
            ))}
          </select>
        </div>
        <div className="pv-field">
          <label>Cantidad</label>
          <QtyStepper value={cantidad} onChange={setCantidad} />
        </div>
        <div className="pv-actions">
          <button className="btn-pri" disabled={enviando || !skuManual} onClick={cargarManual}><IcoSend style={{ marginRight: 4 }} />Cargar</button>
          <button className="btn-sec" disabled={enviando} onClick={cancelar}><IcoX style={{ marginRight: 4 }} />Cancelar</button>
        </div>
      </>
    );
  }

  return (
    <main className="content">
      <PageHeader
        title="Productos — Punto de venta"
        subtitle="Detección de productos en caja: la cajera confirma antes de descontar stock."
        right={
          <label className="cam-switch">
            <span>{activo ? 'Cámara encendida' : 'Cámara apagada'}</span>
            <button
              type="button" role="switch" aria-checked={activo} className="switch"
              data-on={activo ? '1' : '0'} disabled={encendiendo}
              onClick={() => (activo ? apagar() : encender())}
            ><i /></button>
          </label>
        }
      />

      <WipBanner>
        Por ahora la "cámara" reproduce un video ya grabado, no sincronizado con el análisis: el backend lee el mismo archivo por su cuenta y tarda más
        porque cada producto candidato pasa por un modelo de lenguaje antes de mostrarse acá a la derecha. Con cámara en vivo esto deja de pasar
        (un solo feed, no dos lecturas independientes) — queda para una etapa posterior del proyecto.
      </WipBanner>

      <StatTileRow items={[
        { label: "Transacciones", Ico: IcoBox, value: metricas ? metricas.total_transacciones : "—", sub: "ventas confirmadas por la cajera" },
        { label: "Confianza LLM", Ico: IcoSparkle, value: metricas ? Math.round(metricas.confianza_promedio * 100) : "—", unit: metricas ? "%" : "", sub: "promedio sobre todas las detecciones" },
        { label: "Reconocidos solos", Ico: IcoCheck2, value: reconocidosSolo, unit: totalMatching ? `de ${totalMatching}` : "", sub: "sin pedirle a la cajera que elija" },
        { label: "Estado cámara", Ico: IcoCam, value: activo ? (corriendo ? "Encendida" : "Iniciando") : "Apagada", sub: activo ? `fuente: ${esCelu ? 'celular' : fuente}` : "switch arriba a la derecha" },
      ]} />

      <div className="console-grid">
        <div className="panel console-plan">
          <div className="panel-head">
            <div className="panel-title"><span className="ico"><IcoCam /></span>Vista de caja</div>
            {!activo && (
              <select className="btn-sec" style={{ maxWidth: 220 }} value={fuente} onChange={e => setFuente(e.target.value)}>
                <option value={FUENTE_CELU}>📱 Cámara del celular</option>
                {videos.map(v => <option key={v} value={v}>{v}</option>)}
              </select>
            )}
            {activo && (
              <span className={`cam-chip ${corriendo ? 'live' : 'offline'}`}>
                {corriendo && <span className="live-dot" />}
                {corriendo ? 'PROCESANDO' : 'INICIANDO…'}
              </span>
            )}
          </div>

          {!activo && esCelu && (
            <div className="pv-field">
              <label>Dirección de la cámara (IP Camera Lite)</label>
              <input
                className="pv-url-input" value={urlCelu} onChange={e => setUrlCelu(e.target.value)}
                placeholder={URL_CELU_DEFAULT} spellCheck={false}
              />
            </div>
          )}

          <div className="pv-video-frame">
            {activo && esCelu ? (
              <img
                src={`/api/productos/camara?url=${encodeURIComponent(urlCelu.trim())}`}
                alt="Cámara del celular en vivo"
                style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              />
            ) : activo && fuente ? (
              <video
                key={fuente}
                src={`/api/video/${encodeURIComponent(fuente)}`}
                controls autoPlay muted
                style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              />
            ) : (
              <div className="pv-video-empty">
                <IcoCam style={{ width: 32, height: 32, opacity: .35 }} />
                <span>Cámara apagada — elegí un video y activá el switch para empezar a vender.</span>
              </div>
            )}
          </div>
          {activo && (
            <div className="pv-video-caption">
              {esCelu
                ? 'En vivo desde el celular — es la misma cámara que está analizando el detector.'
                : 'Grabación de referencia — no representa en vivo lo que el modelo está analizando en este momento (ver aviso arriba).'}
            </div>
          )}
        </div>

        <div className="console-side">
          <div className="panel" style={{ flex: 'none' }}>
            <div className="panel-head">
              <div className="panel-title">Producto detectado</div>
            </div>
            {decisionContent}
          </div>

          <div className="panel">
            <div className="panel-head">
              <div className="panel-title">Ticket de esta sesión</div>
              <span className="mono" style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{ticket.length} ítem(s)</span>
            </div>
            {ticket.length === 0 ? (
              <div style={{ padding: '16px 0', textAlign: 'center', color: 'var(--fg-3)', fontSize: 12.5 }}>
                Todavía no se confirmó ningún producto.
              </div>
            ) : (
              <div className="pv-ticket-list">
                {ticket.map(it => (
                  <div key={it.id} className="pv-ticket-row">
                    <span className="pv-ticket-qty mono">×{it.cantidad}</span>
                    <span className="pv-ticket-name">{it.nombre}</span>
                    <span className="pv-ticket-time mono">
                      {it.hora.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

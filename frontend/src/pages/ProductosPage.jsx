import { useState, useEffect, useCallback, useRef } from 'react'
import { PageHeader, useToast } from '../components/Toast'
import {
  IcoCam, IcoCheck2, IcoSparkle, IcoX, IcoSend, IcoAlert,
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

// El ticket todavía no está en la base (se guarda recién al confirmar la
// venta), así que se respalda en el navegador: si se recarga la página a
// mitad de una venta, no se pierden los productos ya cargados.
const TICKET_KEY = 'optifull.ticket';
function leerTicket() {
  try {
    return (JSON.parse(localStorage.getItem(TICKET_KEY)) || [])
      .map(it => ({ ...it, hora: new Date(it.hora) }));
  } catch { return []; }
}

function formatoPrecio(valor) {
  return Number(valor || 0).toLocaleString('es-AR', { style: 'currency', currency: 'ARS' });
}

function useProductosEstado(activo) {
  const [estado, setEstado] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!activo) { setEstado(null); return; }
    let cancelado = false;
    let id = null;
    // El próximo poll se agenda recién cuando volvió el anterior (no con
    // setInterval): cada consulta a Supabase tarda ~0.3-0.5s, más que
    // POLL_MS, y con setInterval se iban encimando hasta agotar el pool
    // de conexiones de Flask -- confirmar/cancelar quedaba en la cola.
    const tick = () => {
      fetch('/api/productos/estado')
        .then(r => r.json())
        .then(d => {
          if (cancelado) return;
          if (d.error) { setError(d.error); return; }
          setError(null);
          setEstado(d);
        })
        .catch(e => { if (!cancelado) setError(String(e)); })
        .finally(() => { if (!cancelado) id = setTimeout(tick, POLL_MS); });
    };
    tick();
    return () => { cancelado = true; clearTimeout(id); };
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
  const ultimaBaja = useRef(0);   // cuándo se apagó la cámara por última vez (el detector tarda unos segundos en parar)
  const [ticket, setTicket]           = useState(leerTicket);
  const [confirmandoVenta, setConfirmandoVenta] = useState(false);
  const [cantidad, setCantidad]       = useState(1);
  const [indiceElegido, setIndiceElegido] = useState(0);
  const [skuManual, setSkuManual]     = useState("");
  const [enviando, setEnviando]       = useState(false);
  // Cada error de la imagen de la cámara (celular todavía no disponible) la vuelve a pedir a los 2s.
  const [intentoCam, setIntentoCam]   = useState(0);

  // Si el detector ya estaba corriendo (por ejemplo al recargar la página), se muestra la cámara como encendida
  // en vez de dejar el interruptor apagado -- si no, al encenderla de nuevo el servidor responde 409.
  useEffect(() => {
    fetch('/api/productos/estado').then(r => r.json()).then(d => { if (d?.corriendo) setActivo(true); }).catch(() => {});
  }, []);

  const { estado, error: errorEstado } = useProductosEstado(activo);
  const { productos: catalogo, refresh: refreshStock } = useCatalogo();

  // Decisión que la cajera ya respondió: se oculta al instante en vez de
  // esperar a que main.py la procese y el próximo poll la vea vacía
  // (eso son varias idas y vueltas a Supabase, ~1-2s con el botón ahí).
  const [respondido, setRespondido]   = useState(null);
  const pendienteDb = estado?.pendiente || null;
  const pendiente = pendienteDb && JSON.stringify(pendienteDb) !== respondido ? pendienteDb : null;
  const corriendo = !!estado?.corriendo;

  useEffect(() => { if (!pendienteDb) setRespondido(null); }, [pendienteDb]);

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
      if (r.status === 409) {
        // "la caja ya esta corriendo": o ya estaba encendida, o se la acaba de apagar y todavía está deteniéndose.
        if (Date.now() - ultimaBaja.current < 8000) {
          toast('La cámara se está deteniendo: esperá unos segundos y volvé a encenderla.', { kind: 'info' });
        } else {
          setActivo(true);
          toast('La cámara ya estaba encendida.', { kind: 'info' });
        }
        return;
      }
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
    ultimaBaja.current = Date.now();
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
      setRespondido(JSON.stringify(pendienteDb));
      return true;
    } catch (e) {
      toast(`Error: ${e.message}`, { kind: 'warn' });
      return false;
    } finally {
      setEnviando(false);
    }
  };

  useEffect(() => {
    try { localStorage.setItem(TICKET_KEY, JSON.stringify(ticket)); } catch { /* sin storage: no pasa nada */ }
  }, [ticket]);

  // Confirmar un producto solo lo suma al ticket: el stock se descuenta
  // recién con "Confirmar venta". 'meta' (confianza, estado del matching,
  // JSON del LLM) viaja con el item para guardarlo en 'transacciones'.
  const registrarEnTicket = (producto, cant) => {
    const delCatalogo = catalogo.find(p => p.sku === producto.sku) || producto;
    const meta = pendienteDb?.meta || {};
    setTicket(t => [{
      id: Date.now(), sku: producto.sku, nombre: labelProducto(delCatalogo),
      precio: Number(delCatalogo.precio || 0), cantidad: cant, hora: new Date(),
      confianza_llm: meta.confianza_llm ?? null,
      estado_matching: meta.estado_matching || 'manual',
      datos_llm: meta.datos_llm || null,
    }, ...t]);
    toast(`Agregado al ticket: ${cant} × ${labelProducto(delCatalogo)}`, { kind: 'success' });
  };

  const quitarDelTicket = (id) => setTicket(t => t.filter(it => it.id !== id));
  const totalTicket = ticket.reduce((a, it) => a + it.precio * it.cantidad, 0);

  const vaciarTicket = () => {
    if (ticket.length && window.confirm('¿Vaciar el ticket? Se descartan todos los productos cargados.')) setTicket([]);
  };

  const confirmarVenta = async () => {
    setConfirmandoVenta(true);
    try {
      const r = await fetch('/api/productos/venta', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: ticket.map(({ sku, cantidad, confianza_llm, estado_matching, datos_llm }) =>
          ({ sku, cantidad, confianza_llm, estado_matching, datos_llm })) }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'no se pudo confirmar la venta');
      toast(`Venta confirmada · ${formatoPrecio(totalTicket)}`, { kind: 'success' });
      setTicket([]);
      refreshStock();
    } catch (e) {
      toast(`No se pudo confirmar la venta: ${e.message}`, { kind: 'warn' });
    } finally {
      setConfirmandoVenta(false);
    }
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
                key={intentoCam}
                src={`/api/productos/camara?url=${encodeURIComponent(urlCelu.trim())}${intentoCam ? `&intento=${intentoCam}` : ''}`}
                onError={() => setTimeout(() => setIntentoCam(n => n + 1), 2000)}
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
              <div className="panel-title">Ticket de la venta</div>
              <span className="mono" style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{ticket.length} ítem(s)</span>
            </div>
            {ticket.length === 0 ? (
              <div style={{ padding: '16px 0', textAlign: 'center', color: 'var(--fg-3)', fontSize: 12.5 }}>
                Todavía no se cargó ningún producto.
              </div>
            ) : (
              <>
                <div className="pv-ticket-list">
                  {ticket.map(it => (
                    <div key={it.id} className="pv-ticket-row">
                      <span className="pv-ticket-qty mono">×{it.cantidad}</span>
                      <span className="pv-ticket-name" title={it.nombre}>{it.nombre}</span>
                      <span className="pv-ticket-price mono">
                        {formatoPrecio(it.precio * it.cantidad)}
                        {it.cantidad > 1 && <span className="pv-ticket-unit">{formatoPrecio(it.precio)} c/u</span>}
                      </span>
                      <button type="button" className="pv-ticket-del" title="Quitar del ticket"
                        disabled={confirmandoVenta} onClick={() => quitarDelTicket(it.id)}>
                        <IcoX />
                      </button>
                    </div>
                  ))}
                </div>
                <div className="pv-ticket-total">
                  <span>Total</span>
                  <strong className="mono">{formatoPrecio(totalTicket)}</strong>
                </div>
                <div className="pv-ticket-actions">
                  <button className="btn-sec" disabled={confirmandoVenta} onClick={vaciarTicket}>Vaciar</button>
                  <button className="btn-pri" disabled={confirmandoVenta} onClick={confirmarVenta}>
                    <IcoCheck2 style={{ marginRight: 4 }} />{confirmandoVenta ? 'Confirmando…' : 'Confirmar venta'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

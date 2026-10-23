import { useCallback, useEffect, useState } from 'react'
import { PageHeader } from '../components/Toast'
import { StatTileRow } from '../components/Sparkline'
import { IcoReceipt, IcoBox, IcoTrend, IcoSpinner, IcoChev } from '../components/Icons'

// ── Ventas: tickets confirmados en caja ──
// Lee GET /api/ventas (frontend/api/ventas.py). Cada ticket es una venta
// confirmada con "Confirmar venta" en Productos; las ventas anteriores a
// la tabla 'ventas' llegan sin número, un producto por ticket.

const RANGOS = [["hoy", "Hoy"], ["7d", "7 días"], ["30d", "30 días"], ["todo", "Todo"]];
const DIAS_ATRAS = { hoy: 0, "7d": 6, "30d": 29 };

function formatoPrecio(valor) {
  return Number(valor || 0).toLocaleString('es-AR', { style: 'currency', currency: 'ARS' });
}

// YYYY-MM-DD en hora local (toISOString daría la fecha en UTC: de noche ya es "mañana").
function diaLocal(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function urlVentas(rango) {
  if (rango === "todo") return '/api/ventas';
  const desde = new Date();
  desde.setDate(desde.getDate() - DIAS_ATRAS[rango]);
  return `/api/ventas?desde=${diaLocal(desde)}`;
}

function formatoDia(iso) {
  return new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatoHora(iso) {
  return new Date(iso).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
}

// Una fila por ticket (número, día, hora y total); al hacer clic se despliegan sus productos.
function FilaTicket({ venta, abierto, onToggle }) {
  const alternar = (e) => {
    if (e.type === 'keydown' && e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    onToggle();
  };
  return (
    <div>
      <div className={`dt-row dt-ventas${abierto ? ' expanded' : ''}`} role="button" tabIndex={0}
        aria-expanded={abierto} onClick={alternar} onKeyDown={alternar}>
        <div className="vt-numero">{venta.id ? `Ticket #${venta.id}` : 'Venta sin ticket'}</div>
        <time className="mono vt-dato" dateTime={venta.fecha}>{formatoDia(venta.fecha)}</time>
        <div className="mono vt-dato">{formatoHora(venta.fecha)}</div>
        <div className="mono vt-total">{formatoPrecio(venta.total)}</div>
        <div className="vt-chev"><IcoChev style={{ transform: abierto ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }} /></div>
      </div>
      {abierto && <DetalleTicket venta={venta} />}
    </div>
  );
}

function DetalleTicket({ venta }) {
  return (
    <div className="dt-expand vt-detalle">
      <div className="pv-ticket-list">
        {venta.items.map((it, i) => (
          <div key={`${it.sku}-${i}`} className="pv-ticket-row">
            <span className="pv-ticket-qty mono">×{it.cantidad}</span>
            <span className="pv-ticket-name" title={it.nombre}>{it.nombre}</span>
            <span className="pv-ticket-price mono">
              {it.subtotal == null ? '—' : formatoPrecio(it.subtotal)}
              {it.cantidad > 1 && it.precio_unitario != null && (
                <span className="pv-ticket-unit">{formatoPrecio(it.precio_unitario)} c/u</span>
              )}
            </span>
          </div>
        ))}
      </div>
      <div className="pv-ticket-total">
        <span>Total</span>
        <strong className="mono">{formatoPrecio(venta.total)}</strong>
      </div>
    </div>
  );
}

export function VentasPage() {
  const [rango, setRango]     = useState("7d");
  const [datos, setDatos]     = useState(null);
  const [error, setError]     = useState(null);
  const [cargando, setCargando] = useState(false);
  const [abiertos, setAbiertos] = useState(() => new Set());   // claves de los tickets desplegados

  const cargar = useCallback(() => {
    let cancelado = false;
    setCargando(true);
    fetch(urlVentas(rango))
      .then(r => r.json())
      .then(d => {
        if (cancelado) return;
        if (d.error) throw new Error(d.error);
        setDatos(d);
        setError(null);
      })
      .catch(e => { if (!cancelado) setError(e.message); })
      .finally(() => { if (!cancelado) setCargando(false); });
    return () => { cancelado = true; };
  }, [rango]);

  useEffect(() => cargar(), [cargar]);

  const resumen = datos?.resumen;
  const ventas = datos?.ventas || [];
  const claveDe = (v) => v.id ?? `sin-${v.fecha}-${v.items[0]?.sku}`;
  const alternar = (clave) => setAbiertos(prev => {
    const s = new Set(prev);
    if (s.has(clave)) s.delete(clave); else s.add(clave);
    return s;
  });

  return (
    <main className="content">
      <PageHeader
        stacked
        title="Ventas"
        subtitle="Tickets confirmados en caja, con sus productos, el total y la fecha."
        right={
          <>
            <button className="btn-sec" onClick={cargar} disabled={cargando} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <IcoSpinner style={{ width: 13, height: 13, animation: cargando ? "spin 1s linear infinite" : "none" }} />
              {cargando ? "Actualizando…" : "Actualizar"}
            </button>
            <div className="range-tabs">
              {RANGOS.map(([k, l]) => (
                <button key={k} className={rango === k ? "on" : ""} onClick={() => setRango(k)}>{l}</button>
              ))}
            </div>
          </>
        }
      />

      <StatTileRow items={[
        { label: "Tickets", Ico: IcoReceipt, value: resumen ? resumen.tickets : "—", sub: "ventas confirmadas" },
        { label: "Facturado", Ico: IcoTrend, value: resumen ? formatoPrecio(resumen.total) : "—", sub: "suma de los tickets" },
        { label: "Ticket promedio", Ico: IcoReceipt, value: resumen ? formatoPrecio(resumen.ticket_promedio) : "—", sub: "total / tickets" },
        { label: "Unidades", Ico: IcoBox, value: resumen ? resumen.unidades : "—", sub: "productos vendidos" },
      ]} />

      {error ? (
        <div className="panel vt-vacio">No se pudieron cargar las ventas: {error}</div>
      ) : datos && ventas.length === 0 ? (
        <div className="panel vt-vacio">No hay ventas en este período.</div>
      ) : (
        <div className="data-table">
          <div className="dt-head dt-row dt-ventas">
            <div>Ticket</div>
            <div>Día</div>
            <div>Hora</div>
            <div className="vt-total">Total</div>
            <div></div>
          </div>
          {ventas.map(v => (
            <FilaTicket key={claveDe(v)} venta={v} abierto={abiertos.has(claveDe(v))} onToggle={() => alternar(claveDe(v))} />
          ))}
        </div>
      )}
    </main>
  );
}

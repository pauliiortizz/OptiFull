import { useCallback, useEffect, useState } from 'react'
import { PageHeader } from '../components/Toast'
import { StatTileRow } from '../components/Sparkline'
import { IcoReceipt, IcoBox, IcoTrend, IcoSpinner } from '../components/Icons'

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

function formatoFecha(iso) {
  return new Date(iso).toLocaleString('es-AR', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function Ticket({ venta }) {
  return (
    <article className="panel vt-ticket">
      <div className="panel-head">
        <div className="panel-title">{venta.id ? `Ticket #${venta.id}` : 'Venta sin ticket'}</div>
        <time className="mono vt-fecha" dateTime={venta.fecha}>{formatoFecha(venta.fecha)}</time>
      </div>
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
    </article>
  );
}

export function VentasPage() {
  const [rango, setRango]     = useState("7d");
  const [datos, setDatos]     = useState(null);
  const [error, setError]     = useState(null);
  const [cargando, setCargando] = useState(false);

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
        <div className="vt-grid">
          {ventas.map(v => <Ticket key={v.id ?? `sin-${v.fecha}-${v.items[0]?.sku}`} venta={v} />)}
        </div>
      )}
    </main>
  );
}

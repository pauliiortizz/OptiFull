import { useState } from 'react'
import { useToast } from './Toast'
import { IcoUsers, IcoClock, IcoTrend, IcoCalendar, IcoHeat } from './Icons'
import { KpiCard } from './Sparkline'
import {
  BarChart, CongestionHeatmap,
  useTendenciaSemanal, usePermanenciaSemanal, usePromedioDiario, usePosiblesEmpleados,
  useConversionCompra, useCongestionHoraria,
} from './ReportData'

// Métricas históricas (antes en la versión anterior de Reportes) integradas al
// dashboard principal. Reusa los mismos hooks/endpoints y gráficos; no incluye
// los bloques de esa página que eran datos de ejemplo (alertas del período y
// detalle diario con valores inventados).
const sub = { fontSize: 13, color: "var(--fg-3)", marginTop: 4 }

function ReportMetrics({ stats, onStatsChange, children }) {
  const toast = useToast()
  const [metric, setMetric] = useState("flow")
  const [marcando, setMarcando] = useState(null)
  const { data: tendencia, loading: loadingTend } = useTendenciaSemanal()
  const { data: permSemanal, loading: loadingPermSemanal } = usePermanenciaSemanal()
  const { data: promedioDiario } = usePromedioDiario()
  const { data: congestion, loading: loadingCongestion } = useCongestionHoraria()
  const { data: conversion, loading: loadingConversion } = useConversionCompra()
  const { data: empleados, refresh: refreshEmpleados } = usePosiblesEmpleados()

  const days = tendencia?.labels || ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
  const flowWeek = tendencia?.promedio || [0, 0, 0, 0, 0, 0, 0]
  const diasFlow = tendencia?.dias_con_datos || [0, 0, 0, 0, 0, 0, 0]
  const waitWeek = permSemanal?.promedio || [0, 0, 0, 0, 0, 0, 0]
  const diasWait = permSemanal?.dias_con_datos || [0, 0, 0, 0, 0, 0, 0]

  const marcarEmpleado = (clienteId) => {
    setMarcando(clienteId)
    fetch(`/api/personas/${clienteId}/empleado`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ es_empleado: true }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) { toast(d.error, { kind: "warn" }); return }
        toast(`Cliente ${clienteId} marcado como empleado — excluido de las métricas`, { kind: "success" })
        refreshEmpleados()
        onStatsChange?.()
      })
      .catch(() => toast("No se pudo marcar como empleado", { kind: "warn" }))
      .finally(() => setMarcando(null))
  }

  const side = (
    <>
      <div className="kpi-grid" style={{ marginTop: 0, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
        <KpiCard label="Permanencia máxima" value={stats ? stats.permanencia_maxima_min : "—"} unit="min"
          delta="por grabación analizada" trend="neutral" Ico={IcoTrend}
          spark={flowWeek} color="var(--brand-soft)" />
        <KpiCard label="Promedio diario" value={promedioDiario?.promedio ?? "N/D"} unit={promedioDiario?.promedio != null ? "únicas" : ""}
          delta={promedioDiario?.promedio != null
            ? `${promedioDiario.dias_con_datos} día${promedioDiario.dias_con_datos === 1 ? "" : "s"} · todas las cámaras`
            : "requiere múltiples sesiones"} trend="neutral" Ico={IcoCalendar}
          spark={flowWeek} color="var(--fg-3)" />
      </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <div className="panel-title"><span className="ico"><IcoUsers /></span>Conversión de compra</div>
              <div style={sub}>
                {loadingConversion
                  ? "Cargando…"
                  : conversion?.dias_con_datos
                    ? `Promedio diario · ${conversion.dias_con_datos} día${conversion.dias_con_datos === 1 ? "" : "s"} con datos`
                    : "Sin datos todavía -- analizá algún video para clasificar visitas como compra o tránsito."}
              </div>
            </div>
            {conversion?.pct_conversion != null && (
              <span className="mono" style={{ fontSize: 23, fontWeight: 600, color: "var(--pos-soft)" }}>
                {conversion.pct_conversion}%
              </span>
            )}
          </div>
          {!loadingConversion && conversion?.dias_con_datos > 0 && (() => {
            const filas = [
              { label: "Compraron", valor: conversion.promedio_compraron, color: "var(--pos-soft)" },
              { label: "No compraron", valor: conversion.promedio_no_compraron, color: "var(--fg-3)" },
            ]
            const max = Math.max(...filas.map(f => f.valor), 1)
            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 10, justifyContent: "center", flex: 1 }}>
                {filas.map(f => (
                  <div key={f.label} style={{ display: "grid", gridTemplateColumns: "104px minmax(0, 1fr) 64px", alignItems: "center", gap: 10 }}>
                    <div style={{ fontSize: 16, fontWeight: 600, color: "var(--fg-1)", whiteSpace: "nowrap" }}>{f.label}</div>
                    <div style={{ height: 18, position: "relative" }}>
                      <div style={{ width: `${(f.valor / max) * 100}%`, height: "100%", background: f.color, borderRadius: 4, opacity: .85 }} />
                    </div>
                    <div className="mono" style={{ textAlign: "right", whiteSpace: "nowrap", color: "var(--fg-1)", fontSize: 15, fontWeight: 500 }}>
                      {f.valor} / día
                    </div>
                  </div>
                ))}
              </div>
            )
          })()}
        </div>
      
    </>
  )

  const wide = (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(420px, 100%), 1fr))", gap: 8, marginTop: 8 }}>
      <div className="panel">
        <div className="panel-head">
          <div>
            <div className="panel-title"><span className="ico"><IcoTrend /></span>Tendencia semanal</div>
            <div style={sub}>
              {metric === "flow"
                ? (loadingTend ? "Cargando promedio histórico…" : "Promedio histórico por día de la semana · datos reales")
                : (loadingPermSemanal ? "Cargando promedio histórico…" : "Permanencia promedio (min) por día de la semana · datos reales")}
            </div>
          </div>
          <div className="seg">
            <button className={metric === "flow" ? "on" : ""} onClick={() => setMetric("flow")}>Flujo</button>
            <button className={metric === "wait" ? "on" : ""} onClick={() => setMetric("wait")}>Espera</button>
          </div>
        </div>
        <BarChart data={metric === "flow" ? flowWeek : waitWeek} labels={days}
          diasConDatos={metric === "flow" ? diasFlow : diasWait} />
      </div>

      <div className="panel">
        <div className="panel-head">
          <div>
            <div className="panel-title"><span className="ico"><IcoHeat /></span>Horario de congestión</div>
            <div style={sub}>
              {loadingCongestion
                ? "Cargando…"
                : congestion?.pico
                  ? (() => {
                      const p = congestion.pico
                      const rango = `${String(p.hora_inicio).padStart(2, "0")}-${String((p.hora_fin + 1) % 24).padStart(2, "0")}hs`
                      const n = congestion.picos.length - 1
                      const extra = n > 0 ? ` · +${n} pico${n === 1 ? "" : "s"} más (un mismo día puede tener varios)` : ""
                      return `Pico más alto: ${p.dia} ${rango} · ${p.promedio} personas en promedio${extra}`
                    })()
                  : "Personas en cámara por franja horaria, día por día · sin datos suficientes todavía"}
            </div>
          </div>
        </div>
        {congestion && <CongestionHeatmap data={congestion} />}
      </div>

      </div>
      {empleados?.candidatos?.length > 0 && (
        <div className="panel" style={{ marginTop: 8 }}>
          <div className="panel-head">
            <div>
              <div className="panel-title"><span className="ico"><IcoUsers /></span>Posibles empleados</div>
              <div style={sub}>
                Clientes con más de {empleados.umbral_horas}h detectadas en un mismo día · confirmá para excluirlos de las métricas
              </div>
            </div>
          </div>
          <div className="data-table" style={{ border: 0 }}>
            <div className="dt-head dt-row dt-empleados">
              <div>Cliente</div><div>Fecha</div><div>Apariciones</div><div>Tiempo total</div><div>Rango horario</div><div></div>
            </div>
            {empleados.candidatos.map(c => (
              <div key={`${c.cliente_id}-${c.fecha}`} className="dt-row dt-empleados">
                <div className="mono" style={{ color: "var(--fg-0)" }}>#{c.cliente_id}</div>
                <div className="mono" style={{ color: "var(--fg-2)" }}>{c.fecha}</div>
                <div className="mono" style={{ color: "var(--fg-2)" }}>{c.apariciones}</div>
                <div className="mono" style={{ color: "var(--fg-1)" }}>{Math.floor(c.minutos_totales / 60)}h {c.minutos_totales % 60}m</div>
                <div className="mono" style={{ color: "var(--fg-2)" }}>{c.primera_hora.slice(0, 5)}–{c.ultima_hora.slice(0, 5)}</div>
                <div>
                  <button className="btn-sec" disabled={marcando === c.cliente_id} onClick={() => marcarEmpleado(c.cliente_id)}>
                    {marcando === c.cliente_id ? "Marcando…" : "Marcar como empleado"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  )

  return children({ side, wide })
}

export { ReportMetrics }

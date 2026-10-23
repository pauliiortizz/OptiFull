import { useState } from 'react'
import { IcoUsers, IcoClock, IcoTrend, IcoCalendar, IcoHeat } from './Icons'
import { KpiCard } from './Sparkline'
import {
  BarChart, CongestionHeatmap, AnilloConversion,
  useTendenciaSemanal, usePermanenciaSemanal, usePromedioDiario,
  useConversionCompra, useCongestionHoraria,
} from './ReportData'

// Métricas históricas (antes en la versión anterior de Reportes) integradas al
// dashboard principal. Reusa los mismos hooks/endpoints y gráficos; no incluye
// los bloques de esa página que eran datos de ejemplo (alertas del período y
// detalle diario con valores inventados).
const sub = { fontSize: 13, color: "var(--fg-3)", marginTop: 4 }
const DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

const aFecha = (iso) => new Date(`${iso}T00:00:00`)
const isoDe = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
const diaSemana = (d) => (d.getDay() + 6) % 7   // 0 = lunes, como DIAS
const ddmm = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7)

// Barras de "Tendencia semanal" a partir de la respuesta de tendencia-semanal / permanencia-semanal.
//  - diario (Hoy / 7 días): una barra por fecha, de rango.desde a rango.hasta (p. ej. Vie 16 ... Vie 23).
//  - por día de la semana (30 días / Personalizado): el promedio de los lunes, martes, etc. del período,
//    ordenado para que la última barra sea el día de la semana de rango.hasta.
function serieTendencia(resp, rango, diario) {
  if (diario) {
    const valores = Object.fromEntries((resp?.por_fecha || []).map((f) => [f.fecha, f.valor]))
    const fechas = []
    for (let d = aFecha(rango.desde); d <= aFecha(rango.hasta); d.setDate(d.getDate() + 1)) fechas.push(isoDe(d))
    return {
      labels:       fechas.map((f) => `${DIAS[diaSemana(aFecha(f))]} ${aFecha(f).getDate()}`),
      data:         fechas.map((f) => valores[f] ?? 0),
      diasConDatos: fechas.map((f) => (f in valores ? 1 : 0)),
      pies:         fechas.map(ddmm),
    }
  }
  const ultimo = diaSemana(aFecha(rango.hasta))
  const orden = Array.from({ length: 7 }, (_, k) => (ultimo + 1 + k) % 7)
  const promedio = resp?.promedio || Array(7).fill(0)
  const dias = resp?.dias_con_datos || Array(7).fill(0)
  return { labels: orden.map((i) => DIAS[i]), data: orden.map((i) => promedio[i]), diasConDatos: orden.map((i) => dias[i]), pies: null }
}

// Grilla de "Horario de congestión", con el mismo criterio que la tendencia:
//  - diario (Hoy / 7 días): una fila por fecha del filtro (con Hoy, solo la de hoy); las horas de hoy que
//    todavía no pasaron se marcan aparte.
//  - por día de la semana (30 días / Personalizado): el promedio de cada día de la semana, terminando en el
//    día de la semana de rango.hasta.
function datosCongestion(resp, rango, diario) {
  if (!resp?.matriz) return null
  if (diario) {
    const filas = Object.fromEntries((resp.por_fecha || []).map((f) => [f.fecha, f.horas]))
    const fechas = []
    for (let d = aFecha(rango.desde); d <= aFecha(rango.hasta); d.setDate(d.getDate() + 1)) fechas.push(isoDe(d))
    const etiqueta = (f) => `${DIAS[diaSemana(aFecha(f))]} ${aFecha(f).getDate()}`
    const ahora = new Date(), hoy = isoDe(ahora)
    const matriz = fechas.map((f) => filas[f] || Array(24).fill(0))
    const picos = (resp.picos_por_fecha || []).filter((p) => fechas.includes(p.dia)).map((p) => ({ ...p, dia: etiqueta(p.dia) }))
    return {
      dias: fechas.map(etiqueta), horas: resp.horas, matriz, picos,
      dias_con_datos: matriz.map((fila) => fila.map((c) => (c > 0 ? 1 : 0))),
      futuro: fechas.map((f) => resp.horas.map((h) => f === hoy && h > ahora.getHours())),
      pico: picos[0] || null,
    }
  }
  const ultimo = diaSemana(aFecha(rango.hasta))
  const orden = Array.from({ length: 7 }, (_, k) => (ultimo + 1 + k) % 7)
  return {
    dias: orden.map((i) => DIAS[i]), horas: resp.horas || Array.from({ length: 24 }, (_, h) => h),
    matriz: orden.map((i) => resp.matriz[i] || Array(24).fill(0)),
    dias_con_datos: orden.map((i) => resp.dias_con_datos?.[i] || Array(24).fill(0)),
    picos: resp.picos || [], pico: resp.pico || null,
  }
}

// Texto de un panel que no trajo datos: distingue "no hay datos en el período" de "no se pudo consultar"
// (antes ambos decían "Sin datos todavía" y un corte de la base parecía falta de datos).
const sinDatos = (resp, texto = "Sin datos en este período.") =>
  !resp || resp.fuente === "sin_bd" ? "No se pudo consultar la base de datos · probá con Actualizar datos." : texto

// rango: filtro del dashboard ({desde, hasta}); rangoTendencia: el del gráfico de tendencia (con Hoy son los
// mismos 8 días que con 7 días); diario: barras por fecha (Hoy / 7 días) o por día de la semana; tick: "Actualizar datos".
function ReportMetrics({ stats, rango, rangoTendencia, diario, tick, children }) {
  const [metric, setMetric] = useState("flow")
  const { data: tendencia, loading: loadingTend } = useTendenciaSemanal(rangoTendencia, tick)
  const { data: permSemanal, loading: loadingPermSemanal } = usePermanenciaSemanal(rangoTendencia, tick)
  const { data: promedioDiario, loading: loadingPromedio } = usePromedioDiario(rango, tick)
  const { data: congestion, loading: loadingCongestion } = useCongestionHoraria(rango, tick)
  const { data: conversion, loading: loadingConversion } = useConversionCompra(rango, tick)

  const flujo = serieTendencia(tendencia, rangoTendencia, diario)
  const espera = serieTendencia(permSemanal, rangoTendencia, diario)
  const actual = metric === "flow" ? flujo : espera
  const congestionVista = datosCongestion(congestion, rango, diario)
  const periodoTend = `${ddmm(rangoTendencia.desde)} – ${ddmm(rangoTendencia.hasta)}`

  const side = (
    <>
      <div className="kpi-grid" style={{ marginTop: 0, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
        <KpiCard label="Permanencia máxima" value={stats && stats.personas_validas > 0 ? stats.permanencia_maxima_min : "—"} unit="min"
          trend="neutral" Ico={IcoTrend}
          spark={espera.data} sparkLabels={espera.labels} sparkUnidad="min" color="var(--brand-soft)" />
        <KpiCard label="Promedio diario" value={promedioDiario?.promedio ?? "—"} unit={promedioDiario?.promedio != null ? "personas" : ""}
          delta={loadingPromedio || promedioDiario?.promedio != null ? null
            : (promedioDiario?.fuente === "db" ? "sin datos en este período" : "no se pudo consultar")} trend="neutral" Ico={IcoCalendar}
          spark={flujo.data} sparkLabels={flujo.labels} sparkUnidad="personas" color="var(--fg-3)" />
      </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <div className="panel-title"><span className="ico"><IcoUsers /></span>Conversión de compra</div>
              <div style={sub}>
                {loadingConversion
                  ? "Cargando…"
                  : conversion?.dias_con_datos
                    ? "Promedio por día"
                    : sinDatos(conversion, "Sin visitas clasificadas como compra o tránsito en este período.")}
              </div>
            </div>
          </div>
          {!loadingConversion && conversion?.dias_con_datos > 0 && (
            <AnilloConversion pct={conversion.pct_conversion}
              compraron={conversion.promedio_compraron} noCompraron={conversion.promedio_no_compraron} />
          )}
        </div>

    </>
  )

  const cargandoTend = metric === "flow" ? loadingTend : loadingPermSemanal
  const respTend = metric === "flow" ? tendencia : permSemanal
  const wide = (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(420px, 100%), 1fr))", gap: "var(--gap)" }}>
      <div className="panel">
        <div className="panel-head">
          <div>
            <div className="panel-title"><span className="ico"><IcoTrend /></span>Tendencia semanal</div>
            <div style={sub}>
              {cargandoTend ? "Cargando…"
                : !respTend || respTend.fuente === "sin_bd" ? sinDatos(respTend)
                : `${metric === "flow" ? "Personas únicas" : "Permanencia promedio (min)"} ${diario
                    ? `por día · ${periodoTend}`
                    : `· promedio por día de la semana · ${periodoTend}`}`}
            </div>
          </div>
          <div className="seg">
            <button className={metric === "flow" ? "on" : ""} onClick={() => setMetric("flow")}>Flujo</button>
            <button className={metric === "wait" ? "on" : ""} onClick={() => setMetric("wait")}>Espera</button>
          </div>
        </div>
        <BarChart data={actual.data} labels={actual.labels} diasConDatos={actual.diasConDatos} pies={actual.pies}
          destacar={actual.data.length - 1} promedio={!diario} unidad={metric === "flow" ? "personas" : "min"} />
      </div>

      <div className="panel">
        <div className="panel-head">
          <div>
            <div className="panel-title"><span className="ico"><IcoHeat /></span>Horario de congestión</div>
            <div style={sub}>
              {loadingCongestion
                ? "Cargando…"
                : congestionVista?.pico
                  ? (() => {
                      const p = congestionVista.pico
                      const rangoHs = `${String(p.hora_inicio).padStart(2, "0")}-${String((p.hora_fin + 1) % 24).padStart(2, "0")}hs`
                      const n = (congestionVista.picos?.length ?? 1) - 1
                      const extra = n > 0 ? ` · +${n} pico${n === 1 ? "" : "s"} más (un mismo día puede tener varios)` : ""
                      return `Pico más alto: ${p.dia} ${rangoHs} · ${p.promedio} personas${diario ? "" : " en promedio"}${extra}`
                    })()
                  : sinDatos(congestion, "Personas en cámara por franja horaria · sin datos en este período")}
            </div>
          </div>
        </div>
        {congestionVista && <CongestionHeatmap data={congestionVista} destacar={congestionVista.dias.length - 1} />}
      </div>

      </div>
    </>
  )

  return children({ side, wide })
}

export { ReportMetrics }

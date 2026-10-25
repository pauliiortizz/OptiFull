// Pruebas de los hooks de datos de /api/reportes/* y de los gráficos (barras y franjas de congestión).
import { describe, test, expect } from 'vitest'
import { fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { apiFalsa } from '../test/apiFalsa.js'
import { conMovimientoReducido } from '../test/movimiento.js'
import {
  BarChart, CongestionHeatmap,
  useTendenciaSemanal, usePermanenciaSemanal, usePromedioDiario,
  useConversionCompra, usePermanenciaPorZona, useCongestionHoraria,
} from './ReportData'

conMovimientoReducido()

const DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']

// Respuestas con la forma real del backend (frontend/api/reportes.py)
const RESPUESTAS = {
  '/api/reportes/tendencia-semanal': { labels: DIAS, promedio: [31, 28, 0, 40, 55, 72, 18], dias_con_datos: [2, 1, 0, 3, 3, 2, 1], fuente: 'db' },
  '/api/reportes/permanencia-semanal': { labels: DIAS, promedio: [6.4, 5.1, 0, 7.2, 8, 9.5, 4], dias_con_datos: [2, 1, 0, 3, 3, 2, 1], fuente: 'db' },
  '/api/reportes/promedio-diario': { promedio: 47, dias_con_datos: 12, fuente: 'db' },
  '/api/reportes/conversion-compra': { promedio_compraron: 18, promedio_no_compraron: 30, pct_conversion: 37.5, dias_con_datos: 12, fuente: 'db' },
  '/api/reportes/permanencia-por-zona': { zonas: [{ zona: 'Caja', minutos: 3.2 }, { zona: 'Góndolas', minutos: 5.8 }], fuente: 'db' },
  '/api/reportes/congestion-horaria': { dias: DIAS, horas: [0, 1], matriz: [[0, 0]], dias_con_datos: [[0, 0]], pico: null, picos: [], fuente: 'db' },
}

const HOOKS = [
  ['useTendenciaSemanal', useTendenciaSemanal, '/api/reportes/tendencia-semanal'],
  ['usePermanenciaSemanal', usePermanenciaSemanal, '/api/reportes/permanencia-semanal'],
  ['usePromedioDiario', usePromedioDiario, '/api/reportes/promedio-diario'],
  ['useConversionCompra', useConversionCompra, '/api/reportes/conversion-compra'],
  ['usePermanenciaPorZona', usePermanenciaPorZona, '/api/reportes/permanencia-por-zona'],
  ['useCongestionHoraria', useCongestionHoraria, '/api/reportes/congestion-horaria'],
]

describe('hooks de datos de reportes', () => {
  test.each(HOOKS)('%s pide su endpoint una sola vez y entrega los datos', async (_n, hook, ruta) => {
    const api = apiFalsa({ [ruta]: RESPUESTAS[ruta] })
    const { result } = renderHook(() => hook())
    expect(result.current).toEqual({ data: null, loading: true })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(RESPUESTAS[ruta])
    expect(api.pedidos.map((p) => p.url)).toEqual([ruta])
  })

  test.each(HOOKS)('%s: si la red falla deja de cargar y queda sin datos', async (_n, hook, ruta) => {
    apiFalsa({ [ruta]: new TypeError('Failed to fetch') })
    const { result } = renderHook(() => hook())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toBeNull()
  })
})

describe('BarChart', () => {
  test('muestra etiquetas, valores y "sin datos", sin contar cuántos días tiene cada barra', () => {
    const { container } = render(<BarChart data={[31, 28, 0]} labels={['Lun', 'Mar', 'Mié']} diasConDatos={[2, 1, 0]} />)
    for (const t of ['Lun', 'Mar', 'Mié', '31', '28', 'sin datos']) expect(screen.getByText(t)).toBeInTheDocument()
    expect(screen.queryByText(/\d+ días?$/)).toBeNull()
    // La barra sin datos se atenúa y no muestra su valor encima (las otras rect son las zonas del hover)
    const barras = container.querySelectorAll('rect.gr-barra')
    expect(barras).toHaveLength(3)
    expect(barras[2]).toHaveAttribute('opacity', '0.25')
    expect(barras[0]).toHaveAttribute('opacity', '1')
    // La barra más alta es la del valor mayor
    expect(Number(barras[0].getAttribute('height'))).toBeGreaterThan(Number(barras[1].getAttribute('height')))
  })

  test('sin diasConDatos no muestra el contador de días y dibuja todas las barras normales', () => {
    const { container } = render(<BarChart data={[5, 7]} labels={['A', 'B']} />)
    expect(screen.queryByText(/día/)).toBeNull()
    expect(screen.queryByText('sin datos')).toBeNull()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(container.querySelectorAll('rect[opacity="1"]')).toHaveLength(2)
  })

  test('todos ceros: escala mínima, sin NaN y eje que arranca en 0', () => {
    const { container } = render(<BarChart data={[0, 0, 0]} labels={['A', 'B', 'C']} diasConDatos={[0, 0, 0]} />)
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/)
    expect(screen.getAllByText('sin datos')).toHaveLength(3)
    expect(screen.getAllByText('0').length).toBeGreaterThan(0)
  })

  test('las marcas del eje Y redondean el máximo con 15 % de margen', () => {
    const { container } = render(<BarChart data={[100]} labels={['Lun']} />)
    // max = 115 -> cinco marcas enteras y crecientes de 0 a 115
    const marcas = [...container.querySelectorAll('g > text')].slice(0, 5).map((t) => Number(t.textContent))
    expect(marcas[0]).toBe(0)
    expect(marcas[4]).toBe(115)
    for (let i = 1; i < 5; i++) {
      expect(Number.isInteger(marcas[i])).toBe(true)
      expect(marcas[i]).toBeGreaterThan(marcas[i - 1])
    }
  })
})

describe('CongestionHeatmap', () => {
  const horas = Array.from({ length: 24 }, (_, h) => h)
  const fila = (f) => horas.map(f)
  const data = {
    dias: ['Lun', 'Vie'],
    horas,
    matriz: [fila((h) => (h === 9 ? 4 : 0)), fila((h) => (h === 12 ? 9 : h === 23 ? 2 : 0))],
    dias_con_datos: [fila((h) => (h === 9 ? 1 : 0)), fila((h) => (h === 12 || h === 23 ? 3 : 0))],
  }

  test('muestra los días, las horas cada 3 y la leyenda', () => {
    render(<CongestionHeatmap data={data} />)
    expect(screen.getByText('Lun')).toBeInTheDocument()
    expect(screen.getByText('Vie')).toBeInTheDocument()
    for (const h of [0, 3, 6, 9, 12, 15, 18, 21]) expect(screen.getByText(String(h))).toBeInTheDocument()
    expect(screen.queryByText('1')).toBeNull()
    expect(screen.getByText('menos gente')).toBeInTheDocument()
    expect(screen.getByText('más gente')).toBeInTheDocument()
  })

  test('con el cursor, el globo de cada hora indica la franja y las personas; 23hs cierra en 00', () => {
    const { container } = render(<CongestionHeatmap data={data} />)
    const celdas = container.querySelectorAll('rect.gr-celda')   // por día y, dentro del día, por hora
    expect(celdas).toHaveLength(48)
    const globo = container.querySelector('.gr-globo')
    expect(globo).not.toHaveClass('is-visible')
    const detalle = (dia, hora) => { fireEvent.pointerEnter(celdas[dia * 24 + hora]); return globo.textContent }
    expect(detalle(0, 9)).toBe('Lun 09–10 hs4 personas')
    expect(globo).toHaveClass('is-visible')
    expect(detalle(1, 12)).toBe('Vie 12–13 hs9 personas')
    expect(detalle(1, 23)).toBe('Vie 23–00 hs2 personas')
    expect(detalle(0, 0)).toBe('Lun 00–01 hssin datos')
    fireEvent.pointerLeave(container.querySelector('svg'))
    expect(globo).not.toHaveClass('is-visible')
  })

  test('una celda por hora y día, sin NaN aunque todo esté en cero; las horas sin datos van en gris', () => {
    const vacia = { dias: DIAS, horas, matriz: DIAS.map(() => fila(() => 0)), dias_con_datos: DIAS.map(() => fila(() => 0)) }
    const { container } = render(<CongestionHeatmap data={vacia} />)
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/)
    const celdas = [...container.querySelectorAll('rect.gr-celda')]
    expect(celdas).toHaveLength(7 * 24)
    for (const c of celdas) expect(c).toHaveAttribute('fill', 'var(--bg-3)')
  })
})

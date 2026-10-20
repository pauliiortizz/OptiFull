// Pruebas de los hooks de datos de /api/reportes/* y de los gráficos (barras y franjas de congestión).
import { describe, test, expect } from 'vitest'
import { render, renderHook, screen, waitFor } from '@testing-library/react'
import { apiFalsa } from '../test/apiFalsa.js'
import {
  BarChart, CongestionHeatmap,
  useTendenciaSemanal, usePermanenciaSemanal, usePromedioDiario,
  useConversionCompra, usePermanenciaPorZona, useCongestionHoraria,
} from './ReportData'

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
  test('muestra etiquetas, valores y días con datos (singular/plural y "sin datos")', () => {
    const { container } = render(<BarChart data={[31, 28, 0]} labels={['Lun', 'Mar', 'Mié']} diasConDatos={[2, 1, 0]} />)
    for (const t of ['Lun', 'Mar', 'Mié', '31', '28', '2 días', '1 día', 'sin datos']) expect(screen.getByText(t)).toBeInTheDocument()
    // La barra sin datos se atenúa y no muestra su valor encima
    const barras = container.querySelectorAll('rect')
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

  test('el detalle de cada hora indica la franja, el promedio y los días; 23hs cierra en 00', () => {
    const { container } = render(<CongestionHeatmap data={data} />)
    const titulos = [...container.querySelectorAll('title')].map((t) => t.textContent)
    expect(titulos).toHaveLength(48)
    expect(titulos).toContain('Lun 09-10hs — 4 personas en promedio (1 día)')
    expect(titulos).toContain('Vie 12-13hs — 9 personas en promedio (3 días)')
    expect(titulos).toContain('Vie 23-00hs — 2 personas en promedio (3 días)')
    expect(titulos).toContain('Lun 00-01hs — sin datos')
  })

  test('una franja por día con su propio degradado, sin NaN aunque todo esté en cero', () => {
    const vacia = { dias: DIAS, horas, matriz: DIAS.map(() => fila(() => 0)), dias_con_datos: DIAS.map(() => fila(() => 0)) }
    const { container } = render(<CongestionHeatmap data={vacia} />)
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/)
    for (let i = 0; i < 7; i++) expect(container.querySelector(`#congDia${i}`)).not.toBeNull()
    expect(container.querySelectorAll(`rect[fill^="url(#congDia"]`)).toHaveLength(7)
  })
})

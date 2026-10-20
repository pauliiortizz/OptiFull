// Pruebas de las métricas históricas del Dashboard (tendencia semanal, congestión, conversión, KPIs).
import { Component } from 'react'
import { describe, test, expect, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { apiFalsa } from '../test/apiFalsa.js'
import { ReportMetrics } from './ReportMetrics'

const DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
const horas = Array.from({ length: 24 }, (_, h) => h)
const matriz = DIAS.map((_, i) => horas.map((h) => (i === 4 && (h === 12 || h === 13) ? 9 : i === 5 && h === 21 ? 7 : 0)))
const conDatos = DIAS.map((_, i) => horas.map((h) => (i === 4 && (h === 12 || h === 13) ? 2 : i === 5 && h === 21 ? 1 : 0)))

// Forma real de las respuestas de frontend/api/reportes.py
const reglas = (extra = {}) => ({
  '/api/reportes/tendencia-semanal': { labels: DIAS, promedio: [31, 28, 0, 40, 55, 72, 18], dias_con_datos: [2, 1, 0, 3, 3, 2, 1], fuente: 'db' },
  '/api/reportes/permanencia-semanal': { labels: DIAS, promedio: [6.4, 5.1, 0, 7.2, 8, 9.5, 4], dias_con_datos: [2, 1, 0, 3, 3, 2, 1], fuente: 'db' },
  '/api/reportes/promedio-diario': { promedio: 47, dias_con_datos: 12, fuente: 'db' },
  '/api/reportes/conversion-compra': { promedio_compraron: 18, promedio_no_compraron: 30, pct_conversion: 37.5, dias_con_datos: 12, fuente: 'db' },
  '/api/reportes/congestion-horaria': {
    dias: DIAS, horas, matriz, dias_con_datos: conDatos,
    pico: { dia: 'Vie', hora_inicio: 12, hora_fin: 13, promedio: 9 },
    picos: [{ dia: 'Vie', hora_inicio: 12, hora_fin: 13, promedio: 9 }, { dia: 'Sáb', hora_inicio: 21, hora_fin: 21, promedio: 7 }],
    fuente: 'db',
  },
  ...extra,
})

function renderMetricas(stats = { permanencia_maxima_min: 23 }) {
  return render(
    <ReportMetrics stats={stats}>
      {({ side, wide }) => (<><div data-testid="side">{side}</div><div data-testid="wide">{wide}</div></>)}
    </ReportMetrics>,
  )
}

// Atrapa errores de render para que el test pueda verificar que no hubo ninguno (sin errores no capturados).
class Atrapar extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  render() { return this.state.error ? <p>Se rompió: {this.state.error.message}</p> : this.props.children }
}

const listo = () => waitFor(() => expect(screen.queryByText(/Cargando/)).toBeNull())

describe('ReportMetrics', () => {
  test('pide los cinco endpoints de reportes al montarse', async () => {
    const api = apiFalsa(reglas())
    renderMetricas()
    await listo()
    expect(api.pedidos.map((p) => p.ruta).sort()).toEqual([
      '/api/reportes/congestion-horaria', '/api/reportes/conversion-compra', '/api/reportes/permanencia-semanal',
      '/api/reportes/promedio-diario', '/api/reportes/tendencia-semanal',
    ])
  })

  test('mientras carga muestra los textos de espera', () => {
    apiFalsa({ '/api/reportes': () => new Promise(() => {}) })
    renderMetricas(null)
    expect(screen.getByText('Cargando promedio histórico…')).toBeInTheDocument()
    expect(screen.getAllByText('Cargando…')).toHaveLength(2)
    // Sin stats la permanencia máxima queda con guion y el promedio diario como N/D
    expect(screen.getByText('—', { selector: '.kpi-card-value' })).toBeInTheDocument()
    expect(screen.getByText('N/D')).toBeInTheDocument()
    expect(screen.getByText('requiere múltiples sesiones')).toBeInTheDocument()
  })

  test('KPIs: permanencia máxima en minutos y promedio diario de personas únicas', async () => {
    apiFalsa(reglas())
    renderMetricas({ permanencia_maxima_min: 23 })
    await listo()
    const side = screen.getByTestId('side')
    const tarjetaPerm = within(side).getByText('Permanencia máxima').closest('.kpi-card')
    expect(within(tarjetaPerm).getByText('23')).toBeInTheDocument()
    expect(within(tarjetaPerm).getByText('min')).toBeInTheDocument()
    const tarjetaProm = within(side).getByText('Promedio diario').closest('.kpi-card')
    expect(within(tarjetaProm).getByText('47')).toBeInTheDocument()
    expect(within(tarjetaProm).getByText('únicas')).toBeInTheDocument()
    expect(within(tarjetaProm).getByText('12 días · todas las cámaras')).toBeInTheDocument()
  })

  test('promedio diario con un solo día usa singular', async () => {
    apiFalsa(reglas({ '/api/reportes/promedio-diario': { promedio: 20, dias_con_datos: 1, fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('1 día · todas las cámaras')
  })

  test('conversión de compra: porcentaje, promedios por día y días con datos', async () => {
    apiFalsa(reglas())
    renderMetricas()
    await listo()
    expect(screen.getByText('37.5%')).toBeInTheDocument()
    expect(screen.getByText('Promedio diario · 12 días con datos')).toBeInTheDocument()
    expect(screen.getByText('Compraron')).toBeInTheDocument()
    expect(screen.getByText('18 / día')).toBeInTheDocument()
    expect(screen.getByText('No compraron')).toBeInTheDocument()
    expect(screen.getByText('30 / día')).toBeInTheDocument()
  })

  test('conversión con un solo día usa singular', async () => {
    apiFalsa(reglas({ '/api/reportes/conversion-compra': { promedio_compraron: 0, promedio_no_compraron: 0, pct_conversion: null, dias_con_datos: 1, fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('Promedio diario · 1 día con datos')
    expect(screen.queryByText(/%$/)).toBeNull()
    expect(screen.getAllByText('0 / día')).toHaveLength(2)
  })

  test('conversión sin datos invita a analizar un video y no muestra barras', async () => {
    apiFalsa(reglas({ '/api/reportes/conversion-compra': { promedio_compraron: null, promedio_no_compraron: null, pct_conversion: null, dias_con_datos: 0, fuente: 'db' } }))
    renderMetricas()
    await screen.findByText(/Sin datos todavía -- analizá algún video/)
    expect(screen.queryByText('Compraron')).toBeNull()
  })

  test('tendencia semanal: flujo por defecto y al pasar a Espera muestra minutos de permanencia', async () => {
    const user = userEvent.setup()
    apiFalsa(reglas())
    renderMetricas()
    await listo()
    const wide = screen.getByTestId('wide')
    expect(within(wide).getByText('Promedio histórico por día de la semana · datos reales')).toBeInTheDocument()
    expect(within(wide).getByText('72')).toBeInTheDocument()
    expect(within(wide).getAllByText('sin datos')).toHaveLength(1)
    expect(within(wide).getAllByText('3 días')).toHaveLength(2)

    await user.click(within(wide).getByRole('button', { name: 'Espera' }))
    expect(within(wide).getByRole('button', { name: 'Espera' })).toHaveClass('on')
    expect(within(wide).getByText('Permanencia promedio (min) por día de la semana · datos reales')).toBeInTheDocument()
    expect(within(wide).getByText('9.5')).toBeInTheDocument()
    expect(within(wide).queryByText('72')).toBeNull()

    await user.click(within(wide).getByRole('button', { name: 'Flujo' }))
    expect(within(wide).getByText('72')).toBeInTheDocument()
  })

  test('congestión: pico más alto con franja horaria y cantidad de picos extra', async () => {
    apiFalsa(reglas())
    const { container } = renderMetricas()
    await screen.findByText('Pico más alto: Vie 12-14hs · 9 personas en promedio · +1 pico más (un mismo día puede tener varios)')
    expect(container.querySelectorAll('[id^="congDia"]')).toHaveLength(7)
  })

  test('congestión: pico único que termina a las 23 cierra en 00hs, sin texto de picos extra', async () => {
    const pico = { dia: 'Sáb', hora_inicio: 21, hora_fin: 23, promedio: 7 }
    apiFalsa(reglas({ '/api/reportes/congestion-horaria': { dias: DIAS, horas, matriz, dias_con_datos: conDatos, pico, picos: [pico], fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('Pico más alto: Sáb 21-00hs · 7 personas en promedio')
  })

  test('congestión: varios picos extra usan plural; hora de un dígito con cero adelante', async () => {
    const p = (dia, h) => ({ dia, hora_inicio: h, hora_fin: h, promedio: 5 })
    apiFalsa(reglas({ '/api/reportes/congestion-horaria': { dias: DIAS, horas, matriz, dias_con_datos: conDatos, pico: p('Lun', 8), picos: [p('Lun', 8), p('Mar', 9), p('Mié', 10)], fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('Pico más alto: Lun 08-09hs · 5 personas en promedio · +2 picos más (un mismo día puede tener varios)')
  })

  test('congestión sin base de datos (sin pico) muestra que faltan datos', async () => {
    apiFalsa(reglas({ '/api/reportes/congestion-horaria': { dias: DIAS, horas, matriz: DIAS.map(() => horas.map(() => 0)), dias_con_datos: DIAS.map(() => horas.map(() => 0)), fuente: 'sin_bd' } }))
    renderMetricas()
    await screen.findByText('Personas en cámara por franja horaria, día por día · sin datos suficientes todavía')
  })

  test('si la red falla en todos los endpoints quedan los valores por defecto sin romperse', async () => {
    apiFalsa({ '/api/reportes': new TypeError('Failed to fetch') })
    const { container } = renderMetricas()
    await listo()
    expect(screen.getByText('N/D')).toBeInTheDocument()
    expect(screen.getByText(/Sin datos todavía/)).toBeInTheDocument()
    expect(screen.getByText(/sin datos suficientes todavía/)).toBeInTheDocument()
    // Barras con los días por defecto, todas "sin datos"
    for (const d of DIAS) expect(within(screen.getByTestId('wide')).getByText(d)).toBeInTheDocument()
    expect(screen.getAllByText('sin datos')).toHaveLength(7)
    expect(container.querySelector('[id^="congDia"]')).toBeNull()
  })

  test('errores 500 en tendencia, permanencia, promedio y conversión no rompen el panel', async () => {
    const error = { status: 500, json: { error: 'relation "visitas" does not exist' } }
    apiFalsa(reglas({
      '/api/reportes/tendencia-semanal': error, '/api/reportes/permanencia-semanal': error,
      '/api/reportes/promedio-diario': error, '/api/reportes/conversion-compra': error,
    }))
    renderMetricas()
    await listo()
    expect(screen.getByText('N/D')).toBeInTheDocument()
    expect(screen.getByText(/Sin datos todavía/)).toBeInTheDocument()
    expect(screen.getAllByText('sin datos')).toHaveLength(7)
  })

  // DEFECTO: useCongestionHoraria guarda el cuerpo de error ({error: '...'}) como si fueran datos, y ReportMetrics
  // renderiza <CongestionHeatmap data={congestion}/> con él: `horas` es undefined y `horas.length` lanza TypeError.
  // Como App no tiene error boundary, un 500 de /api/reportes/congestion-horaria deja el Dashboard en blanco.
  test('un 500 de congestión-horaria muestra "sin datos" en vez de romper el Dashboard', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    apiFalsa(reglas({ '/api/reportes/congestion-horaria': { status: 500, json: { error: 'canceling statement due to statement timeout' } } }))
    render(
      <Atrapar>
        <ReportMetrics stats={null}>{({ side, wide }) => <>{side}{wide}</>}</ReportMetrics>
      </Atrapar>,
    )
    await waitFor(() => expect(screen.queryByText(/Cargando/)).toBeNull(), { timeout: 500 }).catch(() => {})
    expect(screen.queryByText(/Se rompió/)).toBeNull()
    await screen.findByText(/sin datos suficientes todavía/)
    expect(screen.getByText('Tendencia semanal')).toBeInTheDocument()
  })
})

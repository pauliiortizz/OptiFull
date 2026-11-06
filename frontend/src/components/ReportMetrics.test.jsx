// Pruebas de las métricas históricas del Dashboard (tendencia semanal, congestión, conversión, KPIs).
import { Component } from 'react'
import { describe, test, expect, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { apiFalsa } from '../test/apiFalsa.js'
import { conMovimientoReducido } from '../test/movimiento.js'
import { ReportMetrics } from './ReportMetrics'

conMovimientoReducido()

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

// Por defecto, el modo de 30 dias / Personalizado (barras por dia de la semana). El 20/10/2026 es martes:
// las barras van de miercoles a martes.
const RANGO = { desde: '2026-09-20', hasta: '2026-10-20' }

function renderMetricas(stats = { permanencia_maxima_min: 23, personas_validas: 5 }, props = {}) {
  return render(
    <ReportMetrics stats={stats} rango={RANGO} rangoTendencia={RANGO} diario={false} tick={0} {...props}>
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
    expect(screen.getAllByText('Cargando…')).toHaveLength(3)   // tendencia, conversion y congestion
    // Sin stats la permanencia máxima queda con guion, igual que el promedio diario mientras carga (sin pie)
    expect(screen.getAllByText('—', { selector: '.kpi-card-value' })).toHaveLength(2)
    expect(document.querySelector('.kpi-card-foot')).toBeNull()
  })

  test('KPIs: visita más larga en minutos y clientes por día en promedio, sin texto al pie', async () => {
    apiFalsa(reglas())
    renderMetricas({ permanencia_maxima_min: 23, personas_validas: 5 })
    await listo()
    const side = screen.getByTestId('side')
    const tarjetaPerm = within(side).getByText('Visita más larga').closest('.kpi-card')
    expect(within(tarjetaPerm).getByText('23')).toBeInTheDocument()
    expect(within(tarjetaPerm).getByText('min')).toBeInTheDocument()
    const tarjetaProm = within(side).getByText('Clientes por día').closest('.kpi-card')
    expect(await within(tarjetaProm).findByText('47')).toBeInTheDocument()   // la cifra llega un render después
    expect(within(tarjetaProm).getByText('prom.')).toBeInTheDocument()
    expect(side.querySelector('.kpi-card-foot')).toBeNull()   // ni "en el período" ni "N días con datos"
  })

  test('promedio diario sin datos en el período lo dice al pie', async () => {
    apiFalsa(reglas({ '/api/reportes/promedio-diario': { promedio: null, dias_con_datos: 0, fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('sin datos en este período')
  })

  test('conversión de compra: porcentaje y promedios por día, sin contar días con datos', async () => {
    apiFalsa(reglas())
    renderMetricas()
    await listo()
    expect(await screen.findByText('37,5%')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '37.5% de conversión' })).toBeInTheDocument()
    expect(screen.getByText('Pasaron por caja · promedio por día')).toBeInTheDocument()
    expect(screen.queryByText(/días con datos/)).toBeNull()
    expect(screen.getByText('Compraron')).toBeInTheDocument()
    expect(screen.getByText('18 / día')).toBeInTheDocument()
    expect(screen.getByText('No compraron')).toBeInTheDocument()
    expect(screen.getByText('30 / día')).toBeInTheDocument()
  })

  test('conversión con clientes en cero no inventa un 0 %', async () => {
    apiFalsa(reglas({ '/api/reportes/conversion-compra': { promedio_compraron: 0, promedio_no_compraron: 0, pct_conversion: null, dias_con_datos: 1, fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('Pasaron por caja · promedio por día')
    // DEF-021: sin porcentaje no se inventa un 0 %, el anillo muestra «—»
    expect(screen.queryByText(/%$/)).toBeNull()
    expect(screen.getByRole('img', { name: 'Conversión sin datos' })).toHaveTextContent('—')
    expect(screen.getAllByText('0 / día')).toHaveLength(2)
  })

  test('conversión sin datos en el período no muestra barras', async () => {
    apiFalsa(reglas({ '/api/reportes/conversion-compra': { promedio_compraron: null, promedio_no_compraron: null, pct_conversion: null, dias_con_datos: 0, fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('Sin visitas clasificadas como compra o tránsito en este período.')
    expect(screen.queryByText('Compraron')).toBeNull()
  })

  test('evolución: clientes por defecto y al pasar a Tiempo de visita muestra minutos', async () => {
    const user = userEvent.setup()
    apiFalsa(reglas())
    renderMetricas()
    await listo()
    const wide = screen.getByTestId('wide')
    expect(within(wide).getByText('Evolución por día de la semana')).toBeInTheDocument()
    expect(within(wide).getByText('Clientes por día · promedio por día de la semana · 20/09 – 20/10')).toBeInTheDocument()
    // La última barra es el día de la semana de la fecha final (martes 20/10), la primera el miércoles
    const etiquetas = [...wide.querySelectorAll('svg.gr-barras text[font-size="16"]')].map((t) => t.textContent).filter((t) => DIAS.includes(t))
    expect(etiquetas).toEqual(['Mié', 'Jue', 'Vie', 'Sáb', 'Dom', 'Lun', 'Mar'])
    expect(await within(wide).findByText('72')).toBeInTheDocument()   // los valores llegan un render después
    expect(within(wide).getAllByText('sin datos')).toHaveLength(1)
    expect(within(wide).queryByText(/\d+ días?$/)).toBeNull()   // sin "N días" bajo las barras

    await user.click(within(wide).getByRole('button', { name: 'Tiempo de visita' }))
    expect(within(wide).getByRole('button', { name: 'Tiempo de visita' })).toHaveClass('on')
    expect(within(wide).getByText('Tiempo promedio de visita (min) · promedio por día de la semana · 20/09 – 20/10')).toBeInTheDocument()
    expect(await within(wide).findByText('9,5')).toBeInTheDocument()   // decimales con coma (es-AR)
    expect(within(wide).queryByText('72')).toBeNull()

    await user.click(within(wide).getByRole('button', { name: 'Clientes' }))
    expect(await within(wide).findByText('72')).toBeInTheDocument()
  })

  test('congestión: pico más alto con franja horaria y cantidad de picos extra', async () => {
    apiFalsa(reglas())
    const { container } = renderMetricas()
    await screen.findByText('Pico más alto: Vie 12-14hs · 9 clientes en promedio · +1 pico más (un mismo día puede tener varios)')
    expect(container.querySelectorAll('rect.gr-celda')).toHaveLength(7 * 24)
    expect(container.querySelectorAll('rect.gr-pico')).toHaveLength(2)   // el pico más alto y el otro
  })

  test('congestión: pico único que termina a las 23 cierra en 00hs, sin texto de picos extra', async () => {
    const pico = { dia: 'Sáb', hora_inicio: 21, hora_fin: 23, promedio: 7 }
    apiFalsa(reglas({ '/api/reportes/congestion-horaria': { dias: DIAS, horas, matriz, dias_con_datos: conDatos, pico, picos: [pico], fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('Pico más alto: Sáb 21-00hs · 7 clientes en promedio')
  })

  test('congestión: varios picos extra usan plural; hora de un dígito con cero adelante', async () => {
    const p = (dia, h) => ({ dia, hora_inicio: h, hora_fin: h, promedio: 5 })
    apiFalsa(reglas({ '/api/reportes/congestion-horaria': { dias: DIAS, horas, matriz, dias_con_datos: conDatos, pico: p('Lun', 8), picos: [p('Lun', 8), p('Mar', 9), p('Mié', 10)], fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('Pico más alto: Lun 08-09hs · 5 clientes en promedio · +2 picos más (un mismo día puede tener varios)')
  })

  test('congestión sin base de datos avisa que no se pudo consultar', async () => {
    apiFalsa(reglas({ '/api/reportes/congestion-horaria': { dias: DIAS, horas, matriz: DIAS.map(() => horas.map(() => 0)), dias_con_datos: DIAS.map(() => horas.map(() => 0)), fuente: 'sin_bd' } }))
    renderMetricas()
    await screen.findByText('No se pudo consultar la base de datos · probá con Actualizar datos.')
  })

  test('congestión sin datos en el período lo dice', async () => {
    apiFalsa(reglas({ '/api/reportes/congestion-horaria': { dias: DIAS, horas, matriz: DIAS.map(() => horas.map(() => 0)), dias_con_datos: DIAS.map(() => horas.map(() => 0)), pico: null, picos: [], fuente: 'db' } }))
    renderMetricas()
    await screen.findByText('Clientes distintos vistos en cada hora · sin datos en este período')
  })

  test('congestión con 7 días: una fila por fecha, la última es hoy, con los picos de cada fecha', async () => {
    const semana = { desde: '2026-10-16', hasta: '2026-10-23' }
    const fila = (h, n) => horas.map((x) => (x === h ? n : 0))
    apiFalsa(reglas({
      '/api/reportes/congestion-horaria': { ...reglas()['/api/reportes/congestion-horaria'],
        por_fecha: [{ fecha: '2026-10-16', horas: fila(10, 4) }, { fecha: '2026-10-22', horas: fila(18, 11) }],
        picos_por_fecha: [{ dia: '2026-10-22', hora_inicio: 18, hora_fin: 18, promedio: 11 }, { dia: '2026-10-16', hora_inicio: 10, hora_fin: 10, promedio: 4 }] },
    }))
    const { container } = renderMetricas(undefined, { rango: semana, rangoTendencia: semana, diario: true })
    await screen.findByText('Pico más alto: Jue 22 18-19hs · 11 clientes · +1 pico más (un mismo día puede tener varios)')
    const cal = container.querySelector('svg.gr-calor')
    const filas = [...cal.querySelectorAll('text[font-size="16"]')].map((t) => t.textContent)
    expect(filas).toEqual(['Vie 16', 'Sáb 17', 'Dom 18', 'Lun 19', 'Mar 20', 'Mié 21', 'Jue 22', 'Vie 23'])
    expect(cal.querySelector('text[font-weight="700"]')).toHaveTextContent('Vie 23')
    expect(cal.querySelectorAll('rect.gr-celda')).toHaveLength(8 * 24)
    expect(cal.querySelectorAll('rect.gr-pico')).toHaveLength(2)
  })

  test('congestión con Hoy: solo la fila de hoy y las horas que todavía no pasaron se ven apagadas', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date(2026, 9, 23, 13, 30))   // viernes 23/10, 13:30
    try {
      const hoy = { desde: '2026-10-23', hasta: '2026-10-23' }
      apiFalsa(reglas({
        '/api/reportes/congestion-horaria': { ...reglas()['/api/reportes/congestion-horaria'],
          por_fecha: [{ fecha: '2026-10-23', horas: horas.map((h) => (h === 12 ? 6 : 0)) }],
          picos_por_fecha: [{ dia: '2026-10-23', hora_inicio: 12, hora_fin: 12, promedio: 6 }] },
      }))
      const { container } = renderMetricas(undefined, { rango: hoy, rangoTendencia: { desde: '2026-10-16', hasta: '2026-10-23' }, diario: true })
      await screen.findByText('Pico más alto: Vie 23 12-13hs · 6 clientes')
      const cal = container.querySelector('svg.gr-calor')
      expect([...cal.querySelectorAll('text[font-size="16"]')].map((t) => t.textContent)).toEqual(['Vie 23'])
      const celdas = cal.querySelectorAll('rect.gr-celda')
      expect(celdas).toHaveLength(24)
      expect(celdas[13]).toHaveAttribute('opacity', '1')      // 13 hs: ya empezó
      expect(celdas[14]).toHaveAttribute('opacity', '0.35')   // 14 hs: todavía no pasó
    } finally {
      vi.useRealTimers()
    }
  })

  test('congestión con 30 días: promedio por día de la semana, terminando en el día de la fecha final', async () => {
    apiFalsa(reglas())
    const { container } = renderMetricas()   // RANGO termina el martes 20/10
    await screen.findByText(/Pico más alto: Vie 12-14hs · 9 clientes en promedio/)
    const filas = [...container.querySelectorAll('svg.gr-calor text[font-size="16"]')].map((t) => t.textContent)
    expect(filas).toEqual(['Mié', 'Jue', 'Vie', 'Sáb', 'Dom', 'Lun', 'Mar'])
  })

  test('todos los reportes se piden con el rango del filtro y se vuelven a pedir con "Actualizar datos"', async () => {
    const api = apiFalsa(reglas())
    const { rerender } = renderMetricas()
    await listo()
    for (const p of api.pedidos) expect(p.query).toEqual(RANGO)
    const antes = api.pedidos.length
    rerender(
      <ReportMetrics stats={null} rango={RANGO} rangoTendencia={RANGO} diario={false} tick={1}>
        {({ side, wide }) => (<><div data-testid="side">{side}</div><div data-testid="wide">{wide}</div></>)}
      </ReportMetrics>,
    )
    await waitFor(() => expect(api.pedidos.length).toBe(antes + 5))
  })

  test('con Hoy / 7 días la tendencia muestra una barra por fecha, del viernes anterior al viernes actual', async () => {
    const semana = { desde: '2026-10-16', hasta: '2026-10-23' }   // viernes 16 a viernes 23
    apiFalsa(reglas({
      '/api/reportes/tendencia-semanal': { ...reglas()['/api/reportes/tendencia-semanal'],
        por_fecha: [{ fecha: '2026-10-16', valor: 11 }, { fecha: '2026-10-20', valor: 64 }, { fecha: '2026-10-23', valor: 37 }] },
    }))
    renderMetricas(undefined, { rango: { desde: '2026-10-23', hasta: '2026-10-23' }, rangoTendencia: semana, diario: true })
    await listo()
    const wide = screen.getByTestId('wide')
    expect(within(wide).getByText('Clientes por día · 16/10 – 23/10')).toBeInTheDocument()
    expect(await within(wide).findByText('64')).toBeInTheDocument()
    const etiquetas = [...wide.querySelectorAll('svg.gr-barras text[font-size="16"]')].map((t) => t.textContent).filter((t) => /^\S+ \d+$/.test(t))
    expect(etiquetas).toEqual(['Vie 16', 'Sáb 17', 'Dom 18', 'Lun 19', 'Mar 20', 'Mié 21', 'Jue 22', 'Vie 23'])
    expect(within(wide).getAllByText('sin datos')).toHaveLength(5)   // 8 fechas, 3 con datos
    expect(wide.querySelector('svg.gr-barras text[font-weight="700"]')).toHaveTextContent('Vie 23')   // hoy, la última barra
  })

  test('si la red falla en todos los endpoints quedan los valores por defecto sin romperse', async () => {
    apiFalsa({ '/api/reportes': new TypeError('Failed to fetch') })
    const { container } = renderMetricas()
    await listo()
    expect(screen.getByText('no se pudo consultar')).toBeInTheDocument()   // promedio diario
    expect(screen.getAllByText(/No se pudo consultar la base de datos/)).toHaveLength(3)   // conversion, tendencia, congestion
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
    expect(screen.getByText('no se pudo consultar')).toBeInTheDocument()
    expect(screen.getAllByText(/No se pudo consultar la base de datos/)).toHaveLength(2)   // conversion y tendencia
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
        <ReportMetrics stats={null} rango={RANGO} rangoTendencia={RANGO} diario={false} tick={0}>{({ side, wide }) => <>{side}{wide}</>}</ReportMetrics>
      </Atrapar>,
    )
    await waitFor(() => expect(screen.queryByText(/Cargando/)).toBeNull(), { timeout: 500 }).catch(() => {})
    expect(screen.queryByText(/Se rompió/)).toBeNull()
    await screen.findAllByText(/No se pudo consultar la base de datos/)
    expect(screen.getByText('Evolución por día de la semana')).toBeInTheDocument()
  })
})

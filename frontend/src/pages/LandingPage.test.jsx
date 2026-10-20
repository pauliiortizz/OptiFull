// Pruebas de la landing publica: entrada de clientes, pedido de demo (POST /api/leads), panel de
// demostracion con datos reales (/api/stats y /api/heatmap/camara/4) y su rotacion automatica.
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { apiFalsa } from '../test/apiFalsa.js'
import { LandingPage } from './LandingPage.jsx'

// Respuesta real de /api/stats (ver api/stats.py: calcular_stats)
const STATS = {
  personas_totales: 140, personas_unicas: 128, personas_validas: 120,
  permanencia_promedio_min: 6.4, permanencia_maxima_min: 40, permanencia_minima_valida_min: 0.5,
  distribucion: [{ rango: '0-2 min', count: 30 }, { rango: '2-5 min', count: 60 }, { rango: '5+ min', count: 30 }],
  fuente: 'db', tiempo_real_disponible: false, rango: { desde: null, hasta: null },
}
const HEAT = { imagen_url: '/heatmaps/camara_4.png' }

let api
beforeEach(() => {
  api = apiFalsa({
    'GET /api/stats': STATS,
    'GET /api/heatmap/camara/4': HEAT,
    'POST /api/leads': { status: 201, json: { ok: true } },
  })
})
afterEach(() => {
  delete window.clarity
  delete window.gtag
  window.history.replaceState(null, '', '/')
})

const panel = () => screen.getByRole('tabpanel')
const pestania = (nombre) => screen.getByRole('tab', { name: nombre })

// Completa los campos obligatorios del formulario de demo.
async function completar(user, { problema = 'Colas en caja' } = {}) {
  await user.type(screen.getByLabelText('Nombre y apellido'), 'Laura Gómez')
  await user.selectOptions(screen.getByLabelText('Tu rol'), 'Gerente de tienda')
  await user.type(screen.getByLabelText('Estación y localidad'), 'YPF Full Av. Colón, Córdoba')
  await user.selectOptions(screen.getByLabelText('¿Cuántas cámaras tiene la tienda?'), '4 a 8')
  await user.type(screen.getByLabelText('WhatsApp o email'), 'laura@ejemplo.com')
  if (problema) await user.click(screen.getByLabelText(problema))
}
describe('LandingPage: navegación', () => {
  test('muestra la propuesta y el enlace de clientes lleva al sistema', async () => {
    const user = userEvent.setup()
    const onEnter = vi.fn()
    render(<LandingPage onEnter={onEnter} />)
    expect(screen.getByRole('heading', { level: 1, name: 'Tus cámaras en acción, nuestra solución.' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ya soy cliente' }))
    expect(onEnter).toHaveBeenCalledTimes(1)
  })

  test('sin onEnter el enlace de clientes no rompe la página', async () => {
    const user = userEvent.setup()
    render(<LandingPage />)
    await user.click(screen.getByRole('button', { name: 'Ya soy cliente' }))
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })

  test('los botones de demo llevan al formulario, enfocan el primer campo y registran el clic', async () => {
    const user = userEvent.setup()
    window.clarity = vi.fn()
    window.gtag = vi.fn()
    const scroll = vi.spyOn(window.HTMLElement.prototype, 'scrollIntoView')
    render(<LandingPage />)
    const botones = [
      screen.getAllByRole('button', { name: 'Pedir demo' })[0],
      screen.getByRole('button', { name: /Quiero una demo en mi tienda/ }),
    ]
    for (const b of botones) {
      scroll.mockClear()
      await user.click(b)
      expect(scroll).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
      expect(screen.getByLabelText('Nombre y apellido')).toHaveFocus()
    }
    expect(window.clarity).toHaveBeenCalledWith('event', 'cta_demo')
    expect(window.gtag).toHaveBeenCalledWith('event', 'cta_demo')
  })

  test('con "reducir movimiento" el salto al formulario es inmediato', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'matchMedia').mockImplementation((q) => ({
      matches: q.includes('reduced-motion'), media: q, addEventListener() {}, removeEventListener() {},
    }))
    const scroll = vi.spyOn(window.HTMLElement.prototype, 'scrollIntoView')
    render(<LandingPage />)
    await user.click(screen.getByRole('button', { name: /Quiero una demo/ }))
    expect(scroll).toHaveBeenCalledWith({ behavior: 'auto', block: 'start' })
  })

  test('si la medición (Clarity / GA) falla, el botón igual funciona', async () => {
    const user = userEvent.setup()
    window.clarity = () => { throw new Error('clarity') }
    window.gtag = () => { throw new Error('ga') }
    render(<LandingPage />)
    await user.click(screen.getByRole('button', { name: /Quiero una demo/ }))
    expect(screen.getByLabelText('Nombre y apellido')).toHaveFocus()
  })
})

describe('LandingPage: panel de demostración con datos reales', () => {
  test('pide las métricas y el mapa de calor al cargar', async () => {
    render(<LandingPage />)
    expect(await screen.findByText('Ya funcionando en una YPF Full de Córdoba')).toBeInTheDocument()
    expect(api.hechos('/api/stats')).toHaveLength(1)
    expect(api.hechos('/api/heatmap/camara/4')).toHaveLength(1)
  })

  test('arranca en la detección y muestra cada vista al elegir su pestaña', async () => {
    const user = userEvent.setup()
    render(<LandingPage />)
    await screen.findByText('Ya funcionando en una YPF Full de Córdoba')
    expect(pestania('Detección')).toHaveAttribute('aria-selected', 'true')
    expect(within(panel()).getByRole('img', { name: /dos personas detectadas/ })).toBeInTheDocument()

    await user.click(pestania('Mapa de calor'))
    expect(pestania('Mapa de calor')).toHaveAttribute('aria-selected', 'true')
    expect(within(panel()).getByRole('img', { name: /Mapa de calor de la zona de cajas/ })).toHaveAttribute('src', HEAT.imagen_url)
    expect(screen.getByText(/Mapa de calor real de la zona de cajas sobre un croquis/)).toBeInTheDocument()

    await user.click(pestania('Métricas'))
    expect(within(panel()).getByText('128')).toBeInTheDocument()
    expect(within(panel()).getByText('6.4 min')).toBeInTheDocument()
    const barras = within(panel()).getByRole('list', { name: 'Distribución de la permanencia' })
    expect(within(barras).getAllByRole('listitem')).toHaveLength(3)
    expect(within(barras).getByText('2-5 min').nextSibling).toHaveStyle({ width: '100%' })
  })

  test('sin datos (o con el pedido caído) avisa que todavía no están disponibles', async () => {
    const user = userEvent.setup()
    api.reglas['GET /api/stats'] = new Error('sin red')
    api.reglas['GET /api/heatmap/camara/4'] = null   // la API responde null si no hay mapa
    render(<LandingPage />)
    await waitFor(() => expect(api.pedidos).toHaveLength(2))
    await user.click(pestania('Mapa de calor'))
    expect(screen.getByText('El mapa de calor todavía no está disponible.')).toBeInTheDocument()
    await user.click(pestania('Métricas'))
    expect(screen.getByText('Las métricas todavía no están disponibles.')).toBeInTheDocument()
    expect(screen.queryByText('Ya funcionando en una YPF Full de Córdoba')).not.toBeInTheDocument()
  })

  test('las métricas sin distribución muestran solo los totales', async () => {
    const user = userEvent.setup()
    api.reglas['GET /api/stats'] = { personas_unicas: 5, permanencia_promedio_min: 2 }
    render(<LandingPage />)
    await screen.findByText('Ya funcionando en una YPF Full de Córdoba')
    await user.click(pestania('Métricas'))
    expect(within(panel()).getByText('2 min')).toBeInTheDocument()
    expect(within(panel()).queryByRole('list')).not.toBeInTheDocument()
  })

  // DEFECTO: LandingPage.jsx:67 no revisa r.ok; si /api/stats responde 500 {error} (BD y CSV caidos),
  // el cuerpo de error se toma como metricas: aparece "Ya funcionando..." y la pestaña Metricas muestra
  // KPIs vacios (" min") en vez de "Las métricas todavía no están disponibles."
  test.fails('si /api/stats responde con error no muestra métricas vacías', async () => {
    const user = userEvent.setup()
    api.reglas['GET /api/stats'] = { status: 500, json: { error: 'sin datos' } }
    render(<LandingPage />)
    await waitFor(() => expect(api.hechos('/api/stats')).toHaveLength(1))
    await user.click(pestania('Métricas'))
    expect(screen.getByText('Las métricas todavía no están disponibles.')).toBeInTheDocument()
  })

  test('actualiza las métricas cada 30 s y deja de pedir al salir de la página', async () => {
    vi.useFakeTimers()
    const { unmount } = render(<LandingPage />)
    await act(async () => {})
    expect(api.hechos('/api/stats')).toHaveLength(1)
    await act(async () => { vi.advanceTimersByTime(30000) })
    expect(api.hechos('/api/stats')).toHaveLength(2)
    expect(api.hechos('/api/heatmap/camara/4')).toHaveLength(2)
    unmount()
    await act(async () => { vi.advanceTimersByTime(60000) })
    expect(api.hechos('/api/stats')).toHaveLength(2)
  })

  test('las vistas rotan solas cada 6 s y paran al elegir una a mano', async () => {
    vi.useFakeTimers()
    render(<LandingPage />)
    await act(async () => {})
    expect(pestania('Detección')).toHaveAttribute('aria-selected', 'true')
    act(() => { vi.advanceTimersByTime(6000) })
    expect(pestania('Mapa de calor')).toHaveAttribute('aria-selected', 'true')
    act(() => { vi.advanceTimersByTime(6000) })
    expect(pestania('Métricas')).toHaveAttribute('aria-selected', 'true')
    act(() => { vi.advanceTimersByTime(6000) })
    expect(pestania('Detección')).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(pestania('Métricas'))
    act(() => { vi.advanceTimersByTime(30000) })
    expect(pestania('Métricas')).toHaveAttribute('aria-selected', 'true')
  })

  test('la rotación se pausa con el cursor o el foco sobre el panel', async () => {
    vi.useFakeTimers()
    render(<LandingPage />)
    await act(async () => {})
    const aside = screen.getByRole('complementary', { name: 'Demostración del sistema' })
    fireEvent.mouseEnter(aside)
    act(() => { vi.advanceTimersByTime(12000) })
    expect(pestania('Detección')).toHaveAttribute('aria-selected', 'true')
    fireEvent.mouseLeave(aside)
    act(() => { vi.advanceTimersByTime(6000) })
    expect(pestania('Mapa de calor')).toHaveAttribute('aria-selected', 'true')
    fireEvent.focus(pestania('Mapa de calor'))
    act(() => { vi.advanceTimersByTime(12000) })
    expect(pestania('Mapa de calor')).toHaveAttribute('aria-selected', 'true')
    fireEvent.blur(pestania('Mapa de calor'))
    act(() => { vi.advanceTimersByTime(6000) })
    expect(pestania('Métricas')).toHaveAttribute('aria-selected', 'true')
  })

  test('con "reducir movimiento" las vistas no rotan', async () => {
    vi.useFakeTimers()
    vi.spyOn(window, 'matchMedia').mockImplementation((q) => ({
      matches: q.includes('reduced-motion'), media: q, addEventListener() {}, removeEventListener() {},
    }))
    render(<LandingPage />)
    await act(async () => {})
    act(() => { vi.advanceTimersByTime(20000) })
    expect(pestania('Detección')).toHaveAttribute('aria-selected', 'true')
  })
})

describe('LandingPage: pedido de demo', () => {
  const botonEnviar = () => within(document.querySelector('form.landing-form')).getByRole('button')

  test('envía el pedido con los datos del formulario y los utm del link, y confirma', async () => {
    const user = userEvent.setup()
    window.gtag = vi.fn()
    window.history.replaceState(null, '', '/?utm_source=instagram&utm_campaign=piloto')
    render(<LandingPage />)
    await completar(user, { problema: 'Faltantes de stock' })
    await user.click(botonEnviar())
    expect(await screen.findByRole('status')).toHaveTextContent('Recibimos tu pedido')
    const [pedido] = api.hechos('/api/leads', 'POST')
    expect(pedido.cuerpo).toEqual({
      nombre: 'Laura Gómez', rol: 'Gerente de tienda', contacto: 'laura@ejemplo.com',
      estacion: 'YPF Full Av. Colón, Córdoba', camaras: '4 a 8', problema: 'faltantes',
      utm_source: 'instagram', utm_medium: '', utm_campaign: 'piloto', utm_content: '',
    })
    expect(window.gtag).toHaveBeenCalledWith('event', 'demo_enviada')
    // el formulario desaparece una vez enviado
    expect(document.querySelector('form.landing-form')).toBeNull()
  })

  test('la opción elegida queda marcada', async () => {
    const user = userEvent.setup()
    render(<LandingPage />)
    await user.click(screen.getByLabelText('Horarios pico y turnos'))
    expect(screen.getByLabelText('Horarios pico y turnos')).toBeChecked()
    expect(screen.getByLabelText('Horarios pico y turnos').closest('label')).toHaveClass('on')
  })

  test('con campos obligatorios vacíos no se envía nada', async () => {
    const user = userEvent.setup()
    render(<LandingPage />)
    await user.click(screen.getByLabelText('Colas en caja'))
    await user.click(botonEnviar())
    expect(screen.getByLabelText('Nombre y apellido')).toBeInvalid()
    expect(api.hechos('/api/leads')).toHaveLength(0)
  })

  test('sin elegir qué resolver pide elegirlo y no envía nada', async () => {
    const user = userEvent.setup()
    render(<LandingPage />)
    await completar(user, { problema: null })
    await user.click(botonEnviar())
    expect(screen.getByRole('alert')).toHaveTextContent('Elegí qué te gustaría resolver primero.')
    expect(api.hechos('/api/leads')).toHaveLength(0)
  })

  // DEFECTO: LandingPage.jsx:341-343 el texto del error depende de 'problema' y no del motivo del error.
  // Si se envia sin elegir que resolver y despues se elige una opcion, el aviso pasa a decir
  // "No se pudo enviar. Probá de nuevo en un momento." aunque no se intento ningun envio.
  test.fails('al elegir la opción que faltaba no aparece un falso error de envío', async () => {
    const user = userEvent.setup()
    render(<LandingPage />)
    await completar(user, { problema: null })
    await user.click(botonEnviar())
    await user.click(screen.getByLabelText('Colas en caja'))
    expect(screen.queryByText('No se pudo enviar. Probá de nuevo en un momento.')).not.toBeInTheDocument()
  })

  test('mientras envía deshabilita el botón para no duplicar el pedido', async () => {
    const user = userEvent.setup()
    let responder
    api.reglas['POST /api/leads'] = () => new Promise((r) => { responder = r })
    render(<LandingPage />)
    await completar(user)
    await user.click(botonEnviar())
    expect(botonEnviar()).toBeDisabled()
    expect(botonEnviar()).toHaveTextContent('Enviando…')
    await act(async () => { responder({ status: 201, json: { ok: true } }) })
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(api.hechos('/api/leads')).toHaveLength(1)
  })

  test('si el servidor rechaza el pedido avisa y permite reintentar', async () => {
    const user = userEvent.setup()
    window.gtag = vi.fn()
    api.reglas['POST /api/leads'] = { status: 400, json: { ok: false, faltan: ['contacto'] } }
    render(<LandingPage />)
    await completar(user)
    await user.click(botonEnviar())
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo enviar. Probá de nuevo en un momento.')
    expect(window.gtag).not.toHaveBeenCalledWith('event', 'demo_enviada')
    expect(botonEnviar()).toBeEnabled()
    // reintento exitoso
    api.reglas['POST /api/leads'] = { status: 201, json: { ok: true } }
    await user.click(botonEnviar())
    expect(await screen.findByRole('status')).toBeInTheDocument()
    expect(api.hechos('/api/leads')).toHaveLength(2)
  })

  test('sin conexión avisa que no se pudo enviar', async () => {
    const user = userEvent.setup()
    api.reglas['POST /api/leads'] = new TypeError('Failed to fetch')
    render(<LandingPage />)
    await completar(user)
    await user.click(botonEnviar())
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo enviar')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

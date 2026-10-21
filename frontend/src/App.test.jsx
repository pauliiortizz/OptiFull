// App completa: ruteo landing / login / panel, sesion (restaurar, vencer, cerrar), permisos por rol y el
// dashboard con datos falsos de la API.
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App.jsx'
import { vigilarSesion } from './components/useSesion.js'
import { apiFalsa } from './test/apiFalsa.js'

const CLAVE = 'optifull-sesion'
const ADMIN = { ok: true, usuario: 'ana', nombre: 'Ana Pérez', rol: 'administrador', cargo: 'dueno' }
const EMPLEADO = { ok: true, usuario: 'juan', nombre: 'Juan Gómez', rol: 'usuario', cargo: 'empleado' }

const AHORA = new Date(2026, 9, 20, 12, 0, 0).getTime()
const ALERTAS = [
  { id: 1, title: 'Posible hurto en góndola 3', status: 'open', sev: 'critical', ts: AHORA - 30_000 },
  { id: 2, title: 'Ocultamiento en caja', status: 'open', sev: 'warning', ts: AHORA - 300_000, foto: '/foto.jpg' },
  { id: 3, title: 'Alerta resuelta', status: 'resolved', sev: 'critical', ts: AHORA },
]

// Respuestas por defecto de todos los endpoints que pide el panel.
function reglasBase() {
  return {
    'GET /api/sesion': { ok: true },
    'POST /api/logout': { ok: true },
    '/api/health': { db: 'ok' },
    '/api/en-tienda': { total: 7, en_vivo: true },
    '/api/alertas': ALERTAS,
    '/api/stats': { personas_validas: 42, permanencia_promedio_min: 6.3, permanencia_maxima_min: 25 },
    '/api/heatmap/plano/tiempo': { zonas: {}, rango: { desde: 480, hasta: 1320 } },
    '/api/heatmap/plano/flujo': { zonas: {} },
    '/api/heatmap/plano': { zonas: { gondola: { intensidad: 0.8, share_pct: 60, camaras: [4] } } },
    '/api/heatmap/camara': { zonas: {} },
    '/api/reportes/permanencia-por-zona': { zonas: [
      { tipo: 'caja', nombre: 'Caja', permanencia_promedio_min: 2.5, pct: 30, visitantes: 10 },
      { tipo: 'gondola', nombre: 'Góndolas', permanencia_promedio_min: 4.25, pct: 60, visitantes: 20 },
      { tipo: 'pasillo', nombre: 'Pasillo X', permanencia_promedio_min: 1, pct: 10, visitantes: 3 },
    ] },
    '/api/reportes/congestion-horaria': {
      dias: ['Lun', 'Mar'], horas: [8, 9, 10], matriz: [[1, 2, 3], [0, 4, 1]], dias_con_datos: [1, 1],
      pico: { hora_inicio: 9, hora_fin: 10, promedio: 3.5, dia: 'Martes' },
      picos: [{ hora_inicio: 9, hora_fin: 10, promedio: 3.5, dia: 'Martes' }],
    },
    '/api/reportes/tendencia-semanal': { labels: ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'], promedio: [1, 2, 3, 4, 5, 6, 7], dias_con_datos: [1, 1, 1, 1, 1, 1, 1] },
    '/api/reportes/permanencia-semanal': { promedio: [1, 1, 1, 1, 1, 1, 1], dias_con_datos: [1, 1, 1, 1, 1, 1, 1] },
    '/api/reportes/promedio-diario': { promedio: 12, dias_con_datos: 3 },
    '/api/reportes/conversion-compra': { dias_con_datos: 2, pct_conversion: 40 },
    '/api/reportes/opciones': { metricas: [], camaras: [], formatos: [{ id: 'pdf', nombre: 'PDF' }], fecha_min: '2026-10-01', fecha_max: '2026-10-20' },
    '/api/productos': {},
    '/api/sessions': [],
    '/api/videos': [],
  }
}

// Abre la app en 'ruta' con la sesion dada guardada (o ninguna) y fetch vigilado como en main.jsx.
function abrir(ruta = '/dashboard', { sesion = ADMIN, mantener = true, reglas = {} } = {}) {
  if (sesion) (mantener ? localStorage : sessionStorage).setItem(CLAVE, JSON.stringify(sesion))
  window.history.replaceState(null, '', ruta)
  const api = apiFalsa({ ...reglasBase(), ...reglas })
  delete window.__optifullVigilaSesion
  vigilarSesion()
  const vista = render(<App />)
  return { api, ...vista }
}

const tile = (etiqueta) => screen.getByText(etiqueta).closest('.stat-tile')
const pedidosA = (api, ruta) => api.pedidos.filter((p) => p.ruta === ruta)
const enPanel = () => screen.findByRole('navigation', { name: 'Ruta de navegación' })
const crumb = () => within(screen.getByRole('navigation', { name: 'Ruta de navegación' })).getByText((_, el) => el.classList.contains('crumb-static'))

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(AHORA)   // martes 20/10/2026, 12:00 hora local
})
afterEach(() => {
  delete window.__optifullVigilaSesion
  window.history.replaceState(null, '', '/')
})

describe('ruteo y sesion', () => {
  test('"/" muestra la landing; "Ya soy cliente" sin sesion lleva al login', async () => {
    abrir('/', { sesion: null })
    await userEvent.click(screen.getByRole('button', { name: 'Ya soy cliente' }))
    expect(await screen.findByRole('heading', { name: 'Iniciá sesión' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/login')
  })

  test('"Ya soy cliente" con sesion guardada va directo al panel', async () => {
    abrir('/', { sesion: ADMIN })
    await userEvent.click(screen.getByRole('button', { name: 'Ya soy cliente' }))
    await enPanel()
    expect(window.location.pathname).toBe('/dashboard')
  })

  test('sin sesion, "/dashboard" muestra el login y no valida nada contra el servidor', async () => {
    const { api } = abrir('/dashboard', { sesion: null })
    expect(screen.getByRole('heading', { name: 'Iniciá sesión' })).toBeInTheDocument()
    expect(pedidosA(api, '/api/sesion')).toHaveLength(0)
  })

  test('restaura la sesion guardada (localStorage) y la valida con GET /api/sesion', async () => {
    const { api } = abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    expect(screen.getByText('Ana Pérez')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Operaciones' })).toBeInTheDocument()
    await waitFor(() => expect(pedidosA(api, '/api/sesion')).toHaveLength(1))
    expect(pedidosA(api, '/api/sesion')[0].metodo).toBe('GET')
  })

  test('tambien restaura una sesion de sessionStorage (sin "mantener")', async () => {
    abrir('/dashboard', { sesion: EMPLEADO, mantener: false })
    await enPanel()
    expect(screen.getByText('Juan Gómez')).toBeInTheDocument()
  })

  test('una sesion del modo demo viejo (sin rol) se descarta y pide login', () => {
    abrir('/dashboard', { sesion: { usuario: 'demo' } })
    expect(screen.getByRole('heading', { name: 'Iniciá sesión' })).toBeInTheDocument()
    expect(localStorage.getItem(CLAVE)).toBeNull()
  })

  test('si el servidor dice que la sesion vencio (401) vuelve al login y borra lo guardado', async () => {
    abrir('/dashboard', { sesion: ADMIN, reglas: { 'GET /api/sesion': { status: 401, json: { error: 'vencida' } } } })
    expect(await screen.findByRole('heading', { name: 'Iniciá sesión' })).toBeInTheDocument()
    expect(localStorage.getItem(CLAVE)).toBeNull()
  })

  test('un 401 en cualquier otro pedido de la API tambien cierra la sesion', async () => {
    abrir('/dashboard', { sesion: ADMIN, reglas: { '/api/en-tienda': { status: 401, json: {} } } })
    expect(await screen.findByRole('heading', { name: 'Iniciá sesión' })).toBeInTheDocument()
    expect(localStorage.getItem(CLAVE)).toBeNull()
  })

  test('si /api/sesion no responde (sin red) la sesion guardada sigue', async () => {
    abrir('/dashboard', { sesion: ADMIN, reglas: { 'GET /api/sesion': new TypeError('sin red') } })
    await enPanel()
    await act(() => vi.advanceTimersByTimeAsync(10))
    expect(screen.getByText('Ana Pérez')).toBeInTheDocument()
  })

  test('cerrar sesion llama a POST /api/logout, borra la sesion y vuelve a la landing', async () => {
    const { api } = abrir('/dashboard', { sesion: ADMIN })
    sessionStorage.setItem(CLAVE, JSON.stringify(ADMIN))
    await enPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(api.hechos('/api/logout', 'POST')).toHaveLength(1)
    expect(localStorage.getItem(CLAVE)).toBeNull()
    expect(sessionStorage.getItem(CLAVE)).toBeNull()
    expect(window.location.pathname).toBe('/')
    expect(await screen.findByRole('button', { name: 'Ya soy cliente' })).toBeInTheDocument()
  })

  test('si POST /api/logout falla igual se sale', async () => {
    abrir('/dashboard', { sesion: ADMIN, reglas: { 'POST /api/logout': new TypeError('sin red') } })
    await enPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(await screen.findByRole('button', { name: 'Ya soy cliente' })).toBeInTheDocument()
  })

  test('el boton atras del navegador (popstate) cambia entre landing y panel', async () => {
    abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    act(() => {
      window.history.pushState(null, '', '/')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(screen.getByRole('button', { name: 'Ya soy cliente' })).toBeInTheDocument()
    act(() => {
      window.history.pushState(null, '', '/dashboard')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    await enPanel()
  })

  test('iniciar sesion desde la app lleva al panel en la seccion del rol', async () => {
    const { api } = abrir('/login', { sesion: null, reglas: { 'POST /api/login': EMPLEADO } })
    await userEvent.type(screen.getByLabelText('Email o usuario'), 'juan')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'clave')
    await userEvent.click(screen.getByRole('button', { name: 'Ingresar' }))
    await enPanel()
    expect(window.location.pathname).toBe('/dashboard')
    expect(crumb()).toHaveTextContent('Productos')
    expect(api.hechos('/api/login', 'POST')[0].cuerpo).toEqual({ usuario: 'juan', clave: 'clave', mantener: true })
    expect(JSON.parse(localStorage.getItem(CLAVE))).toMatchObject({ usuario: 'juan', rol: 'usuario' })
  })

  test('desde el login, "Volver al inicio" lleva a la landing', async () => {
    abrir('/login', { sesion: null })
    await userEvent.click(screen.getByRole('button', { name: '← Volver al inicio' }))
    expect(window.location.pathname).toBe('/')
    expect(screen.getByRole('button', { name: 'Ya soy cliente' })).toBeInTheDocument()
  })

  test('"Pedí una demo" vuelve a la landing y baja hasta el formulario de demo', async () => {
    const bajar = vi.spyOn(window.HTMLElement.prototype, 'scrollIntoView')
    abrir('/login', { sesion: null })
    await userEvent.click(screen.getByRole('button', { name: 'Pedí una demo' }))
    expect(window.location.pathname).toBe('/')
    await act(() => vi.advanceTimersByTimeAsync(100))
    expect(bajar).toHaveBeenCalled()
    expect(bajar.mock.contexts[0].id).toBe('demo')
  })

  test('con View Transitions la navegacion pasa por la transicion', async () => {
    document.startViewTransition = vi.fn((f) => f())
    try {
      abrir('/login', { sesion: null })
      await userEvent.click(screen.getByRole('button', { name: '← Volver al inicio' }))
      expect(document.startViewTransition).toHaveBeenCalled()
      expect(screen.getByRole('button', { name: 'Ya soy cliente' })).toBeInTheDocument()
    } finally {
      delete document.startViewTransition
    }
  })
})

describe('permisos por rol', () => {
  test('el empleado arranca en Productos y no puede llegar al dashboard', async () => {
    const { api } = abrir('/dashboard', { sesion: EMPLEADO })
    await enPanel()
    expect(crumb()).toHaveTextContent('Productos')
    expect(screen.queryByRole('heading', { name: 'Operaciones' })).not.toBeInTheDocument()
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
    // El inicio de la ruta de navegacion apunta al dashboard: para el empleado no cambia nada.
    await userEvent.click(screen.getByRole('button', { name: 'OptiFull' }))
    expect(crumb()).toHaveTextContent('Productos')
    expect(pedidosA(api, '/api/stats')).toHaveLength(0)
  })

  test('el empleado puede ir a Alertas', async () => {
    abrir('/dashboard', { sesion: EMPLEADO })
    await enPanel()
    await userEvent.click(screen.getByText('Alertas', { selector: '.side-nav-label' }))
    expect(crumb()).toHaveTextContent('Alertas')
  })

  test('el administrador navega por todas las secciones desde el menu', async () => {
    abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    expect(crumb()).toHaveTextContent('Operativo')
    for (const [item, miga] of [['Productos', 'Productos'], ['Reportes', 'Reportes'], ['Alertas', 'Alertas'], ['Config', 'Configuración'], ['Dashboard', 'Operativo']]) {
      await userEvent.click(screen.getByText(item, { selector: '.side-nav-label' }))
      expect(crumb(), item).toHaveTextContent(miga)
    }
  })
})

describe('barra superior', () => {
  test('el estado de sincronizacion refleja /api/health', async () => {
    abrir('/dashboard', { sesion: ADMIN, reglas: { '/api/health': { db: 'error' } } })
    await enPanel()
    expect(await screen.findByText('Reconectando…')).toBeInTheDocument()
  })

  test('sincronizado cuando la base responde, y se vuelve a consultar cada 30 s', async () => {
    const { api } = abrir('/dashboard', { sesion: ADMIN })
    expect(await screen.findByText('Sincronizado')).toBeInTheDocument()
    const antes = pedidosA(api, '/api/health').length
    await act(() => vi.advanceTimersByTimeAsync(30_000))
    expect(pedidosA(api, '/api/health').length).toBeGreaterThan(antes)
  })

  test('sin red el estado pasa a reconectando', async () => {
    abrir('/dashboard', { sesion: ADMIN, reglas: { '/api/health': new TypeError('sin red') } })
    expect(await screen.findByText('Reconectando…')).toBeInTheDocument()
  })

  test('las notificaciones listan solo alertas abiertas y llevan a la seccion Alertas', async () => {
    abrir('/dashboard', { sesion: ADMIN })
    const campana = await screen.findByRole('button', { name: 'Notificaciones: 2 alertas pendientes' })
    await userEvent.click(campana)
    expect(campana).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Posible hurto en góndola 3')).toBeInTheDocument()
    expect(screen.getByText(/^hace 3\ds$/)).toBeInTheDocument()
    expect(screen.getByText('hace 5m')).toBeInTheDocument()
    expect(screen.queryByText('Alerta resuelta')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ver todas las alertas →' }))
    expect(crumb()).toHaveTextContent('Alertas')
    expect(screen.queryByText('Ver todas las alertas →')).not.toBeInTheDocument()
  })

  test('tocar una notificacion tambien lleva a Alertas, y clic afuera cierra el menu', async () => {
    abrir('/dashboard', { sesion: ADMIN })
    const campana = await screen.findByRole('button', { name: /Notificaciones: 2/ })
    await userEvent.click(campana)
    fireEvent.mouseDown(document.body)
    expect(campana).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(campana)
    await userEvent.click(screen.getByText('Ocultamiento en caja'))
    expect(crumb()).toHaveTextContent('Alertas')
  })

  test('sin alertas abiertas la campana lo dice', async () => {
    abrir('/dashboard', { sesion: ADMIN, reglas: { '/api/alertas': [] } })
    await enPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Notificaciones' }))
    expect(screen.getByText('Sin alertas pendientes')).toBeInTheDocument()
  })

  test('el boton de tema alterna dia y noche', async () => {
    abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    const antes = document.documentElement.dataset.theme
    const boton = screen.getByRole('button', { name: antes === 'dark' ? 'Cambiar a modo día' : 'Cambiar a modo noche' })
    await userEvent.click(boton)
    await act(() => vi.advanceTimersByTimeAsync(500))
    expect(document.documentElement.dataset.theme).toBe(antes === 'dark' ? 'light' : 'dark')
    expect(localStorage.getItem('optifull-theme')).toBe(document.documentElement.dataset.theme)
  })

  test('el menu del celular se abre con la hamburguesa y se cierra con Escape o tocando afuera', async () => {
    const { container } = abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    const aside = container.querySelector('aside')
    await userEvent.click(screen.getByRole('button', { name: 'Abrir menú' }))
    expect(aside).toHaveClass('mobile-open')
    await userEvent.keyboard('{Escape}')
    expect(aside).not.toHaveClass('mobile-open')
    await userEvent.click(screen.getByRole('button', { name: 'Abrir menú' }))
    await userEvent.click(container.querySelector('.side-backdrop'))
    expect(aside).not.toHaveClass('mobile-open')
  })

  test('el reloj avanza cada segundo', async () => {
    const { container } = abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    const reloj = container.querySelector('.clock .mono')
    const antes = reloj.textContent
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(reloj.textContent).not.toBe(antes)
    expect(screen.getByText(/© 2026 OptiFull/)).toBeInTheDocument()
  })

  test('el panel de ajustes cambia el acento y los demas ajustes', async () => {
    const { container } = abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    const estilo = document.documentElement.style
    expect(estilo.getPropertyValue('--brand')).toBe('#4f68e5')
    expect(estilo.getPropertyValue('--brand-soft')).toBe('rgb(125, 150, 255)')
    act(() => { window.dispatchEvent(new MessageEvent('message', { data: { type: '__activate_edit_mode' } })) })
    const chips = container.querySelectorAll('.twk-chip')
    expect(chips).toHaveLength(4)
    await userEvent.click(chips[1])
    expect(estilo.getPropertyValue('--brand')).toBe('#fa98d1')
    expect(chips[1]).toHaveAttribute('aria-checked', 'true')
    for (const sw of screen.getAllByRole('switch')) {
      await userEvent.click(sw)
      expect(sw).toHaveAttribute('aria-checked', 'false')
    }
    fireEvent.change(container.querySelector('.twk-slider'), { target: { value: '0.6' } })
    expect(container.querySelector('.twk-slider')).toHaveValue('0.6')
    // Densidad: segmento "compact" (el control mide su ancho real, en jsdom se simula).
    vi.spyOn(window.HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 104, height: 20 })
    fireEvent.pointerDown(container.querySelector('.twk-seg'), { clientX: 10 })
    fireEvent.pointerUp(window)
    expect(screen.getByRole('radio', { name: 'compact' })).toHaveAttribute('aria-checked', 'true')
  })
})

describe('dashboard', () => {
  test('muestra los KPI con los datos de la API', async () => {
    abrir('/dashboard', { sesion: ADMIN })
    await waitFor(() => expect(tile('Personas en tienda')).toHaveTextContent('7'))
    expect(tile('Personas en tienda')).toHaveTextContent('en vivo · cámaras')
    await waitFor(() => expect(tile('Permanencia')).toHaveTextContent('6.3'))
    expect(tile('Permanencia')).toHaveTextContent('máx 25 min · 42 personas')
    await waitFor(() => expect(tile('Alertas activas')).toHaveTextContent('2'))
    expect(tile('Alertas activas')).toHaveTextContent('1 críticas')
    await waitFor(() => expect(tile('Hora pico')).toHaveTextContent('09–11'))
    expect(tile('Hora pico')).toHaveTextContent('3.5 pers. simult.')
    expect(tile('Hora pico')).toHaveTextContent('Martes')
    expect(screen.getByText(/Cámaras en vivo · análisis en curso · Hoy · 20\/10\/2026/)).toBeInTheDocument()
  })

  test('las zonas se ordenan por permanencia y suman los visitantes', async () => {
    const { container } = abrir('/dashboard', { sesion: ADMIN })
    await waitFor(() => expect(container.querySelectorAll('.roi-row')).toHaveLength(3))
    const filas = [...container.querySelectorAll('.roi-label')].map((e) => e.textContent)
    expect(filas).toEqual(['Góndolas Centrales', 'Línea de Cajas', 'Pasillo X'])
    expect(screen.getByText('4.3m')).toBeInTheDocument()
    expect(screen.getByText(/33 visitantes distintos/)).toBeInTheDocument()
  })

  test('sin datos muestra guiones y avisos en vez de numeros', async () => {
    abrir('/dashboard', { sesion: ADMIN, reglas: {
      '/api/en-tienda': { total: 0, en_vivo: false },
      '/api/stats': { personas_validas: 0 },
      '/api/reportes/permanencia-por-zona': { zonas: [] },
      '/api/reportes/congestion-horaria': { dias: [], horas: [8], matriz: [], dias_con_datos: [], pico: null, picos: [] },
      '/api/alertas': [{ ...ALERTAS[1] }],
    } })
    await waitFor(() => expect(tile('Permanencia')).toHaveTextContent('sin datos en este período'))
    expect(tile('Personas en tienda')).toHaveTextContent('—')
    expect(tile('Personas en tienda')).toHaveTextContent('sin cámara en vivo')
    expect(tile('Alertas activas')).toHaveTextContent('estable')
    await waitFor(() => expect(tile('Hora pico')).toHaveTextContent('sin datos en este período'))
    expect(await screen.findByText('Sin datos de permanencia en este período.')).toBeInTheDocument()
    expect(screen.getByText(/Sin análisis en vivo · mostrando datos guardados/)).toBeInTheDocument()
  })

  test('si fallan los pedidos el dashboard no se rompe', async () => {
    const sinRed = new TypeError('sin red')
    abrir('/dashboard', { sesion: ADMIN, reglas: {
      '/api/en-tienda': sinRed, '/api/stats': sinRed, '/api/heatmap/plano': sinRed, '/api/heatmap/plano/tiempo': sinRed,
      '/api/heatmap/plano/flujo': sinRed, '/api/reportes/permanencia-por-zona': sinRed,
      '/api/reportes/congestion-horaria': sinRed, '/api/alertas': sinRed,
    } })
    await waitFor(() => expect(screen.getByRole('button', { name: /Actualizar datos/ })).toBeEnabled())
    expect(tile('Permanencia')).toHaveTextContent('cargando…')
    expect(tile('Personas en tienda')).toHaveTextContent('—')
  })

  test('arranca en "Hoy" y manda ?desde=&hasta= con la fecha de hoy', async () => {
    const { api } = abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    await waitFor(() => expect(pedidosA(api, '/api/stats')).toHaveLength(1))
    for (const ruta of ['/api/stats', '/api/reportes/permanencia-por-zona']) {
      expect(pedidosA(api, ruta).at(-1).query).toEqual({ desde: '2026-10-20', hasta: '2026-10-20' })
    }
    // La hora pico tambien pide con rango (la otra consulta, sin query, es la del mapa de congestion).
    expect(pedidosA(api, '/api/reportes/congestion-horaria').some((p) => p.query.desde === '2026-10-20')).toBe(true)
  })

  test.each([
    ['7 días', { desde: '2026-10-14', hasta: '2026-10-20' }, 'Últimos 7 días · 14/10/2026 – 20/10/2026'],
    ['30 días', { desde: '2026-09-21', hasta: '2026-10-20' }, 'Últimos 30 días · 21/09/2026 – 20/10/2026'],
  ])('el filtro "%s" pide el rango correcto', async (boton, rango, etiqueta) => {
    const { api } = abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    await userEvent.click(screen.getByRole('button', { name: boton }))
    expect(screen.getByRole('button', { name: boton })).toHaveClass('on')
    await waitFor(() => expect(pedidosA(api, '/api/stats').at(-1).query).toEqual(rango))
    expect(pedidosA(api, '/api/reportes/permanencia-por-zona').at(-1).query).toEqual(rango)
    expect(pedidosA(api, '/api/reportes/congestion-horaria').at(-1).query).toEqual(rango)
    expect(screen.getByText(new RegExp(etiqueta))).toBeInTheDocument()
  })

  test('el filtro personalizado arranca en los ultimos 7 dias y usa las fechas elegidas', async () => {
    const { api } = abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Personalizado' }))
    const desde = screen.getByLabelText('Desde'), hasta = screen.getByLabelText('Hasta')
    expect(desde).toHaveValue('2026-10-14')
    expect(hasta).toHaveValue('2026-10-20')
    expect(hasta).toHaveAttribute('max', '2026-10-20')
    await waitFor(() => expect(pedidosA(api, '/api/stats').at(-1).query).toEqual({ desde: '2026-10-14', hasta: '2026-10-20' }))
    fireEvent.change(desde, { target: { value: '2026-10-01' } })
    fireEvent.change(hasta, { target: { value: '2026-10-05' } })
    await waitFor(() => expect(pedidosA(api, '/api/stats').at(-1).query).toEqual({ desde: '2026-10-01', hasta: '2026-10-05' }))
    expect(screen.getByText(/01\/10\/2026 – 05\/10\/2026/)).toBeInTheDocument()
    // Borrar una fecha no deja el rango vacio.
    fireEvent.change(desde, { target: { value: '' } })
    expect(desde).toHaveValue('2026-10-01')
    // Un solo dia muestra una sola fecha.
    fireEvent.change(hasta, { target: { value: '2026-10-01' } })
    expect(await screen.findByText(/· 01\/10\/2026$/)).toBeInTheDocument()
  })

  test('"Actualizar datos" vuelve a pedir todo y refresca el croquis', async () => {
    const { api } = abrir('/dashboard', { sesion: ADMIN })
    const boton = await screen.findByRole('button', { name: /Actualizar datos/ })
    await waitFor(() => expect(boton).toBeEnabled())
    const antes = pedidosA(api, '/api/stats').length
    await userEvent.click(boton)
    await waitFor(() => expect(pedidosA(api, '/api/stats').length).toBe(antes + 1))
    expect(pedidosA(api, '/api/heatmap/plano/tiempo').at(-1).query).toEqual({ refrescar: '1' })
    expect(pedidosA(api, '/api/heatmap/plano/flujo').at(-1).query).toEqual({ refrescar: '1' })
  })

  test('mientras carga el boton dice "Actualizando…" y queda deshabilitado', async () => {
    let soltar
    abrir('/dashboard', { sesion: ADMIN, reglas: { '/api/stats': () => new Promise((r) => { soltar = r }) } })
    expect(await screen.findByRole('button', { name: /Actualizando…/ })).toBeDisabled()
    soltar({ json: { personas_validas: 1, permanencia_promedio_min: 1, permanencia_maxima_min: 1 } })
    await waitFor(() => expect(screen.getByRole('button', { name: /Actualizar datos/ })).toBeEnabled())
  })

  test('las personas en tienda se actualizan cada 5 s', async () => {
    let total = 3
    const { api } = abrir('/dashboard', { sesion: ADMIN, reglas: { '/api/en-tienda': () => ({ json: { total: total++, en_vivo: true } }) } })
    await waitFor(() => expect(tile('Personas en tienda')).toHaveTextContent('3'))
    await act(() => vi.advanceTimersByTimeAsync(5000))
    await waitFor(() => expect(tile('Personas en tienda')).toHaveTextContent('4'))
    expect(pedidosA(api, '/api/en-tienda').length).toBeGreaterThanOrEqual(2)
  })

  test('el calor del croquis se vuelve a pedir cada minuto', async () => {
    const { api } = abrir('/dashboard', { sesion: ADMIN })
    await waitFor(() => expect(pedidosA(api, '/api/heatmap/plano')).toHaveLength(1))
    await act(() => vi.advanceTimersByTimeAsync(60_000))
    expect(pedidosA(api, '/api/heatmap/plano').length).toBeGreaterThanOrEqual(2)
  })

  test('el reproductor del croquis arranca en la hora actual, avanza y se detiene al final', async () => {
    const { container } = abrir('/dashboard', { sesion: ADMIN })
    const hora = () => container.querySelector('.plan-scrub-time').textContent
    await waitFor(() => expect(container.querySelector('.plan-scrub-range')).toHaveTextContent('08:00–22:00'))
    expect(hora()).toBe('12:00')
    await userEvent.click(screen.getByTitle('Reproducir'))
    await act(() => vi.advanceTimersByTimeAsync(900))
    expect(hora()).toBe('12:05')
    await userEvent.click(screen.getByTitle('Pausar'))
    // Se lleva el control al final y al reproducir llega a 22:00 y se pausa sola.
    fireEvent.change(container.querySelector('.plan-scrub-track input'), { target: { value: '1310' } })
    expect(hora()).toBe('21:50')
    await userEvent.click(screen.getByTitle('Reproducir'))
    await act(() => vi.advanceTimersByTimeAsync(2000))
    expect(hora()).toBe('22:00')
    expect(screen.getByTitle('Reproducir')).toBeInTheDocument()
    // Play desde el final vuelve a empezar.
    await userEvent.click(screen.getByTitle('Reproducir'))
    expect(hora()).toBe('08:00')
  })

  test('las capas, la opacidad, el filtro de zona y el modo acumulado responden', async () => {
    const { container } = abrir('/dashboard', { sesion: ADMIN })
    await enPanel()
    for (const capa of ['Trayectorias', 'Zonas', 'Calor']) {
      await userEvent.click(screen.getByRole('button', { name: capa }))
      expect(screen.getByRole('button', { name: capa })).toHaveClass('on')
    }
    fireEvent.change(container.querySelector('.plan-opacity input'), { target: { value: '45' } })
    expect(container.querySelector('.plan-opacity')).toHaveTextContent('45%')
    const seg = container.querySelector('.plan-scrubber .seg')
    await userEvent.click(within(seg).getByRole('button', { name: 'Caja' }))
    expect(within(seg).getByRole('button', { name: 'Caja' })).toHaveClass('on')
    await userEvent.click(screen.getByRole('button', { name: 'Acumulado hasta esa hora' }))
    expect(screen.getByRole('button', { name: 'Acumulado hasta esa hora' })).toHaveClass('on')
    await userEvent.click(screen.getByRole('button', { name: 'Últimos 30 min' }))
    expect(screen.getByRole('button', { name: 'Últimos 30 min' })).toHaveClass('on')
  })

  // DEFECTO: si /api/reportes/congestion-horaria responde un error JSON (p. ej. 500 {error}), ReportData guarda ese
  // objeto como datos (ReportData.jsx:89, sin mirar r.ok) y CongestionHeatmap lee horas.length de undefined
  // (ReportData.jsx:181). No hay error boundary en App.jsx, asi que todo el panel queda en blanco.
  test('un error 500 de congestion-horaria no deja el panel en blanco', async () => {
    const errores = []
    const alError = (e) => { errores.push(e.error); e.preventDefault() }
    window.addEventListener('error', alError)
    vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      abrir('/dashboard', { sesion: ADMIN, reglas: { '/api/reportes/congestion-horaria': { status: 500, json: { error: 'db caida' } } } })
      await enPanel()
      await act(() => vi.advanceTimersByTimeAsync(50))
      expect(errores).toEqual([])
      expect(screen.getByRole('heading', { name: 'Operaciones' })).toBeInTheDocument()
    } finally {
      window.removeEventListener('error', alError)
    }
  })
})

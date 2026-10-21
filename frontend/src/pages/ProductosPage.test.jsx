// Pruebas de la caja web (ProductosPage): encender/apagar el detector, las decisiones que se le piden a la cajera
// (confirmar / elegir / manual), el ticket y la confirmación de la venta. La API es falsa (ver src/test/apiFalsa.js)
// y respeta los contratos de frontend/api/productos.py.
import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { apiFalsa } from '../test/apiFalsa'
import { ToastProvider } from '../components/Toast'
import { ProductosPage } from './ProductosPage'

const URL_CELU_DEFAULT = 'http://admin:admin@192.168.0.10:8081/video'
// Mismo formato que la página; Testing Library normaliza el espacio duro del texto, así que acá también.
const pesos = (v) => Number(v).toLocaleString('es-AR', { style: 'currency', currency: 'ARS' }).replace(/\s/g, ' ')

const CATALOGO = [
  { sku: 'SKU001', nombre: 'Gaseosa', marca: 'Coca-Cola', variante: 'Zero', tamano_valor: 500, tamano_unidad: 'ml', categoria: 'Bebidas', cantidad: 20, precio: 1500 },
  { sku: 'SKU002', nombre: 'Galletitas', marca: 'Oreo', variante: null, tamano_valor: null, tamano_unidad: null, categoria: 'Almacén', cantidad: 3, precio: '800.50' },
  { sku: 'SKU003', nombre: 'Yerba', marca: 'Playadito', variante: null, tamano_valor: 1, tamano_unidad: 'kg', categoria: null, cantidad: 0, precio: 4200 },
]
const META = { confianza_llm: 0.91, estado_matching: 'reconocido', datos_llm: { marca: 'Coca-Cola', confianza: 0.91 } }
const PEND_CONFIRMAR = { tipo: 'confirmar', producto: CATALOGO[0], confianza: 0.874, meta: META }
const PEND_ELEGIR = {
  tipo: 'elegir',
  candidatos: [CATALOGO[0], CATALOGO[1], CATALOGO[2]],
  datos_llm: { marca: '?' },
  meta: { confianza_llm: 0.55, estado_matching: 'confirmar', datos_llm: { marca: '?' } },
}
const PEND_MANUAL = { tipo: 'manual', meta: { confianza_llm: 0.7, estado_matching: 'no_reconocido', datos_llm: null } }

const METRICAS = {
  total_transacciones: 12,
  confianza_promedio: 0.873,
  por_estado_matching: [{ estado_matching: 'reconocido', cantidad: 5 }, { estado_matching: 'confirmar', cantidad: 3 }],
  productos_con_mas_problemas: [],
}

// Estado que devuelve GET /api/productos/estado (lo que main.py dejó en caja_estado). Cada test lo cambia.
let estadoCaja

function montar(reglas = {}) {
  const api = apiFalsa({
    'GET /api/productos/estado': () => estadoCaja,
    'GET /api/videos': ['prueba.mp4', 'caja 2.mp4'],
    'GET /api/productos/stock': { productos: CATALOGO },
    'GET /api/productos/metricas': METRICAS,
    'POST /api/productos/iniciar': (req) => ({ json: { ok: true, pid: 4321, source: req.cuerpo.source, log: 'caja.log' } }),
    'POST /api/productos/detener': { ok: true, aviso: 'se va a detener en el proximo punto seguro (hasta ~1-2s)' },
    'POST /api/productos/accion': { ok: true },
    'POST /api/productos/venta': { ok: true, stock: {} },
    ...reglas,
  })
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
  const vista = render(<ToastProvider><ProductosPage /></ToastProvider>)
  return { api, user, ...vista }
}

// Deja correr el polling (250 ms entre consultas) y las promesas pendientes.
const avanzar = (ms = 300) => act(() => vi.advanceTimersByTimeAsync(ms))
const panelDecision = () => screen.getByText('Producto detectado').closest('.panel')
const panelTicket = () => screen.getByText('Ticket de la venta').closest('.panel')
const toasts = () => document.querySelector('.toast-stack')
const accionesEnviadas = (api) => api.hechos('/api/productos/accion', 'POST').map((p) => p.cuerpo)

// Monta la página con el detector ya corriendo y la decisión indicada pendiente.
async function conDecision(pendiente, reglas) {
  estadoCaja = { corriendo: true, estado: pendiente ? 'esperando_decision' : 'inactivo', pendiente }
  const r = montar(reglas)
  await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
  await avanzar()
  return r
}

const tileValor = (etiqueta) => screen.getByText(etiqueta).closest('.stat-tile')

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  estadoCaja = { corriendo: false, estado: 'inactivo', pendiente: null }
})

describe('encender y apagar la cámara', () => {
  test('arranca apagada, con la cámara del celular como fuente y la URL por defecto', async () => {
    const { api } = montar()
    const sw = screen.getByRole('switch')
    expect(sw).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText('Cámara apagada')).toBeInTheDocument()
    expect(screen.getByDisplayValue(URL_CELU_DEFAULT)).toBeInTheDocument()
    expect(screen.getByText('Encendé la cámara para empezar a recibir productos.')).toBeInTheDocument()
    // Los videos de la carpeta quedan como alternativa en el selector de fuente.
    await waitFor(() => expect(screen.getByRole('option', { name: 'prueba.mp4' })).toBeInTheDocument())
    expect(screen.getByRole('combobox')).toHaveValue('__celular__')
    // Mientras está apagada no se consulta el estado en loop: solo la consulta inicial.
    await avanzar(2000)
    expect(api.hechos('/api/productos/estado')).toHaveLength(1)
  })

  test('encender con el celular manda la URL escrita, la recuerda y muestra el video en vivo', async () => {
    const { api, user } = montar()
    const input = screen.getByDisplayValue(URL_CELU_DEFAULT)
    await user.clear(input)
    await user.type(input, '  http://yo:clave@192.168.1.50:8081/video  ')
    await user.click(screen.getByRole('switch'))

    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    const [pedido] = api.hechos('/api/productos/iniciar', 'POST')
    expect(pedido.cuerpo).toEqual({ source: 'http://yo:clave@192.168.1.50:8081/video' })
    expect(window.localStorage.getItem('optifull.urlCelu')).toBe('http://yo:clave@192.168.1.50:8081/video')
    expect(within(toasts()).getByText('Cámara encendida · fuente: celular')).toBeInTheDocument()
    expect(screen.getByText('Cámara encendida')).toBeInTheDocument()

    const img = screen.getByRole('img', { name: 'Cámara del celular en vivo' })
    expect(img).toHaveAttribute('src', `/api/productos/camara?url=${encodeURIComponent('http://yo:clave@192.168.1.50:8081/video')}`)
    expect(screen.getByText(/En vivo desde el celular/)).toBeInTheDocument()
    // Ya no se puede cambiar la fuente con la cámara encendida.
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  test('la URL del celular recordada se usa al volver a abrir la página', () => {
    window.localStorage.setItem('optifull.urlCelu', 'http://192.168.0.99:8080/video')
    montar()
    expect(screen.getByDisplayValue('http://192.168.0.99:8080/video')).toBeInTheDocument()
  })

  test('encender con un video grabado manda la ruta ../videos/ y lo reproduce', async () => {
    const { api, user } = montar()
    await waitFor(() => expect(screen.getByRole('option', { name: 'caja 2.mp4' })).toBeInTheDocument())
    await user.selectOptions(screen.getByRole('combobox'), 'caja 2.mp4')
    // Con un video elegido no se pide la URL del celular.
    expect(screen.queryByDisplayValue(URL_CELU_DEFAULT)).not.toBeInTheDocument()
    await user.click(screen.getByRole('switch'))

    await waitFor(() => expect(within(toasts()).getByText('Cámara encendida · fuente: ../videos/caja 2.mp4')).toBeInTheDocument())
    expect(api.hechos('/api/productos/iniciar', 'POST')[0].cuerpo).toEqual({ source: '../videos/caja 2.mp4' })
    const video = document.querySelector('.pv-video-frame video')
    expect(video).toHaveAttribute('src', '/api/video/caja%202.mp4')
    expect(screen.getByText(/Grabación de referencia/)).toBeInTheDocument()
    expect(tileValor('Estado cámara')).toHaveTextContent('fuente: caja 2.mp4')
  })

  test('mientras arranca muestra "Iniciando" y cuando el detector corre pasa a "PROCESANDO"', async () => {
    const { user } = montar()
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(screen.getByText('INICIANDO…')).toBeInTheDocument())
    expect(screen.getByText('Iniciando la detección…')).toBeInTheDocument()
    expect(tileValor('Estado cámara')).toHaveTextContent('Iniciando')

    estadoCaja = { corriendo: true, estado: 'inactivo', pendiente: null }
    await avanzar()
    expect(screen.getByText('PROCESANDO')).toBeInTheDocument()
    expect(screen.getByText('Esperando que aparezca un producto…')).toBeInTheDocument()
    expect(tileValor('Estado cámara')).toHaveTextContent('Encendida')
  })

  test('si al abrir la página el detector ya estaba corriendo, el interruptor aparece encendido', async () => {
    estadoCaja = { corriendo: true, estado: 'inactivo', pendiente: null }
    montar()
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
  })

  test('si el servidor responde 409 (ya estaba corriendo), se muestra encendida sin error', async () => {
    const { user } = montar({ 'POST /api/productos/iniciar': { status: 409, json: { error: 'la caja ya esta corriendo' } } })
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(within(toasts()).getByText('La cámara ya estaba encendida.')).toBeInTheDocument())
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })

  test('si se reenciende enseguida de apagar y el detector todavía se está deteniendo, se pide esperar', async () => {
    estadoCaja = { corriendo: true, estado: 'inactivo', pendiente: null }
    const { user } = montar({ 'POST /api/productos/iniciar': { status: 409, json: { error: 'la caja ya esta corriendo' } } })
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false'))
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(within(toasts()).getByText(/se está deteniendo: esperá unos segundos/)).toBeInTheDocument())
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })

  test('si no se puede iniciar, avisa el motivo y queda apagada', async () => {
    const { user } = montar({ 'POST /api/productos/iniciar': { status: 400, json: { error: "no existe la camara 'Camara Caja'" } } })
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(within(toasts()).getByText("No se pudo encender la cámara: no existe la camara 'Camara Caja'")).toBeInTheDocument())
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('switch')).toBeEnabled()
  })

  test('un error 500 sin mensaje usa el texto genérico; un fallo de red también se informa', async () => {
    let regla = { status: 500, json: {} }
    const { user } = montar({ 'POST /api/productos/iniciar': () => regla })
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(within(toasts()).getByText('No se pudo encender la cámara: no se pudo iniciar')).toBeInTheDocument())

    regla = new TypeError('Failed to fetch')
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(within(toasts()).getByText('No se pudo encender la cámara: Failed to fetch')).toBeInTheDocument())
  })

  test('apagar pide detener y muestra el aviso del servidor', async () => {
    estadoCaja = { corriendo: true, estado: 'inactivo', pendiente: null }
    const { api, user } = montar()
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(within(toasts()).getByText('se va a detener en el proximo punto seguro (hasta ~1-2s)')).toBeInTheDocument())
    expect(api.hechos('/api/productos/detener', 'POST')).toHaveLength(1)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText('Encendé la cámara para empezar a recibir productos.')).toBeInTheDocument()

    // Apagada deja de consultar el estado.
    const antes = api.hechos('/api/productos/estado').length
    await avanzar(2000)
    expect(api.hechos('/api/productos/estado')).toHaveLength(antes)
  })

  test('apagar sin aviso del servidor muestra "Cámara apagada"; si falla, avisa el error', async () => {
    estadoCaja = { corriendo: true, estado: 'inactivo', pendiente: null }
    let regla = { ok: true }
    const { user } = montar({ 'POST /api/productos/detener': () => regla })
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(within(toasts()).getByText('Cámara apagada')).toBeInTheDocument())

    regla = { status: 503, json: { error: 'sin conexion a la base de datos' } }
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(within(toasts()).getByText('Error al apagar: sin conexion a la base de datos')).toBeInTheDocument())

    regla = { status: 500, json: {} }
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    await user.click(screen.getByRole('switch'))
    await waitFor(() => expect(within(toasts()).getByText('Error al apagar: no se pudo detener')).toBeInTheDocument())
  })
})

describe('estado del detector', () => {
  test('sin base de datos (503) muestra el error en lugar de la decisión, y se recupera solo', async () => {
    estadoCaja = { corriendo: true, estado: 'inactivo', pendiente: null }
    let caida = false
    montar({ 'GET /api/productos/estado': () => (caida ? { status: 503, json: { error: 'sin conexion a la base de datos' } } : estadoCaja) })
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    caida = true
    await avanzar(600)
    expect(within(panelDecision()).getByText('sin conexion a la base de datos')).toBeInTheDocument()

    caida = false
    await avanzar(600)
    expect(within(panelDecision()).queryByText('sin conexion a la base de datos')).not.toBeInTheDocument()
    expect(screen.getByText('Esperando que aparezca un producto…')).toBeInTheDocument()
  })

  test('si el servidor no responde, muestra el error de red y sigue reintentando', async () => {
    estadoCaja = { corriendo: true, estado: 'inactivo', pendiente: null }
    let caida = false
    const { api } = montar({ 'GET /api/productos/estado': () => (caida ? new TypeError('Failed to fetch') : estadoCaja) })
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    caida = true
    await avanzar(600)
    expect(within(panelDecision()).getByText('TypeError: Failed to fetch')).toBeInTheDocument()
    const antes = api.hechos('/api/productos/estado').length
    await avanzar(1000)
    expect(api.hechos('/api/productos/estado').length).toBeGreaterThan(antes)
  })

  test('el polling espera a que vuelva cada consulta antes de pedir la siguiente (no se encima)', async () => {
    estadoCaja = { corriendo: true, estado: 'inactivo', pendiente: null }
    let resolver
    let lento = false
    const { api } = montar({
      'GET /api/productos/estado': () => (lento ? new Promise((r) => { resolver = () => r(estadoCaja) }) : estadoCaja),
    })
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'))
    lento = true
    await avanzar(300)
    const enCurso = api.hechos('/api/productos/estado').length
    await avanzar(3000)
    expect(api.hechos('/api/productos/estado')).toHaveLength(enCurso)
    lento = false
    await act(async () => { resolver() })
    await avanzar(300)
    expect(api.hechos('/api/productos/estado').length).toBeGreaterThan(enCurso)
  })
})

describe('decisión "confirmar" (producto reconocido)', () => {
  test('muestra el producto, su SKU, categoría y la confianza del modelo', async () => {
    await conDecision(PEND_CONFIRMAR)
    const panel = within(panelDecision())
    expect(panel.getByText('Coca-Cola Gaseosa Zero · 500ml')).toBeInTheDocument()
    expect(panel.getByText('SKU SKU001 · Bebidas')).toBeInTheDocument()
    expect(panel.getByText('Confianza del modelo: 87%')).toBeInTheDocument()
    expect(panel.getByRole('spinbutton')).toHaveValue(1)
  })

  test('un producto sin categoría ni confianza lo indica', async () => {
    await conDecision({ tipo: 'confirmar', producto: { sku: 'SKU999' } })
    const panel = within(panelDecision())
    expect(panel.getByText('SKU999', { selector: '.pv-product-name' })).toBeInTheDocument()
    expect(panel.getByText('SKU SKU999 · sin categoría')).toBeInTheDocument()
    expect(panel.getByText('Confianza del modelo: 0%')).toBeInTheDocument()
  })

  test('Confirmar manda la cantidad elegida, lo suma al ticket y oculta la decisión al instante', async () => {
    const { api, user } = await conDecision(PEND_CONFIRMAR)
    const panel = within(panelDecision())
    await user.click(panel.getByRole('button', { name: '+' }))
    await user.click(panel.getByRole('button', { name: '+' }))
    await user.click(panel.getByRole('button', { name: '+' }))
    await user.click(panel.getByRole('button', { name: '–' }))
    expect(panel.getByRole('spinbutton')).toHaveValue(3)

    await user.click(panel.getByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(accionesEnviadas(api)).toEqual([{ accion: 'confirmar', cantidad: 3 }]))
    expect(within(toasts()).getByText('Agregado al ticket: 3 × Coca-Cola Gaseosa Zero · 500ml')).toBeInTheDocument()

    // Aunque el poll siga devolviendo la misma decisión (main.py todavía no la procesó), ya no se muestra.
    await avanzar(600)
    expect(screen.queryByRole('button', { name: 'Confirmar' })).not.toBeInTheDocument()
    expect(screen.getByText('Esperando que aparezca un producto…')).toBeInTheDocument()

    const ticket = within(panelTicket())
    expect(ticket.getByText('1 ítem(s)')).toBeInTheDocument()
    expect(ticket.getByText('×3')).toBeInTheDocument()
    expect(ticket.getByTitle('Coca-Cola Gaseosa Zero · 500ml')).toBeInTheDocument()
    expect(ticket.getByText(`${pesos(1500)} c/u`)).toBeInTheDocument()
    expect(within(document.querySelector('.pv-ticket-total')).getByText(pesos(4500))).toBeInTheDocument()
  })

  test('la cantidad no baja de 1 y se puede escribir a mano', async () => {
    const { user } = await conDecision(PEND_CONFIRMAR)
    const panel = within(panelDecision())
    await user.click(panel.getByRole('button', { name: '–' }))
    expect(panel.getByRole('spinbutton')).toHaveValue(1)
    await user.tripleClick(panel.getByRole('spinbutton'))
    await user.keyboard('7')
    expect(panel.getByRole('spinbutton')).toHaveValue(7)
    await user.clear(panel.getByRole('spinbutton'))
    expect(panel.getByRole('spinbutton')).toHaveValue(1)
  })

  test('"Corregir manualmente" pide la carga manual y "Cancelar" descarta, sin tocar el ticket', async () => {
    const { api, user } = await conDecision(PEND_CONFIRMAR)
    await user.click(within(panelDecision()).getByRole('button', { name: 'Corregir manualmente' }))
    await waitFor(() => expect(accionesEnviadas(api)).toEqual([{ accion: 'manual' }]))

    // main.py pasa a pedir la carga manual.
    estadoCaja = { ...estadoCaja, pendiente: PEND_MANUAL }
    await avanzar()
    await user.click(within(panelDecision()).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(accionesEnviadas(api)).toEqual([{ accion: 'manual' }, { accion: 'cancelar' }]))
    expect(within(panelTicket()).getByText('Todavía no se cargó ningún producto.')).toBeInTheDocument()
  })

  test('si el servidor rechaza la respuesta (409), avisa y la decisión sigue a la vista', async () => {
    const { user } = await conDecision(PEND_CONFIRMAR, {
      'POST /api/productos/accion': { status: 409, json: { error: 'no hay ninguna decision pendiente ahora mismo' } },
    })
    await user.click(within(panelDecision()).getByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(within(toasts()).getByText('Error: no hay ninguna decision pendiente ahora mismo')).toBeInTheDocument())
    expect(within(panelDecision()).getByRole('button', { name: 'Confirmar' })).toBeEnabled()
    expect(within(panelTicket()).getByText('0 ítem(s)')).toBeInTheDocument()
  })

  test('un error sin mensaje usa el texto genérico', async () => {
    const { user } = await conDecision(PEND_CONFIRMAR, { 'POST /api/productos/accion': { status: 500, json: {} } })
    await user.click(within(panelDecision()).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(within(toasts()).getByText('Error: no se pudo enviar la respuesta')).toBeInTheDocument())
  })

  test('mientras se envía la respuesta los botones quedan deshabilitados', async () => {
    let soltar
    const { user } = await conDecision(PEND_CONFIRMAR, {
      'POST /api/productos/accion': () => new Promise((r) => { soltar = () => r({ ok: true }) }),
    })
    await user.click(within(panelDecision()).getByRole('button', { name: 'Confirmar' }))
    for (const nombre of ['Confirmar', 'Corregir manualmente', 'Cancelar']) {
      expect(within(panelDecision()).getByRole('button', { name: nombre })).toBeDisabled()
    }
    await act(async () => { soltar() })
    await waitFor(() => expect(within(panelTicket()).getByText('1 ítem(s)')).toBeInTheDocument())
  })

  test('cuando main.py la procesa y aparece la siguiente decisión, se muestra con la cantidad en 1', async () => {
    const { user } = await conDecision(PEND_CONFIRMAR)
    await user.click(within(panelDecision()).getByRole('button', { name: '+' }))
    await user.click(within(panelDecision()).getByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(within(panelTicket()).getByText('1 ítem(s)')).toBeInTheDocument())

    estadoCaja = { corriendo: true, estado: 'inactivo', pendiente: null }
    await avanzar()
    // El mismo producto vuelve a pasar por la cámara: se vuelve a pedir confirmación.
    estadoCaja = { corriendo: true, estado: 'esperando_decision', pendiente: PEND_CONFIRMAR }
    await avanzar()
    expect(within(panelDecision()).getByRole('button', { name: 'Confirmar' })).toBeInTheDocument()
    expect(within(panelDecision()).getByRole('spinbutton')).toHaveValue(1)
  })
})

describe('decisión "elegir" (varios candidatos)', () => {
  test('lista los candidatos con el primero elegido por defecto', async () => {
    await conDecision(PEND_ELEGIR)
    const radios = within(panelDecision()).getAllByRole('radio')
    expect(radios).toHaveLength(3)
    expect(radios[0]).toBeChecked()
    expect(screen.getByText('Oreo Galletitas')).toBeInTheDocument()
    expect(screen.getByText('Playadito Yerba · 1kg')).toBeInTheDocument()
    expect(screen.getByText('SKU SKU002')).toBeInTheDocument()
  })

  test('"Confirmar elección" manda el índice y la cantidad, y suma el candidato elegido al ticket', async () => {
    const { api, user } = await conDecision(PEND_ELEGIR)
    const panel = within(panelDecision())
    await user.click(screen.getByText('Oreo Galletitas'))
    expect(panel.getAllByRole('radio')[1]).toBeChecked()
    await user.click(panel.getAllByRole('radio')[2])
    expect(panel.getAllByRole('radio')[2]).toBeChecked()
    await user.click(panel.getByRole('button', { name: '+' }))

    await user.click(panel.getByRole('button', { name: 'Confirmar elección' }))
    await waitFor(() => expect(accionesEnviadas(api)).toEqual([{ accion: 'elegir', indice: 2, cantidad: 2 }]))
    const ticket = within(panelTicket())
    await waitFor(() => expect(ticket.getByTitle('Playadito Yerba · 1kg')).toBeInTheDocument())
    expect(ticket.getByText('×2')).toBeInTheDocument()
    expect(within(document.querySelector('.pv-ticket-total')).getByText(pesos(8400))).toBeInTheDocument()
  })

  test('"Cargar manualmente" y "Cancelar" mandan su acción', async () => {
    const { api, user } = await conDecision(PEND_ELEGIR)
    await user.click(within(panelDecision()).getByRole('button', { name: 'Cargar manualmente' }))
    await waitFor(() => expect(accionesEnviadas(api)).toEqual([{ accion: 'manual' }]))
    estadoCaja = { ...estadoCaja, pendiente: { ...PEND_ELEGIR, candidatos: [CATALOGO[1], CATALOGO[2]] } }
    await avanzar()
    await user.click(within(panelDecision()).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(accionesEnviadas(api)).toEqual([{ accion: 'manual' }, { accion: 'cancelar' }]))
  })

  test('al cambiar los candidatos se vuelve a elegir el primero', async () => {
    const { user } = await conDecision(PEND_ELEGIR)
    await user.click(within(panelDecision()).getAllByRole('radio')[2])
    estadoCaja = { ...estadoCaja, pendiente: { ...PEND_ELEGIR, candidatos: [CATALOGO[2], CATALOGO[1]] } }
    await avanzar()
    expect(within(panelDecision()).getAllByRole('radio')[0]).toBeChecked()
  })

  test('sin candidatos no se puede confirmar', async () => {
    await conDecision({ tipo: 'elegir', candidatos: [] })
    expect(within(panelDecision()).getByRole('button', { name: 'Confirmar elección' })).toBeDisabled()
    expect(within(panelDecision()).queryAllByRole('radio')).toHaveLength(0)
  })

  test('si "candidatos" no viene, tampoco se rompe', async () => {
    await conDecision({ tipo: 'elegir' })
    expect(within(panelDecision()).getByRole('button', { name: 'Confirmar elección' })).toBeDisabled()
  })
})

describe('decisión "manual" (producto que no está en la base)', () => {
  test('ofrece el catálogo y no deja cargar hasta elegir un producto', async () => {
    await conDecision(PEND_MANUAL)
    const select = within(panelDecision()).getByRole('combobox')
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual([
      '— elegir producto —',
      'Coca-Cola Gaseosa Zero · 500ml (SKU001)',
      'Oreo Galletitas (SKU002)',
      'Playadito Yerba · 1kg (SKU003)',
    ])
    expect(within(panelDecision()).getByRole('button', { name: 'Cargar' })).toBeDisabled()
  })

  test('"Cargar" manda el SKU y la cantidad, y suma el producto con el precio del catálogo', async () => {
    const { api, user } = await conDecision(PEND_MANUAL)
    const panel = within(panelDecision())
    await user.selectOptions(panel.getByRole('combobox'), 'SKU002')
    await user.click(panel.getByRole('button', { name: '+' }))
    await user.click(panel.getByRole('button', { name: 'Cargar' }))

    await waitFor(() => expect(accionesEnviadas(api)).toEqual([{ accion: 'cargar', sku: 'SKU002', cantidad: 2 }]))
    const ticket = within(panelTicket())
    await waitFor(() => expect(ticket.getByTitle('Oreo Galletitas')).toBeInTheDocument())
    expect(within(document.querySelector('.pv-ticket-total')).getByText(pesos(1601))).toBeInTheDocument()
  })

  test('"Cancelar" manda cancelar', async () => {
    const { api, user } = await conDecision(PEND_MANUAL)
    await user.click(within(panelDecision()).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(accionesEnviadas(api)).toEqual([{ accion: 'cancelar' }]))
  })

  test('si el catálogo no cargó (servidor caído) el selector queda vacío y solo se puede cancelar', async () => {
    await conDecision(PEND_MANUAL, { 'GET /api/productos/stock': new TypeError('Failed to fetch') })
    const select = within(panelDecision()).getByRole('combobox')
    expect(within(select).getAllByRole('option')).toHaveLength(1)
    expect(within(panelDecision()).getByRole('button', { name: 'Cargar' })).toBeDisabled()
    expect(within(panelDecision()).getByRole('button', { name: 'Cancelar' })).toBeEnabled()
  })

  test('un tipo de decisión desconocido no muestra nada en el panel', async () => {
    await conDecision({ tipo: 'otro' })
    expect(within(panelDecision()).queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('ticket de la venta', () => {
  const ITEMS = [
    { id: 2, sku: 'SKU002', nombre: 'Oreo Galletitas', precio: 800.5, cantidad: 2, hora: '2026-10-20T10:00:00.000Z', confianza_llm: null, estado_matching: 'manual', datos_llm: null },
    { id: 1, sku: 'SKU001', nombre: 'Coca-Cola Gaseosa Zero · 500ml', precio: 1500, cantidad: 1, hora: '2026-10-20T09:59:00.000Z', confianza_llm: 0.91, estado_matching: 'reconocido', datos_llm: { marca: 'Coca-Cola' } },
  ]
  const conTicket = (items = ITEMS) => window.localStorage.setItem('optifull.ticket', JSON.stringify(items))

  test('vacío muestra el mensaje y no ofrece confirmar', () => {
    montar()
    expect(within(panelTicket()).getByText('Todavía no se cargó ningún producto.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirmar venta' })).not.toBeInTheDocument()
  })

  test('se recupera del navegador al recargar la página, con cantidades, precios y total', () => {
    conTicket()
    montar()
    const ticket = within(panelTicket())
    expect(ticket.getByText('2 ítem(s)')).toBeInTheDocument()
    expect(ticket.getByText('×2')).toBeInTheDocument()
    expect(ticket.getByText(`${pesos(800.5)} c/u`)).toBeInTheDocument()
    // La línea de cantidad 1 no muestra precio unitario.
    expect(ticket.getAllByText(/c\/u/)).toHaveLength(1)
    expect(within(document.querySelector('.pv-ticket-total')).getByText(pesos(3101))).toBeInTheDocument()
  })

  test('un respaldo dañado en el navegador se ignora (ticket vacío)', () => {
    window.localStorage.setItem('optifull.ticket', '{no es json')
    montar()
    expect(within(panelTicket()).getByText('Todavía no se cargó ningún producto.')).toBeInTheDocument()
  })

  test('quitar un producto actualiza el total y el respaldo', async () => {
    conTicket()
    const { user } = montar()
    const filas = within(panelTicket()).getAllByTitle('Quitar del ticket')
    await user.click(filas[0])
    expect(within(panelTicket()).getByText('1 ítem(s)')).toBeInTheDocument()
    expect(within(document.querySelector('.pv-ticket-total')).getByText(pesos(1500))).toBeInTheDocument()
    expect(JSON.parse(window.localStorage.getItem('optifull.ticket')).map((it) => it.sku)).toEqual(['SKU001'])
  })

  test('"Vaciar" pide confirmación: si se cancela no cambia nada, si se acepta lo vacía', async () => {
    conTicket()
    const confirmar = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { user } = montar()
    await user.click(screen.getByRole('button', { name: 'Vaciar' }))
    expect(confirmar).toHaveBeenCalledWith('¿Vaciar el ticket? Se descartan todos los productos cargados.')
    expect(within(panelTicket()).getByText('2 ítem(s)')).toBeInTheDocument()

    confirmar.mockReturnValue(true)
    await user.click(screen.getByRole('button', { name: 'Vaciar' }))
    expect(within(panelTicket()).getByText('Todavía no se cargó ningún producto.')).toBeInTheDocument()
    expect(JSON.parse(window.localStorage.getItem('optifull.ticket'))).toEqual([])
  })

  test('"Confirmar venta" manda todos los ítems con sus datos de detección, vacía el ticket y refresca stock y métricas', async () => {
    conTicket()
    const { api, user } = montar()
    await waitFor(() => expect(api.hechos('/api/productos/metricas')).toHaveLength(1))
    await user.click(screen.getByRole('button', { name: 'Confirmar venta' }))

    await waitFor(() => expect(within(toasts()).getByText(`Venta confirmada · ${pesos(3101)}`)).toBeInTheDocument())
    expect(api.hechos('/api/productos/venta', 'POST')[0].cuerpo).toEqual({
      items: [
        { sku: 'SKU002', cantidad: 2, confianza_llm: null, estado_matching: 'manual', datos_llm: null },
        { sku: 'SKU001', cantidad: 1, confianza_llm: 0.91, estado_matching: 'reconocido', datos_llm: { marca: 'Coca-Cola' } },
      ],
    })
    expect(within(panelTicket()).getByText('Todavía no se cargó ningún producto.')).toBeInTheDocument()
    await waitFor(() => expect(api.hechos('/api/productos/stock')).toHaveLength(2))
    await waitFor(() => expect(api.hechos('/api/productos/metricas')).toHaveLength(2))
  })

  test('los productos confirmados por la cajera viajan a la venta con la meta de la detección', async () => {
    const { api, user } = await conDecision(PEND_CONFIRMAR)
    await user.click(within(panelDecision()).getByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(within(panelTicket()).getByText('1 ítem(s)')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    await waitFor(() => expect(api.hechos('/api/productos/venta', 'POST')).toHaveLength(1))
    expect(api.hechos('/api/productos/venta', 'POST')[0].cuerpo).toEqual({
      items: [{ sku: 'SKU001', cantidad: 1, confianza_llm: 0.91, estado_matching: 'reconocido', datos_llm: META.datos_llm }],
    })
  })

  test('una carga manual sin meta queda registrada como "manual"', async () => {
    const { api, user } = await conDecision({ tipo: 'manual' })
    await user.selectOptions(within(panelDecision()).getByRole('combobox'), 'SKU003')
    await user.click(within(panelDecision()).getByRole('button', { name: 'Cargar' }))
    await waitFor(() => expect(within(panelTicket()).getByText('1 ítem(s)')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    await waitFor(() => expect(api.hechos('/api/productos/venta', 'POST')).toHaveLength(1))
    expect(api.hechos('/api/productos/venta', 'POST')[0].cuerpo.items).toEqual([
      { sku: 'SKU003', cantidad: 1, confianza_llm: null, estado_matching: 'manual', datos_llm: null },
    ])
  })

  test('mientras se confirma muestra "Confirmando…" y bloquea quitar y vaciar', async () => {
    conTicket()
    let soltar
    const { user } = montar({ 'POST /api/productos/venta': () => new Promise((r) => { soltar = () => r({ ok: true }) }) })
    await user.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    expect(screen.getByRole('button', { name: 'Confirmando…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Vaciar' })).toBeDisabled()
    for (const b of within(panelTicket()).getAllByTitle('Quitar del ticket')) expect(b).toBeDisabled()
    await act(async () => { soltar() })
    await waitFor(() => expect(within(panelTicket()).getByText('Todavía no se cargó ningún producto.')).toBeInTheDocument())
  })

  test('si la venta falla (400), avisa el motivo y el ticket queda intacto', async () => {
    conTicket()
    const { api, user } = montar({
      'POST /api/productos/venta': { status: 400, json: { error: 'productos inexistentes: SKU002' } },
    })
    await user.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    await waitFor(() => expect(within(toasts()).getByText('No se pudo confirmar la venta: productos inexistentes: SKU002')).toBeInTheDocument())
    expect(within(panelTicket()).getByText('2 ítem(s)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar venta' })).toBeEnabled()
    expect(api.hechos('/api/productos/stock')).toHaveLength(1)
  })

  test('si la venta falla sin mensaje (500) o por red, también se avisa', async () => {
    conTicket()
    let regla = { status: 500, json: {} }
    const { user } = montar({ 'POST /api/productos/venta': () => regla })
    await user.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    await waitFor(() => expect(within(toasts()).getByText('No se pudo confirmar la venta: no se pudo confirmar la venta')).toBeInTheDocument())
    regla = new TypeError('Failed to fetch')
    await user.click(screen.getByRole('button', { name: 'Confirmar venta' }))
    await waitFor(() => expect(within(toasts()).getByText('No se pudo confirmar la venta: Failed to fetch')).toBeInTheDocument())
    expect(within(panelTicket()).getByText('2 ítem(s)')).toBeInTheDocument()
  })
})

describe('métricas', () => {
  test('muestra transacciones, confianza promedio y cuántos se reconocieron solos', async () => {
    montar()
    await waitFor(() => expect(tileValor('Transacciones')).toHaveTextContent('12'))
    expect(tileValor('Confianza LLM')).toHaveTextContent('87%')
    expect(tileValor('Reconocidos solos')).toHaveTextContent('5de 8')
    expect(tileValor('Estado cámara')).toHaveTextContent('Apagada')
  })

  test('sin métricas (error del servidor) muestra guiones y cero reconocidos', async () => {
    const { api } = montar({ 'GET /api/productos/metricas': { status: 503, json: { error: 'sin conexion a la base de datos' } } })
    await waitFor(() => expect(api.hechos('/api/productos/metricas')).toHaveLength(1))
    await avanzar()
    expect(tileValor('Transacciones')).toHaveTextContent('—')
    expect(tileValor('Confianza LLM')).toHaveTextContent('—')
    expect(tileValor('Reconocidos solos').querySelector('.stat-tile-val')).toHaveTextContent('0')
    expect(tileValor('Reconocidos solos').querySelector('.stat-tile-unit')).toBeNull()
  })

  test('con la base vacía (sin transacciones) muestra cero', async () => {
    montar({ 'GET /api/productos/metricas': { total_transacciones: 0, confianza_promedio: 0, por_estado_matching: [], productos_con_mas_problemas: [] } })
    await waitFor(() => expect(tileValor('Transacciones').querySelector('.stat-tile-val')).toHaveTextContent('0'))
    expect(tileValor('Confianza LLM')).toHaveTextContent('0%')
  })

  test('si el servidor está caído no se rompe la página', async () => {
    const { api } = montar({
      'GET /api/productos/metricas': new TypeError('Failed to fetch'),
      'GET /api/videos': new TypeError('Failed to fetch'),
      'GET /api/productos/estado': new TypeError('Failed to fetch'),
    })
    await waitFor(() => expect(api.hechos('/api/videos')).toHaveLength(1))
    await avanzar()
    expect(screen.getByRole('heading', { name: /Productos — Punto de venta/ })).toBeInTheDocument()
    expect(within(screen.getByRole('combobox')).getAllByRole('option')).toHaveLength(1)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })

  test('si /api/videos no devuelve una lista, se ignora', async () => {
    const { api } = montar({ 'GET /api/videos': { error: 'x' } })
    await waitFor(() => expect(api.hechos('/api/videos')).toHaveLength(1))
    await avanzar()
    expect(within(screen.getByRole('combobox')).getAllByRole('option')).toHaveLength(1)
  })
})

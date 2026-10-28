// Pruebas de la página de Alertas (SectionPages.jsx): lista, filtros, resolver, decidir si una persona es empleada,
// y las ventanas de evidencia / video / foto. La API es falsa (ver src/test/apiFalsa.js) y respeta los contratos de
// frontend/api/alertas.py (GET /api/alertas, POST /api/alertas/<id>/resolver) y stats.py (POST /api/personas/<id>/empleado).
import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { apiFalsa } from '../test/apiFalsa'
import { ToastProvider } from '../components/Toast'
import { AlertsPage } from './SectionPages'

const AHORA = new Date('2026-10-20T15:00:00Z').getTime()
const SEG = 1000
const MIN = 60 * SEG
const HORA = 60 * MIN

const HURTO = {
  id: 1, persona_id: 11, tipo: 'posible_hurto', sev: 'warn', title: 'Posible hurto', desc: 'Guardó un producto sin pasar por caja',
  zone: 'Góndola 3', secuencia: ['Entrada', 'Góndola 3'], cam: 2, ts: AHORA - 30 * SEG, status: 'open',
  sesion_id: 7, offset_seg: 12, evidencia: null,
}
const CON_EVIDENCIA = {
  id: 2, persona_id: 12, tipo: 'posible_hurto', sev: 'warn', title: 'Merodeo en caja', desc: 'Estuvo mucho tiempo cerca de la caja',
  zone: 'Caja', secuencia: ['Caja'], cam: 1, ts: AHORA - (2 * HORA + 5 * MIN), status: 'resolved',
  sesion_id: 8, offset_seg: 0,
  evidencia: {
    video: '/api/evidencias/clip2.mp4',
    frames: [
      { url: '/api/evidencias/f1.jpg', etiqueta: 'Toma el producto', ts: '2026-10-20T12:55:00Z' },
      { url: '/api/evidencias/f2.jpg', etiqueta: 'Lo guarda', ts: '2026-10-20T12:55:04Z' },
    ],
  },
}
const EMPLEADO = {
  id: 'emp-5-20261017', tipo: 'posible_empleado', persona_id: 5, sev: 'info', title: 'Persona posiblemente empleada',
  desc: 'Estuvo 7 h 05 min en la tienda', zone: 'Tienda', secuencia: [], cam: 3, ts: AHORA - 3 * 24 * HORA, status: 'open',
  sesion_id: null, offset_seg: 0, evidencia: null, foto: '/api/evidencias/persona5.jpg', es_empleado: false, minutos: 425,
}
const SIN_SESION = {
  id: 4, persona_id: 14, tipo: 'otro', sev: 'info', title: 'Alerta', desc: '', zone: 'Desconocida', secuencia: [],
  cam: 2, ts: AHORA - 10 * MIN, status: 'open', sesion_id: null, offset_seg: 0, evidencia: null,
}
const TODAS = [HURTO, SIN_SESION, CON_EVIDENCIA, EMPLEADO]

const SESIONES = [
  { id: 30, camara_id: 1, nombre: 'cam1_lunes.mp4', disponible: true, offset_seg: 65 },
  { id: 31, camara_id: 2, nombre: 'cam2_lunes.mp4', disponible: true, offset_seg: 0 },
  { id: 32, camara_id: 2, nombre: 'borrado.mp4', disponible: false, offset_seg: 0 },
]

function montar(reglas = {}) {
  const api = apiFalsa({
    'GET /api/alertas': TODAS,
    'POST /api/alertas/': (req) => ({ json: { id: Number(req.ruta.split('/')[3]), resuelta: true } }),
    'POST /api/personas/': (req) => ({ json: { cliente_id: Number(req.ruta.split('/')[3]), ...req.cuerpo } }),
    'GET /api/sessions': SESIONES,
    'GET /api/videos': ['local1.mp4', 'local2.mp4'],
    ...reglas,
  })
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
  const vista = render(<ToastProvider><AlertsPage /></ToastProvider>)
  return { api, user, ...vista }
}

const avanzar = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))
const toasts = () => document.querySelector('.toast-stack')
const fila = (titulo) => screen.getByText(titulo, { selector: 'div' }).closest('.dt-alerts')
// Detalle desplegado de una alerta (debajo de su fila).
const detalle = (titulo) => fila(titulo).parentElement.querySelector('.dt-expand')
const stat = (etiqueta) => screen.getByText(etiqueta, { selector: '.stat-mini-lbl' }).closest('.stat-mini')
const contador = () => screen.getByText(/\d+ \/ \d+ eventos/)
const modal = () => document.querySelector('.vm-modal')

// La página arranca filtrando warning + abiertas; la mayoría de las pruebas miran todas las alertas.
async function verTodas(user) {
  await user.click(screen.getByRole('button', { name: 'Todas' }))
  await user.click(screen.getByRole('button', { name: 'Todos' }))
}

// Igual que montar(), pero una vez cargada la lista deja ver todas las alertas (no solo warning + abiertas).
async function montarTodas(reglas) {
  const r = montar(reglas)
  await waitFor(() => expect(screen.queryByText('Cargando alertas…')).not.toBeInTheDocument())
  await verTodas(r.user)
  return r
}

async function cargada(reglas) {
  const r = montar(reglas)
  await waitFor(() => expect(screen.getByText('Posible hurto')).toBeInTheDocument())
  await verTodas(r.user)
  return r
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(AHORA)
})

describe('lista de alertas', () => {
  test('mientras carga muestra "Cargando alertas…"', async () => {
    let soltar
    montar({ 'GET /api/alertas': () => new Promise((r) => { soltar = () => r({ json: TODAS }) }) })
    expect(screen.getByText('Cargando alertas…')).toBeInTheDocument()
    await act(async () => { soltar() })
    await waitFor(() => expect(screen.queryByText('Cargando alertas…')).not.toBeInTheDocument())
  })

  test('muestra los totales: warning, abiertas, resueltas y el porcentaje resuelto', async () => {
    await cargada()
    expect(stat('Total')).toHaveTextContent('4')
    expect(stat('Warning')).toHaveTextContent('2')
    expect(stat('Abiertas')).toHaveTextContent('3')
    expect(stat('Resueltas')).toHaveTextContent('1')
    expect(stat('Resueltas')).toHaveTextContent('25% del total')
    expect(contador()).toHaveTextContent('4 / 4 eventos')
    // orden de las tarjetas: abiertas, warning, resueltas y al final el total
    expect([...document.querySelectorAll('.stat-mini-lbl')].map((e) => e.textContent)).toEqual(['Abiertas', 'Warning', 'Resueltas', 'Total'])
  })

  test('cada fila muestra título, descripción, zona, cámara, estado y el tiempo transcurrido', async () => {
    await cargada()
    const f = within(fila('Posible hurto'))
    expect(f.getByText('Guardó un producto sin pasar por caja')).toBeInTheDocument()
    expect(f.getByText('Góndola 3')).toBeInTheDocument()
    expect(f.getByText('cam-2')).toBeInTheDocument()
    expect(f.getByText('Abierta')).toBeInTheDocument()
    expect(f.getByText('hace 30s')).toHaveAttribute('title', new Date(HURTO.ts).toLocaleString('es-AR'))

    expect(within(fila('Alerta')).getByText('hace 10m')).toBeInTheDocument()
    expect(within(fila('Merodeo en caja')).getByText('hace 2h 5m')).toBeInTheDocument()
    expect(within(fila('Merodeo en caja')).getByText('Resuelta')).toBeInTheDocument()
    expect(within(fila('Merodeo en caja')).getByText('▶ Evidencia')).toBeInTheDocument()
  })

  test('las alertas de más de un día muestran la fecha y hora exactas en vez de "hace N"', async () => {
    await cargada()
    const d = new Date(EMPLEADO.ts)
    const esperado = d.toLocaleDateString('es-AR', { day: '2-digit', month: 'short' }) + ' '
      + d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false })
    const celda = within(fila('Persona posiblemente empleada')).getByTitle(d.toLocaleString('es-AR'))
    expect(celda.textContent).toBe(esperado)
    expect(celda.textContent).not.toMatch(/^hace/)
  })

  test('el tiempo transcurrido se actualiza solo y la lista se vuelve a pedir cada 20 s', async () => {
    const { api } = await cargada()
    expect(api.hechos('/api/alertas')).toHaveLength(1)
    await avanzar(10 * SEG)
    expect(within(fila('Posible hurto')).getByText('hace 40s')).toBeInTheDocument()
    await avanzar(10 * SEG)
    expect(api.hechos('/api/alertas')).toHaveLength(2)
  })

  test('sin alertas muestra el estado vacío y no muestra porcentaje', async () => {
    const { api } = montar({ 'GET /api/alertas': [] })
    await waitFor(() => expect(screen.getByText('No hay alertas con los filtros aplicados.')).toBeInTheDocument())
    expect(api.hechos('/api/alertas')).toHaveLength(1)
    expect(stat('Total')).toHaveTextContent('0')
    expect(screen.queryByText(/% del total/)).not.toBeInTheDocument()
    expect(contador()).toHaveTextContent('0 / 0 eventos')
  })

  test('si la API responde un error (500) o no responde, queda la lista vacía sin romperse', async () => {
    let regla = { status: 500, json: { error: 'relation "alertas" does not exist' } }
    montar({ 'GET /api/alertas': () => regla })
    await waitFor(() => expect(screen.getByText('No hay alertas con los filtros aplicados.')).toBeInTheDocument())

    regla = new TypeError('Failed to fetch')
    await avanzar(20 * SEG)
    expect(screen.getByText('No hay alertas con los filtros aplicados.')).toBeInTheDocument()
    expect(stat('Total')).toHaveTextContent('0')
  })
})

describe('filtros', () => {
  test('al entrar muestra solo los warning abiertos (los posibles hurtos para revisar)', async () => {
    montar()
    await waitFor(() => expect(screen.getByText('Posible hurto')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Warning' })).toHaveClass('on')
    expect(screen.getByRole('button', { name: 'Abierta' })).toHaveClass('on')
    expect(contador()).toHaveTextContent('1 / 4 eventos')
    expect(screen.queryByText('Merodeo en caja')).not.toBeInTheDocument()                 // warning, pero resuelta
    expect(screen.queryByText('Persona posiblemente empleada')).not.toBeInTheDocument()   // info
    // ya no hay severidad "Crítica": solo Warning e Info
    expect(screen.queryByRole('button', { name: 'Crítica' })).not.toBeInTheDocument()
    expect(stat('Warning')).toHaveTextContent('2')
  })

  test('por severidad', async () => {
    const { user } = await cargada()
    await user.click(screen.getByRole('button', { name: 'Warning' }))
    expect(contador()).toHaveTextContent('2 / 4 eventos')
    expect(screen.getByText('Posible hurto')).toBeInTheDocument()
    expect(screen.getByText('Merodeo en caja')).toBeInTheDocument()
    expect(screen.queryByText('Persona posiblemente empleada')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Warning' })).toHaveClass('on')

    await user.click(screen.getByRole('button', { name: 'Info' }))
    expect(contador()).toHaveTextContent('2 / 4 eventos')
    expect(screen.getByText('Persona posiblemente empleada')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Todas' }))
    expect(contador()).toHaveTextContent('4 / 4 eventos')
  })

  test('por estado', async () => {
    const { user } = await cargada()
    await user.click(screen.getByRole('button', { name: 'Resuelta' }))
    expect(contador()).toHaveTextContent('1 / 4 eventos')
    expect(screen.getByText('Merodeo en caja')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Abierta' }))
    expect(contador()).toHaveTextContent('3 / 4 eventos')
    await user.click(screen.getByRole('button', { name: 'Todos' }))
    expect(contador()).toHaveTextContent('4 / 4 eventos')
  })

  test('por zona, con las zonas que aparecen en las alertas', async () => {
    const { user } = await cargada()
    const select = screen.getByRole('combobox')
    expect(within(select).getAllByRole('option').map((o) => o.textContent))
      .toEqual(['Todas las zonas', 'Góndola 3', 'Desconocida', 'Caja', 'Tienda'])
    await user.selectOptions(select, 'Caja')
    expect(contador()).toHaveTextContent('1 / 4 eventos')
    expect(screen.getByText('Merodeo en caja')).toBeInTheDocument()
  })

  test('filtros combinados sin resultados muestran el estado vacío', async () => {
    const { user } = await cargada()
    await user.click(screen.getByRole('button', { name: 'Info' }))
    await user.click(screen.getByRole('button', { name: 'Resuelta' }))
    expect(screen.getByText('No hay alertas con los filtros aplicados.')).toBeInTheDocument()
    expect(contador()).toHaveTextContent('0 / 4 eventos')
  })
})

describe('detalle y resolver', () => {
  test('al tocar una fila se despliega el detalle y al tocarla de nuevo se cierra', async () => {
    const { user } = await cargada()
    await user.click(screen.getByText('Posible hurto'))
    const b = within(detalle('Posible hurto'))
    expect(b.getByText('Entrada → Góndola 3')).toBeInTheDocument()
    expect(b.getByText('#11')).toBeInTheDocument()
    expect(b.getByText(new Date(HURTO.ts).toLocaleTimeString('es-AR'))).toBeInTheDocument()
    // Alerta reciente sin evidencia todavía: se avisa que se está preparando.
    expect(b.getByText('Preparando el clip y los frames…')).toBeInTheDocument()
    expect(b.getByRole('button', { name: 'Ver video' })).toBeInTheDocument()

    await user.click(screen.getByText('Posible hurto'))
    expect(screen.queryByText('Entrada → Góndola 3')).not.toBeInTheDocument()
  })

  test('una alerta vieja sin secuencia ni evidencia muestra "—" y no promete evidencia', async () => {
    const { user } = await cargada()
    await user.click(screen.getByText('Alerta', { selector: 'div' }))
    const b = within(detalle('Alerta'))
    expect(b.getByText('—')).toBeInTheDocument()
    expect(b.queryByText('Preparando el clip y los frames…')).not.toBeInTheDocument()
  })

  test('resolver desde el botón rápido manda resuelta=true, avisa y vuelve a pedir la lista', async () => {
    const { api, user } = await cargada()
    await user.click(within(fila('Posible hurto')).getByRole('button', { name: 'Resolver' }))
    await waitFor(() => expect(within(toasts()).getByText('Alerta #1 resuelta')).toBeInTheDocument())
    const [pedido] = api.hechos('/api/alertas/1/resolver', 'POST')
    expect(pedido.cuerpo).toEqual({ resuelta: true })
    await waitFor(() => expect(api.hechos('/api/alertas')).toHaveLength(2))
    // La fila no se abrió al tocar el botón.
    expect(screen.queryByText('Entrada → Góndola 3')).not.toBeInTheDocument()
  })

  test('las alertas resueltas no ofrecen "Resolver"', async () => {
    const { user } = await cargada()
    expect(within(fila('Merodeo en caja')).queryByRole('button', { name: 'Resolver' })).not.toBeInTheDocument()
    await user.click(screen.getByText('Merodeo en caja'))
    expect(within(detalle('Merodeo en caja')).queryByRole('button', { name: 'Resolver' })).not.toBeInTheDocument()
  })

  test('mientras se resuelve, el botón del detalle dice "Resolviendo…" y queda deshabilitado', async () => {
    let soltar
    const { user } = await cargada({ 'POST /api/alertas/': () => new Promise((r) => { soltar = () => r({ json: { id: 1, resuelta: true } }) }) })
    await user.click(screen.getByText('Posible hurto'))
    await user.click(within(detalle('Posible hurto')).getByRole('button', { name: 'Resolver' }))
    expect(within(detalle('Posible hurto')).getByRole('button', { name: 'Resolviendo…' })).toBeDisabled()
    expect(within(fila('Posible hurto')).getByTitle('Resolver')).toBeDisabled()
    await act(async () => { soltar() })
    await waitFor(() => expect(within(detalle('Posible hurto')).getByRole('button', { name: 'Resolver' })).toBeEnabled())
  })

  test('si el servidor responde con error (404), lo muestra', async () => {
    const { api, user } = await cargada({ 'POST /api/alertas/': { status: 404, json: { error: 'no existe alerta con id 1' } } })
    await user.click(within(fila('Posible hurto')).getByRole('button', { name: 'Resolver' }))
    await waitFor(() => expect(within(toasts()).getByText('no existe alerta con id 1')).toBeInTheDocument())
    expect(within(toasts()).queryByText('Alerta #1 resuelta')).not.toBeInTheDocument()
    expect(api.hechos('/api/alertas')).toHaveLength(1)
  })

  test('si no hay conexión, avisa que no se pudo resolver', async () => {
    const { user } = await cargada({ 'POST /api/alertas/': new TypeError('Failed to fetch') })
    await user.click(within(fila('Posible hurto')).getByRole('button', { name: 'Resolver' }))
    await waitFor(() => expect(within(toasts()).getByText('No se pudo resolver la alerta')).toBeInTheDocument())
    expect(within(fila('Posible hurto')).getByRole('button', { name: 'Resolver' })).toBeEnabled()
  })
})

describe('persona posiblemente empleada', () => {
  test('la fila muestra la foto y no ofrece "Resolver"; el detalle muestra el tiempo en la tienda', async () => {
    const { user } = await cargada()
    const f = within(fila('Persona posiblemente empleada'))
    expect(f.getByRole('img', { name: 'Persona #5' })).toHaveAttribute('src', '/api/evidencias/persona5.jpg')
    expect(f.queryByRole('button', { name: 'Resolver' })).not.toBeInTheDocument()
    expect(f.getByRole('button', { name: 'Ver foto' })).toBeInTheDocument()

    await user.click(screen.getByText('Persona posiblemente empleada'))
    const b = within(detalle('Persona posiblemente empleada'))
    expect(b.getByText('Tiempo en la tienda')).toBeInTheDocument()
    expect(b.getByText('7 h 05 min')).toBeInTheDocument()
    expect(b.getByText('Foto de la persona')).toBeInTheDocument()
  })

  test('"Es empleado" desde el detalle manda es_empleado=true y revisado=true', async () => {
    const { api, user } = await cargada()
    await user.click(screen.getByText('Persona posiblemente empleada'))
    await user.click(within(detalle('Persona posiblemente empleada')).getByRole('button', { name: 'Es empleado' }))
    await waitFor(() => expect(within(toasts()).getByText('Persona #5 marcada como empleada — excluida de las métricas')).toBeInTheDocument())
    expect(api.hechos('/api/personas/5/empleado', 'POST')[0].cuerpo).toEqual({ es_empleado: true, revisado: true })
    await waitFor(() => expect(api.hechos('/api/alertas')).toHaveLength(2))
  })

  test('"No es empleado" desde el detalle la confirma como cliente', async () => {
    const { api, user } = await cargada()
    await user.click(screen.getByText('Persona posiblemente empleada'))
    await user.click(within(detalle('Persona posiblemente empleada')).getByRole('button', { name: 'No es empleado' }))
    await waitFor(() => expect(within(toasts()).getByText('Persona #5 confirmada como cliente')).toBeInTheDocument())
    expect(api.hechos('/api/personas/5/empleado', 'POST')[0].cuerpo).toEqual({ es_empleado: false, revisado: true })
  })

  test('la foto se abre en una ventana con los dos botones; al decidir se cierra', async () => {
    const { api, user } = await cargada()
    await user.click(within(fila('Persona posiblemente empleada')).getByRole('button', { name: 'Ver foto' }))
    const dialogo = screen.getByRole('dialog', { name: 'Persona posiblemente empleada' })
    expect(within(dialogo).getByRole('img', { name: 'Foto de la persona #5' })).toBeInTheDocument()
    expect(within(dialogo).getByText('Persona #5')).toBeInTheDocument()
    expect(within(dialogo).getByText('Estuvo 7 h 05 min en la tienda')).toBeInTheDocument()

    await user.click(within(dialogo).getByRole('button', { name: 'No es empleado' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(api.hechos('/api/personas/5/empleado', 'POST')[0].cuerpo).toEqual({ es_empleado: false, revisado: true })
  })

  test('si guardar la decisión falla, avisa y la ventana sigue abierta', async () => {
    let regla = { status: 404, json: { error: 'no existe persona con id 5' } }
    const { user } = await cargada({ 'POST /api/personas/': () => regla })
    await user.click(within(fila('Persona posiblemente empleada')).getByRole('button', { name: 'Ver foto' }))
    const dialogo = screen.getByRole('dialog')
    await user.click(within(dialogo).getByRole('button', { name: 'Es empleado' }))
    await waitFor(() => expect(within(toasts()).getByText('no existe persona con id 5')).toBeInTheDocument())
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    regla = new TypeError('Failed to fetch')
    await user.click(within(dialogo).getByRole('button', { name: 'Es empleado' }))
    await waitFor(() => expect(within(toasts()).getByText('No se pudo guardar la decisión')).toBeInTheDocument())
    expect(within(dialogo).getByRole('button', { name: 'Es empleado' })).toBeEnabled()
  })

  test('mientras se guarda, los botones de la ventana quedan deshabilitados', async () => {
    let soltar
    const { user } = await cargada({ 'POST /api/personas/': () => new Promise((r) => { soltar = () => r({ json: { ok: true } }) }) })
    await user.click(within(fila('Persona posiblemente empleada')).getByRole('button', { name: 'Ver foto' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Es empleado' }))
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: 'No es empleado' })).toBeDisabled()
    await act(async () => { soltar() })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('la ventana se cierra con Escape, con ✕ o tocando afuera', async () => {
    const { user } = await cargada()
    await user.click(screen.getByText('Persona posiblemente empleada'))
    // La miniatura del detalle también abre la foto.
    await user.click(within(detalle('Persona posiblemente empleada')).getAllByRole('img', { name: 'Persona #5' }).at(-1))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(within(detalle('Persona posiblemente empleada')).getByRole('button', { name: 'Ver foto' }))
    // Un clic dentro de la ventana no la cierra.
    await user.click(within(screen.getByRole('dialog')).getByText('Estuvo 7 h 05 min en la tienda'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(within(fila('Persona posiblemente empleada')).getByRole('button', { name: 'Ver foto' }))
    await user.click(document.querySelector('.vm-overlay'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('sin foto todavía, lo indica; una persona ya revisada no muestra los botones de decisión', async () => {
    const sinFoto = { ...EMPLEADO, foto: null }
    const revisada = { ...EMPLEADO, id: 'emp-6-20261017', persona_id: 6, title: 'Revisada', status: 'resolved', desc: 'Marcada como empleada: excluida de las métricas.' }
    const { user } = await montarTodas({ 'GET /api/alertas': [sinFoto, revisada] })
    await waitFor(() => expect(screen.getByText('Persona posiblemente empleada')).toBeInTheDocument())
    expect(within(fila('Persona posiblemente empleada')).getByText('?')).toBeInTheDocument()

    await user.click(screen.getByText('Persona posiblemente empleada'))
    expect(within(detalle('Persona posiblemente empleada')).getByText(/Todavía no hay una foto de esta persona \(se guarda/)).toBeInTheDocument()
    await user.click(within(fila('Persona posiblemente empleada')).getByRole('button', { name: 'Ver foto' }))
    expect(within(screen.getByRole('dialog')).getByText('Todavía no hay una foto de esta persona.')).toBeInTheDocument()
    await user.keyboard('{Escape}')

    await user.click(screen.getByText('Revisada'))
    const b = within(detalle('Revisada'))
    expect(b.queryByRole('button', { name: 'Es empleado' })).not.toBeInTheDocument()
    await user.click(b.getByRole('button', { name: 'Ver foto' }))
    expect(within(screen.getByRole('dialog')).queryByRole('button', { name: 'Es empleado' })).not.toBeInTheDocument()
  })
})

describe('evidencia (clip + frames)', () => {
  test('el detalle lista los frames y al tocar uno se abre la evidencia en ese frame', async () => {
    const { user } = await cargada()
    await user.click(screen.getByText('Merodeo en caja'))
    const b = within(detalle('Merodeo en caja'))
    expect(b.getByText('Frames donde se detectó (2) · clip disponible')).toBeInTheDocument()
    await user.click(b.getByTitle('Lo guarda'))

    const m = within(modal())
    expect(m.getByText(/^Lo guarda ·/, { selector: '.ev-caption' })).toBeInTheDocument()
    expect(modal().querySelector('.ev-main-img')).toHaveAttribute('src', '/api/evidencias/f2.jpg')
    expect(m.getByText('⬇ Frame').closest('a')).toHaveAttribute('href', '/api/evidencias/f2.jpg')
    expect(m.queryByText('⬇ Descargar')).not.toBeInTheDocument()
  })

  test('"Ver evidencia" abre el clip; con las flechas se recorren los frames y se vuelve al clip', async () => {
    const { user } = await cargada()
    await user.click(within(fila('Merodeo en caja')).getByRole('button', { name: 'Ver evidencia' }))
    const m = within(modal())
    expect(modal().querySelector('video source')).toHaveAttribute('src', '/api/evidencias/clip2.mp4')
    expect(m.getByText('⬇ Descargar').closest('a')).toHaveAttribute('href', '/api/evidencias/clip2.mp4')
    expect(m.getByText('⬇ Descargar').closest('a')).toHaveAttribute('download', 'alerta-2-clip.mp4')
    expect(m.getByText(/Frames donde se detectó \(2\)/)).toBeInTheDocument()

    await user.keyboard('{ArrowRight}')
    expect(modal().querySelector('.ev-main-img')).toHaveAttribute('src', '/api/evidencias/f1.jpg')
    await user.keyboard('{ArrowRight}')
    await user.keyboard('{ArrowRight}')
    expect(modal().querySelector('.ev-main-img')).toHaveAttribute('src', '/api/evidencias/f2.jpg')
    await user.keyboard('{ArrowLeft}')
    expect(modal().querySelector('.ev-main-img')).toHaveAttribute('src', '/api/evidencias/f1.jpg')
    await user.keyboard('{ArrowLeft}')
    expect(modal().querySelector('video')).not.toBeNull()
    await user.keyboard('{ArrowLeft}')
    expect(modal().querySelector('video')).not.toBeNull()

    await user.keyboard('{Escape}')
    expect(modal()).toBeNull()
  })

  test('si el clip no se puede reproducir, lo avisa y se puede reintentar con "Ver clip"', async () => {
    const { user } = await cargada()
    await user.click(screen.getByText('Merodeo en caja'))
    await user.click(within(detalle('Merodeo en caja')).getByRole('button', { name: 'Ver evidencia' }))
    fireEvent.error(modal().querySelector('video'))
    expect(within(modal()).getByText(/No se pudo reproducir el clip/)).toBeInTheDocument()

    await user.click(within(modal()).getAllByRole('button').find((b) => b.classList.contains('ev-thumb')))
    expect(modal().querySelector('.ev-main-img')).not.toBeNull()
    await user.click(within(modal()).getByRole('button', { name: '▶ Ver clip' }))
    expect(modal().querySelector('video')).not.toBeNull()

    await user.click(within(modal()).getByRole('button', { name: '✕' }))
    expect(modal()).toBeNull()
  })

  test('la evidencia en Supabase Storage se descarga con ?download= (otro dominio ignora el atributo download)', async () => {
    const base = 'https://x.supabase.co/storage/v1/object/public/heatmaps/evidencias/alerta_2'
    const enStorage = { ...CON_EVIDENCIA, evidencia: { video: `${base}/clip.mp4`, frames: [{ ...CON_EVIDENCIA.evidencia.frames[0], url: `${base}/frame_01.jpg` }] } }
    const { user } = await montarTodas({ 'GET /api/alertas': [enStorage] })
    await waitFor(() => expect(screen.getByText('Merodeo en caja')).toBeInTheDocument())
    await user.click(within(fila('Merodeo en caja')).getByRole('button', { name: 'Ver evidencia' }))
    const m = within(modal())
    expect(modal().querySelector('video source')).toHaveAttribute('src', `${base}/clip.mp4`)
    expect(m.getByText('⬇ Descargar').closest('a')).toHaveAttribute('href', `${base}/clip.mp4?download=alerta-2-clip.mp4`)
    await user.keyboard('{ArrowRight}')
    expect(m.getByText('⬇ Frame').closest('a')).toHaveAttribute('href', `${base}/frame_01.jpg?download=alerta-2-frame-1.jpg`)
  })

  test('evidencia sin clip arranca en el primer frame', async () => {
    const soloFrames = { ...CON_EVIDENCIA, evidencia: { video: null, frames: CON_EVIDENCIA.evidencia.frames } }
    const { user } = await montarTodas({ 'GET /api/alertas': [soloFrames] })
    await waitFor(() => expect(screen.getByText('Merodeo en caja')).toBeInTheDocument())
    await user.click(screen.getByText('Merodeo en caja'))
    expect(within(detalle('Merodeo en caja')).getByText('Frames donde se detectó (2)')).toBeInTheDocument()
    await user.click(within(fila('Merodeo en caja')).getByRole('button', { name: 'Ver evidencia' }))
    expect(modal().querySelector('.ev-main-img')).toHaveAttribute('src', '/api/evidencias/f1.jpg')
    expect(within(modal()).queryByRole('button', { name: '▶ Ver clip' })).not.toBeInTheDocument()
    await user.keyboard('{ArrowLeft}')
    expect(modal().querySelector('.ev-main-img')).toHaveAttribute('src', '/api/evidencias/f1.jpg')
    await user.click(document.querySelector('.vm-overlay'))
    expect(modal()).toBeNull()
  })
})

describe('video de la alerta (sin evidencia propia)', () => {
  test('usa el clip exacto de la sesión de la alerta y lista los videos disponibles', async () => {
    let soltar
    const { api, user } = await cargada({ 'GET /api/sessions': () => new Promise((r) => { soltar = () => r({ json: SESIONES }) }) })
    await user.click(within(fila('Posible hurto')).getByRole('button', { name: 'Ver clip' }))
    expect(within(modal()).getByText('Buscando video…')).toBeInTheDocument()
    await act(async () => { soltar() })

    await waitFor(() => expect(modal().querySelector('video source')).toHaveAttribute('src', '/api/sessions/7/clip?t=12&dur=50'))
    expect(api.hechos('/api/videos')).toHaveLength(1)
    const m = within(modal())
    expect(m.getByText('⬇ Descargar').closest('a')).toHaveAttribute('href', '/api/sessions/7/clip?t=12&dur=50')
    // se descarga como .mp4 con un nombre propio, no como 'clip' sin extension
    expect(m.getByText('⬇ Descargar').closest('a')).toHaveAttribute('download', 'alerta-1-cam2.mp4')
    // Solo las sesiones con archivo disponible, más los videos locales.
    expect(m.getByText('cam1_lunes.mp4')).toBeInTheDocument()
    expect(m.getByText('cam-1 · desde 01:05')).toBeInTheDocument()
    expect(m.queryByText('borrado.mp4')).not.toBeInTheDocument()
    expect(m.getAllByText('carpeta videos/')).toHaveLength(2)

    await user.click(m.getByText('local2.mp4'))
    expect(modal().querySelector('video source')).toHaveAttribute('src', '/api/video/local2.mp4')
    expect(m.getByText('local2.mp4').closest('button')).toHaveClass('active')
  })

  test('sin sesión propia busca una sesión de la misma cámara', async () => {
    const { user } = await cargada()
    await user.click(screen.getByText('Alerta', { selector: 'div' }))
    await user.click(within(detalle('Alerta')).getByRole('button', { name: 'Ver video' }))
    await waitFor(() => expect(modal().querySelector('video source')).toHaveAttribute('src', '/api/sessions/31/clip?t=0&dur=50'))
  })

  test('sin sesión de esa cámara usa la primera disponible; sin sesiones, los videos locales; sin nada, avisa', async () => {
    const otraCam = { ...SIN_SESION, cam: 9, title: 'Otra cámara' }
    let sesiones = [SESIONES[1]]
    let videos = ['a.mp4', 'b.mp4']
    const { user } = await montarTodas({
      'GET /api/alertas': [otraCam],
      'GET /api/sessions': () => sesiones,
      'GET /api/videos': () => videos,
    })
    await waitFor(() => expect(screen.getByText('Otra cámara')).toBeInTheDocument())
    const abrir = () => user.click(within(fila('Otra cámara')).getByRole('button', { name: 'Ver clip' }))

    await abrir()
    await waitFor(() => expect(modal().querySelector('video source')).toHaveAttribute('src', '/api/sessions/31/clip?t=0&dur=50'))
    await user.keyboard('{Escape}')

    sesiones = []
    await abrir()
    // (cam - 1) % cantidad de videos = 8 % 2 = 0
    await waitFor(() => expect(modal().querySelector('video source')).toHaveAttribute('src', '/api/video/a.mp4'))
    await user.click(document.querySelector('.vm-overlay'))
    expect(modal()).toBeNull()

    videos = []
    await abrir()
    await waitFor(() => expect(within(modal()).getByText('No se encontró video en disco')).toBeInTheDocument())
    expect(within(modal()).queryByText('⬇ Descargar')).not.toBeInTheDocument()
    expect(modal().querySelector('.vm-sources')).toBeNull()
    await user.click(within(modal()).getByRole('button', { name: '✕' }))
    expect(modal()).toBeNull()
  })

  test('si la API de videos no responde, no se rompe y avisa que no hay video', async () => {
    const { user } = await montarTodas({
      'GET /api/alertas': [SIN_SESION],
      'GET /api/sessions': new TypeError('Failed to fetch'),
      'GET /api/videos': new TypeError('Failed to fetch'),
    })
    await waitFor(() => expect(screen.getByText('Alerta', { selector: 'div' })).toBeInTheDocument())
    await user.click(within(fila('Alerta')).getByRole('button', { name: 'Ver clip' }))
    await waitFor(() => expect(within(modal()).getByText('No se encontró video en disco')).toBeInTheDocument())
  })

  test('si el navegador no puede reproducir el video, ofrece descargarlo; cambiar de fuente lo reintenta', async () => {
    const { user } = await cargada({ 'GET /api/sessions/7/clip': { texto: 'mp4', headers: { 'Content-Type': 'video/mp4' } } })
    await user.click(within(fila('Posible hurto')).getByRole('button', { name: 'Ver clip' }))
    await waitFor(() => expect(modal().querySelector('video')).not.toBeNull())
    fireEvent.error(modal().querySelector('video'))
    const m = within(modal())
    await waitFor(() => expect(m.getByText('El navegador no puede reproducir este video')).toBeInTheDocument())
    expect(m.getByText('⬇ Descargar video').closest('a')).toHaveAttribute('href', '/api/sessions/7/clip?t=12&dur=50')

    await user.click(m.getByText('cam2_lunes.mp4'))
    expect(m.queryByText('El navegador no puede reproducir este video')).not.toBeInTheDocument()
    expect(modal().querySelector('video source')).toHaveAttribute('src', '/api/sessions/31/clip?t=0&dur=50')
  })

  test('si el clip responde un error (no un video), no culpa al códec ni ofrece bajar la página de error', async () => {
    const { user } = await cargada({ 'GET /api/sessions/7/clip': { status: 404, texto: 'Archivo no encontrado' } })
    await user.click(within(fila('Posible hurto')).getByRole('button', { name: 'Ver clip' }))
    await waitFor(() => expect(modal().querySelector('video')).not.toBeNull())
    fireEvent.error(modal().querySelector('video'))
    const m = within(modal())
    await waitFor(() => expect(m.getByText('El video no está disponible en el servidor')).toBeInTheDocument())
    expect(m.queryByText('El navegador no puede reproducir este video')).not.toBeInTheDocument()
    expect(m.queryByText(/Descargar/)).not.toBeInTheDocument()
  })

  test('si el video original de la alerta no está en el servidor, ni lo pide: avisa y deja elegir otro', async () => {
    const enOtraPc = { ...HURTO, video_disponible: false }
    const { api, user } = montar({ 'GET /api/alertas': [enOtraPc] })
    await waitFor(() => expect(screen.getByText('Posible hurto')).toBeInTheDocument())
    await user.click(within(fila('Posible hurto')).getByRole('button', { name: 'Ver clip' }))
    const m = within(modal())
    await waitFor(() => expect(m.getByText('El video de esta alerta no está en el servidor')).toBeInTheDocument())
    expect(modal().querySelector('video')).toBeNull()
    expect(m.queryByText('⬇ Descargar')).not.toBeInTheDocument()
    expect(api.hechos('/api/sessions/7/clip')).toHaveLength(0)
    await user.click(m.getByText('cam2_lunes.mp4'))
    expect(modal().querySelector('video source')).toHaveAttribute('src', '/api/sessions/31/clip?t=0&dur=50')
  })
})

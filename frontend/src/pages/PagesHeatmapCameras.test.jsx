// Pruebas de la página de Configuración (SettingsPage): pestañas, apariencia, umbrales, notificaciones y usuarios.
import { describe, test, expect, beforeEach } from 'vitest'
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '../components/Toast'
import { setTema } from '../components/useTheme'
import { apiFalsa } from '../test/apiFalsa.js'
import { SettingsPage, LIMITES_UMBRALES, umbralValido } from './PagesHeatmapCameras'

function abrir(reglas = {}) {
  const api = apiFalsa({ 'GET /api/configuracion': { status: 503, json: { error: 'sin base' } }, ...reglas })
  const user = userEvent.setup()
  const utils = render(<ToastProvider><SettingsPage /></ToastProvider>)
  return { api, user, ...utils }
}

const pestaña = (nombre) => screen.getByText(nombre, { selector: '.settings-nav a' })
const toasts = () => [...document.querySelectorAll('.toast > span:last-child')].map((t) => t.textContent)

beforeEach(() => {
  // El tema es estado global del módulo: cada test arranca en Día.
  setTema('light')
})

describe('SettingsPage', () => {
  test('arranca en General con la sucursal y el sistema, y pide la configuración guardada', () => {
    const { api } = abrir()
    expect(screen.getByRole('heading', { name: 'Configuración' })).toBeInTheDocument()
    expect(pestaña('General')).toHaveClass('active')
    expect(screen.getByDisplayValue('Strumia — Mendoza')).toBeInTheDocument()
    expect(screen.getByDisplayValue('YOLOv8m')).toBeDisabled()
    expect(screen.getByDisplayValue('YOLOv8m').closest('.form-field')).toHaveClass('ro')
    expect(screen.getByDisplayValue('Strumia — Mendoza')).toBeEnabled()
    expect(screen.getByDisplayValue('3')).toBeDisabled()
    expect(screen.getByDisplayValue('OptiFull v0.3.0')).toHaveClass('mono')
    expect(api.pedidos.map((p) => `${p.metodo} ${p.ruta}`)).toEqual(['GET /api/configuracion'])
  })

  test('apariencia: solo Día y Noche; elegir uno cambia y guarda el tema', async () => {
    const { user } = abrir()
    const grupo = screen.getByRole('radiogroup', { name: 'Apariencia' })
    expect(within(grupo).getAllByRole('radio').map((r) => r.textContent)).toEqual(['Día', 'Noche'])
    expect(within(grupo).queryByRole('radio', { name: 'Automático' })).toBeNull()
    expect(within(grupo).getByRole('radio', { name: 'Día' })).toHaveAttribute('aria-checked', 'true')

    await user.click(within(grupo).getByRole('radio', { name: 'Noche' }))
    expect(within(grupo).getByRole('radio', { name: 'Noche' })).toHaveAttribute('aria-checked', 'true')
    expect(within(grupo).getByRole('radio', { name: 'Día' })).toHaveAttribute('aria-checked', 'false')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('optifull-theme')).toBe('dark')

    await user.click(within(grupo).getByRole('radio', { name: 'Día' }))
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(within(grupo).getByRole('radio', { name: 'Día' })).toHaveClass('on')
  })

  test('no hay pestaña de Cámaras', () => {
    abrir()
    expect([...document.querySelectorAll('.settings-nav a')].map((a) => a.textContent))
      .toEqual(['General', 'Umbrales de alertas', 'Notificaciones', 'Usuarios y roles'])
    expect(screen.queryByText('RTSP')).toBeNull()
  })

  test('carga los umbrales, la sucursal y push guardados en el servidor', async () => {
    const { user } = abrir({ 'GET /api/configuracion': {
      umbrales: { wait: 2.5 }, sucursal: { nombre: 'Local Centro', direccion: 'Calle 1', horario: '08 – 20' }, push: false,
    } })
    expect(await screen.findByDisplayValue('Local Centro')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Calle 1')).toBeInTheDocument()
    await user.click(pestaña('Umbrales de alertas'))
    expect(screen.getAllByRole('slider').map((s) => s.value)).toEqual(['2.5'])
    await user.click(pestaña('Notificaciones'))
    expect(screen.getByRole('switch', { name: 'Notificaciones push' })).toHaveAttribute('aria-checked', 'false')
  })

  test('umbrales: solo la espera máxima (minutos), sin cola; rango y campo numérico van juntos', async () => {
    const { user } = abrir()
    await user.click(pestaña('Umbrales de alertas'))
    const sliders = screen.getAllByRole('slider')
    expect(sliders).toHaveLength(1)
    expect(sliders[0]).toHaveValue('4')
    expect(sliders[0]).toHaveAttribute('min', '1')
    expect(sliders[0]).toHaveAttribute('step', '0.5')
    expect(sliders[0]).toHaveAttribute('max', '15')
    for (const quitado of ['Cola máxima por caja', 'Densidad máxima', 'Confianza mínima del modelo', 'Stock mínimo en góndola']) {
      expect(screen.queryByText(quitado)).toBeNull()
    }

    const espera = screen.getByRole('spinbutton', { name: 'Espera máxima (min)' })
    expect(screen.queryByText('seg')).toBeNull()
    fireEvent.change(espera, { target: { value: '6.5' } })
    expect(screen.getByRole('slider', { name: 'Espera máxima' })).toHaveValue('6.5')
    fireEvent.change(sliders[0], { target: { value: '7' } })
    expect(espera).toHaveValue(7)

    // Al salir del campo, un valor fuera de rango o fuera de paso se ajusta
    fireEvent.change(espera, { target: { value: '50' } })
    fireEvent.blur(espera)
    expect(espera).toHaveValue(15)
    fireEvent.change(espera, { target: { value: '2.3' } })
    fireEvent.blur(espera)
    expect(espera).toHaveValue(2.5)

    // El valor sobrevive a cambiar de pestaña y volver
    await user.click(pestaña('General'))
    await user.click(pestaña('Umbrales de alertas'))
    expect(screen.getByRole('slider')).toHaveValue('2.5')
  })

  test('umbrales: guardar con el campo vacío avisa y no confirma', async () => {
    const { user, api } = abrir()
    await user.click(pestaña('Umbrales de alertas'))
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Espera máxima (min)' }), { target: { value: '' } })
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(toasts()).toEqual(['La espera máxima debe estar entre 1 y 15'])
    expect(document.querySelector('.toast')).toHaveClass('toast-warn')
    expect(api.pedidos.some((p) => p.metodo === 'PUT')).toBe(false)
  })

  test('umbralValido respeta rango y paso', () => {
    expect(Object.keys(LIMITES_UMBRALES)).toEqual(['wait'])
    expect(LIMITES_UMBRALES.wait).toEqual({ min: 1, max: 15, step: 0.5 })
    expect(umbralValido('wait', 1)).toBe(true)
    expect(umbralValido('wait', 15)).toBe(true)
    expect(umbralValido('wait', 4.5)).toBe(true)
    expect(umbralValido('wait', 0.5)).toBe(false)
    expect(umbralValido('wait', 4.2)).toBe(false)
    expect(umbralValido('wait', NaN)).toBe(false)
    expect(umbralValido('wait', '4')).toBe(false)
  })

  test('notificaciones: solo push, sin Email ni Telegram, y el interruptor la alterna', async () => {
    const { user } = abrir()
    await user.click(pestaña('Notificaciones'))
    expect(screen.queryByText('Email')).toBeNull()
    expect(screen.queryByText('Telegram')).toBeNull()
    const sw = screen.getByRole('switch', { name: 'Notificaciones push' })
    expect(sw).toHaveAttribute('aria-checked', 'true')
    expect(sw.style.background).toBe('var(--pos-soft)')
    await user.click(sw)
    expect(sw).toHaveAttribute('aria-checked', 'false')
    expect(sw.style.background).toBe('var(--bg-1)')
  })

  test('usuarios: lista con rol y nivel; editar e invitar avisan con un toast', async () => {
    const { user } = abrir()
    await user.click(pestaña('Usuarios y roles'))
    const nombres = ['Agostina Blasón', 'Arnon Daniel Nahmias', 'Paulina Ortiz', 'Henry Martinez']
    for (const n of nombres) expect(screen.getByText(n)).toBeInTheDocument()
    expect(screen.getByText('Visualizador YPF')).toBeInTheDocument()
    expect(screen.getByText('owner')).toBeInTheDocument()
    expect(screen.getAllByText('admin')).toHaveLength(2)
    expect(screen.getByText('viewer')).toBeInTheDocument()
    expect(screen.getByText('AB')).toHaveClass('avatar')

    const fila = screen.getByText('Paulina Ortiz').parentElement.parentElement
    await user.click(within(fila).getByRole('button'))
    expect(toasts()).toEqual(['Editando permisos de Paulina Ortiz'])

    await user.click(screen.getByRole('button', { name: '+ Invitar usuario' }))
    expect(toasts()).toContain('Invitar usuario · próximamente')
  })

  test('"Guardar cambios" manda todo al servidor y confirma con un toast de éxito', async () => {
    const { user, api } = abrir({ 'PUT /api/configuracion': (req) => ({ json: req.cuerpo }) })
    fireEvent.change(screen.getByDisplayValue('Strumia — Mendoza'), { target: { value: 'Sucursal Norte' } })
    await user.click(pestaña('Umbrales de alertas'))
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Espera máxima (min)' }), { target: { value: '6' } })
    await user.click(pestaña('Notificaciones'))
    await user.click(screen.getByRole('switch', { name: 'Notificaciones push' }))
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(toasts()).toEqual(['Cambios guardados']))
    expect(document.querySelector('.toast')).toHaveClass('toast-success')
    const put = api.pedidos.find((p) => p.metodo === 'PUT')
    expect(put.ruta).toBe('/api/configuracion')
    expect(put.cuerpo).toEqual({
      umbrales: { wait: 6 },
      sucursal: { nombre: 'Sucursal Norte', direccion: 'Av. San Martín 1234', horario: '06:00 – 22:00' },
      push: false,
    })
  })

  test('si el servidor rechaza el guardado avisa con el motivo', async () => {
    const { user } = abrir({ 'PUT /api/configuracion': { status: 503, json: { error: 'sin conexion a la base de datos' } } })
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await waitFor(() => expect(toasts()).toEqual(['No se pudieron guardar los cambios: sin conexion a la base de datos']))
    expect(document.querySelector('.toast')).toHaveClass('toast-warn')
  })

  test('no deja guardar la sucursal con el nombre vacío', async () => {
    const { user, api } = abrir()
    fireEvent.change(screen.getByDisplayValue('Strumia — Mendoza'), { target: { value: '  ' } })
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(toasts()).toEqual(['El nombre de la sucursal no puede quedar vacío'])
    expect(api.pedidos.some((p) => p.metodo === 'PUT')).toBe(false)
  })
})

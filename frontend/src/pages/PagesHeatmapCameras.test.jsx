// Pruebas de la página de Configuración (SettingsPage): pestañas, apariencia, umbrales, notificaciones y usuarios.
import { describe, test, expect, beforeEach } from 'vitest'
import { render, screen, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '../components/Toast'
import { setTema } from '../components/useTheme'
import { apiFalsa } from '../test/apiFalsa.js'
import { SettingsPage, LIMITES_UMBRALES, umbralValido } from './PagesHeatmapCameras'

function abrir() {
  const api = apiFalsa({})
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
  test('arranca en General con la sucursal y el sistema, y no pide nada al servidor', () => {
    const { api } = abrir()
    expect(screen.getByRole('heading', { name: 'Configuración' })).toBeInTheDocument()
    expect(pestaña('General')).toHaveClass('active')
    expect(screen.getByDisplayValue('Strumia — Mendoza')).toBeInTheDocument()
    expect(screen.getByDisplayValue('YOLOv8m')).toBeDisabled()
    expect(screen.getByDisplayValue('YOLOv8m').closest('.form-field')).toHaveClass('ro')
    expect(screen.getByDisplayValue('3')).toBeEnabled()
    expect(screen.getByDisplayValue('3').closest('.form-field')).not.toHaveClass('ro')
    expect(screen.getByDisplayValue('OptiFull v0.3.0')).toHaveClass('mono')
    expect(api.pedidos).toHaveLength(0)
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

  test('cámaras: la pestaña es de solo lectura, ningún parámetro se puede editar', async () => {
    const { user } = abrir()
    await user.click(pestaña('Cámaras'))
    expect(pestaña('Cámaras')).toHaveClass('active')
    expect(pestaña('General')).not.toHaveClass('active')
    expect(screen.getByText('Configuración global de cámaras')).toBeInTheDocument()
    expect(screen.getByText(/Solo lectura/)).toBeInTheDocument()
    for (const valor of ['RTSP', 'nvr.local:554', 'H.264', '1280×720']) {
      expect(screen.getByDisplayValue(valor)).toBeDisabled()
      expect(screen.getByDisplayValue(valor).closest('.form-field')).toHaveClass('ro')
    }
    expect(document.querySelectorAll('.panel input:not(:disabled)')).toHaveLength(0)
    expect(screen.queryByText('Sucursal')).toBeNull()
  })

  test('umbrales: solo cola (personas) y espera (minutos); rango y campo numérico van juntos', async () => {
    const { user } = abrir()
    await user.click(pestaña('Umbrales de alertas'))
    const sliders = screen.getAllByRole('slider')
    expect(sliders).toHaveLength(2)
    expect(sliders.map((s) => s.value)).toEqual(['4', '4'])
    expect(sliders[0]).toHaveAttribute('min', '1')
    expect(sliders[0]).toHaveAttribute('max', '20')
    expect(sliders[1]).toHaveAttribute('step', '0.5')
    expect(sliders[1]).toHaveAttribute('max', '15')
    for (const quitado of ['Densidad máxima', 'Confianza mínima del modelo', 'Stock mínimo en góndola']) {
      expect(screen.queryByText(quitado)).toBeNull()
    }

    const cola = screen.getByRole('spinbutton', { name: 'Cola máxima por caja (personas)' })
    const espera = screen.getByRole('spinbutton', { name: 'Espera máxima (min)' })
    expect(screen.queryByText('seg')).toBeNull()

    fireEvent.change(sliders[0], { target: { value: '7' } })
    expect(cola).toHaveValue(7)
    fireEvent.change(espera, { target: { value: '6.5' } })
    expect(screen.getByRole('slider', { name: 'Espera máxima' })).toHaveValue('6.5')

    // Al salir del campo, un valor fuera de rango o fuera de paso se ajusta
    fireEvent.change(cola, { target: { value: '50' } })
    fireEvent.blur(cola)
    expect(cola).toHaveValue(20)
    fireEvent.change(espera, { target: { value: '2.3' } })
    fireEvent.blur(espera)
    expect(espera).toHaveValue(2.5)

    // Los valores sobreviven a cambiar de pestaña y volver
    await user.click(pestaña('General'))
    await user.click(pestaña('Umbrales de alertas'))
    expect(screen.getAllByRole('slider').map((s) => s.value)).toEqual(['20', '2.5'])
  })

  test('umbrales: guardar con un campo vacío avisa y no confirma', async () => {
    const { user } = abrir()
    await user.click(pestaña('Umbrales de alertas'))
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Cola máxima por caja (personas)' }), { target: { value: '' } })
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(toasts()).toEqual(['La cola máxima debe estar entre 1 y 20'])
    expect(document.querySelector('.toast')).toHaveClass('toast-warn')
  })

  test('umbralValido respeta rango y paso', () => {
    expect(LIMITES_UMBRALES.wait).toEqual({ min: 1, max: 15, step: 0.5 })
    expect(umbralValido('queue', 1)).toBe(true)
    expect(umbralValido('queue', 20)).toBe(true)
    expect(umbralValido('queue', 0)).toBe(false)
    expect(umbralValido('queue', 3.5)).toBe(false)
    expect(umbralValido('wait', 4.5)).toBe(true)
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

  test('"Guardar cambios" confirma con un toast de éxito', async () => {
    const { user } = abrir()
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(toasts()).toEqual(['Cambios guardados'])
    expect(document.querySelector('.toast')).toHaveClass('toast-success')
  })
})

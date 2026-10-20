// Pruebas de la página de Configuración (SettingsPage): pestañas, apariencia, umbrales, notificaciones y usuarios.
import { describe, test, expect, beforeEach } from 'vitest'
import { render, screen, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from '../components/Toast'
import { setTema } from '../components/useTheme'
import { apiFalsa } from '../test/apiFalsa.js'
import { SettingsPage } from './PagesHeatmapCameras'

function abrir() {
  const api = apiFalsa({})
  const user = userEvent.setup()
  const utils = render(<ToastProvider><SettingsPage /></ToastProvider>)
  return { api, user, ...utils }
}

const pestaña = (nombre) => screen.getByText(nombre, { selector: '.settings-nav a' })
const toasts = () => [...document.querySelectorAll('.toast > span:last-child')].map((t) => t.textContent)

beforeEach(() => {
  // El tema es estado global del módulo: cada test arranca en Automático.
  setTema('auto')
})

describe('SettingsPage', () => {
  test('arranca en General con la sucursal y el sistema, y no pide nada al servidor', () => {
    const { api } = abrir()
    expect(screen.getByRole('heading', { name: 'Configuración' })).toBeInTheDocument()
    expect(pestaña('General')).toHaveClass('active')
    expect(screen.getByDisplayValue('Strumia — Mendoza')).toBeInTheDocument()
    expect(screen.getByDisplayValue('YOLOv8m')).toHaveAttribute('readonly')
    expect(screen.getByDisplayValue('3')).not.toHaveAttribute('readonly')
    expect(screen.getByDisplayValue('OptiFull v0.3.0')).toHaveClass('mono')
    expect(api.pedidos).toHaveLength(0)
  })

  test('apariencia: Automático por defecto y elegir Noche/Día cambia y guarda el tema', async () => {
    const { user } = abrir()
    const grupo = screen.getByRole('radiogroup', { name: 'Apariencia' })
    expect(within(grupo).getByRole('radio', { name: 'Automático' })).toHaveAttribute('aria-checked', 'true')

    await user.click(within(grupo).getByRole('radio', { name: 'Noche' }))
    expect(within(grupo).getByRole('radio', { name: 'Noche' })).toHaveAttribute('aria-checked', 'true')
    expect(within(grupo).getByRole('radio', { name: 'Automático' })).toHaveAttribute('aria-checked', 'false')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('optifull-theme')).toBe('dark')

    await user.click(within(grupo).getByRole('radio', { name: 'Día' }))
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(within(grupo).getByRole('radio', { name: 'Día' })).toHaveClass('on')
  })

  test('cambiar de pestaña muestra su contenido y marca la activa', async () => {
    const { user } = abrir()
    await user.click(pestaña('Cámaras'))
    expect(pestaña('Cámaras')).toHaveClass('active')
    expect(pestaña('General')).not.toHaveClass('active')
    expect(screen.getByText('Configuración global de cámaras')).toBeInTheDocument()
    expect(screen.getByDisplayValue('RTSP')).toHaveAttribute('readonly')
    expect(screen.getByDisplayValue('nvr.local:554')).not.toHaveAttribute('readonly')
    expect(screen.queryByText('Sucursal')).toBeNull()
  })

  test('umbrales: cada control muestra su valor y unidad, y moverlo actualiza el número', async () => {
    const { user } = abrir()
    await user.click(pestaña('Umbrales de alertas'))
    const sliders = screen.getAllByRole('slider')
    expect(sliders).toHaveLength(5)
    expect(sliders.map((s) => s.value)).toEqual(['4', '240', '1.8', '60', '5'])
    expect(sliders[1]).toHaveAttribute('step', '15')
    expect(sliders[2]).toHaveAttribute('min', '0.5')
    expect(sliders[2]).toHaveAttribute('max', '3')

    fireEvent.change(sliders[0], { target: { value: '7' } })
    fireEvent.change(sliders[2], { target: { value: '2.4' } })
    const fila = (label) => screen.getByText(label).parentElement
    expect(fila('Cola máxima por caja')).toHaveTextContent('7 personas')
    expect(fila('Densidad máxima')).toHaveTextContent('2.4 pers/m²')
    expect(fila('Espera máxima')).toHaveTextContent('240 seg')
    expect(fila('Confianza mínima del modelo')).toHaveTextContent('60 %')

    fireEvent.change(sliders[1], { target: { value: '300' } })
    fireEvent.change(sliders[3], { target: { value: '80' } })
    fireEvent.change(sliders[4], { target: { value: '12' } })
    expect(fila('Espera máxima')).toHaveTextContent('300 seg')
    expect(fila('Confianza mínima del modelo')).toHaveTextContent('80 %')
    expect(fila('Stock mínimo en góndola')).toHaveTextContent('12 unidades')
    // Los valores sobreviven a cambiar de pestaña y volver
    await user.click(pestaña('General'))
    await user.click(pestaña('Umbrales de alertas'))
    expect(screen.getAllByRole('slider').map((s) => s.value)).toEqual(['7', '300', '2.4', '80', '12'])
  })

  test('notificaciones: los interruptores alternan cada canal', async () => {
    const { user } = abrir()
    await user.click(pestaña('Notificaciones'))
    const canal = (nombre) => screen.getByText(nombre).parentElement.parentElement
    const fondo = (nombre) => within(canal(nombre)).getByRole('button').style.background
    expect(fondo('Email')).toBe('var(--pos-soft)')
    expect(fondo('Notificaciones push')).toBe('var(--pos-soft)')
    expect(fondo('Telegram')).toBe('var(--bg-1)')
    expect(screen.getByText(/Canal de equipo @strumia-ops \(próximamente\)/)).toBeInTheDocument()

    await user.click(within(canal('Telegram')).getByRole('button'))
    await user.click(within(canal('Email')).getByRole('button'))
    expect(fondo('Telegram')).toBe('var(--pos-soft)')
    expect(fondo('Email')).toBe('var(--bg-1)')
    expect(fondo('Notificaciones push')).toBe('var(--pos-soft)')
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

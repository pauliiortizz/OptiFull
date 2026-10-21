// Pantalla de inicio de sesion (ver LoginPage.jsx y frontend/api/login.py).
import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LoginPage } from './LoginPage.jsx'
import { leerSesion } from '../components/useSesion.js'
import { apiFalsa } from '../test/apiFalsa.js'
import { conMovimientoReducido } from '../test/movimiento.js'

const DATOS = { ok: true, usuario: 'ana', nombre: 'Ana Pérez', email: 'ana@tienda.com', rol: 'administrador', cargo: 'dueno', sucursales: [1] }
const CLAVE = 'optifull-sesion'

function pantalla() {
  const props = { onLogin: vi.fn(), onBack: vi.fn(), onDemo: vi.fn() }
  render(<LoginPage {...props} />)
  return {
    ...props,
    usuario: screen.getByLabelText('Email o usuario'),
    clave: screen.getByLabelText('Contraseña'),
    mantener: screen.getByRole('checkbox', { name: 'Mantener sesión iniciada' }),
    ingresar: () => screen.getByRole('button', { name: /Ingres/ }),
  }
}

async function completar(p, usuario = 'ana', clave = 'secreta') {
  if (usuario) await userEvent.type(p.usuario, usuario)
  if (clave) await userEvent.type(p.clave, clave)
}

// tras un ingreso correcto se espera la animación del botón; con movimiento reducido, no
conMovimientoReducido()

describe('LoginPage', () => {
  let api
  beforeEach(() => { api = apiFalsa({ 'POST /api/login': DATOS }) })

  test('muestra el formulario con el foco en el usuario y "mantener" marcado', () => {
    const p = pantalla()
    expect(screen.getByRole('heading', { name: 'Iniciá sesión' })).toBeInTheDocument()
    expect(p.usuario).toHaveFocus()
    expect(p.mantener).toBeChecked()
    expect(p.clave).toHaveAttribute('type', 'password')
  })

  test('con los campos vacios avisa por campo y no llama al servidor', async () => {
    const p = pantalla()
    await userEvent.click(p.ingresar())
    expect(screen.getByText('Completá el usuario o el email.')).toBeInTheDocument()
    expect(screen.getByText('Completá la contraseña.')).toBeInTheDocument()
    expect(p.usuario).toHaveAttribute('aria-invalid', 'true')
    expect(p.usuario).toHaveAccessibleDescription('Completá el usuario o el email.')
    expect(p.usuario).toHaveFocus()
    expect(api.pedidos).toHaveLength(0)
  })

  test('un usuario de solo espacios cuenta como vacio', async () => {
    const p = pantalla()
    await completar(p, '   ', 'x')
    await userEvent.click(p.ingresar())
    expect(screen.getByText('Completá el usuario o el email.')).toBeInTheDocument()
    expect(screen.queryByText('Completá la contraseña.')).not.toBeInTheDocument()
    expect(api.pedidos).toHaveLength(0)
  })

  test('si falta solo la contraseña lleva el foco ahi, y el aviso se va al escribir', async () => {
    const p = pantalla()
    await completar(p, 'ana', '')
    await userEvent.click(p.ingresar())
    expect(p.clave).toHaveFocus()
    expect(screen.getByRole('alert')).toHaveTextContent('Completá la contraseña.')
    await userEvent.type(p.clave, 'x')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(p.clave).toHaveAttribute('aria-invalid', 'false')
  })

  test('el ojito muestra y oculta la contraseña', async () => {
    const p = pantalla()
    await userEvent.click(screen.getByRole('button', { name: 'Mostrar contraseña' }))
    expect(p.clave).toHaveAttribute('type', 'text')
    const ocultar = screen.getByRole('button', { name: 'Ocultar contraseña' })
    expect(ocultar).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(ocultar)
    expect(p.clave).toHaveAttribute('type', 'password')
  })

  test('al ingresar manda usuario (sin espacios), clave y "mantener", y guarda la sesion en localStorage', async () => {
    const p = pantalla()
    await completar(p, '  ana  ', 'secreta')
    await userEvent.click(p.ingresar())
    await waitFor(() => expect(p.onLogin).toHaveBeenCalledWith(DATOS))
    expect(api.hechos('/api/login', 'POST')[0].cuerpo).toEqual({ usuario: 'ana', clave: 'secreta', mantener: true })
    expect(JSON.parse(localStorage.getItem(CLAVE))).toMatchObject({ usuario: 'ana', rol: 'administrador' })
    expect(sessionStorage.getItem(CLAVE)).toBeNull()
    expect(leerSesion()).toMatchObject({ nombre: 'Ana Pérez' })
  })

  test('sin "mantener" la sesion queda solo en sessionStorage', async () => {
    const p = pantalla()
    await userEvent.click(p.mantener)
    await completar(p)
    await userEvent.click(p.ingresar())
    await waitFor(() => expect(p.onLogin).toHaveBeenCalled())
    expect(api.pedidos[0].cuerpo.mantener).toBe(false)
    expect(localStorage.getItem(CLAVE)).toBeNull()
    expect(JSON.parse(sessionStorage.getItem(CLAVE))).toMatchObject({ usuario: 'ana' })
  })

  test('mientras espera la respuesta el boton queda deshabilitado', async () => {
    let soltar
    apiFalsa({ 'POST /api/login': () => new Promise((r) => { soltar = () => r({ json: DATOS }) }) })
    const p = pantalla()
    await completar(p)
    await userEvent.click(p.ingresar())
    expect(screen.getByRole('button', { name: 'Ingresando…' })).toBeDisabled()
    soltar()
    // al confirmarse el ingreso el botón muestra «¡Listo!» (sigue deshabilitado) y se pasa al panel
    expect(await screen.findByRole('button', { name: '¡Listo!' })).toBeDisabled()
    await waitFor(() => expect(p.onLogin).toHaveBeenCalled())
  })

  test.each([
    [401, 'El email, el usuario o la contraseña son incorrectos.'],
    [429, 'Demasiados intentos fallidos. Probá de nuevo en 5 minutos.'],
    [503, 'No se pudo conectar con el servidor. Probá de nuevo en un momento.'],
  ])('un %i muestra el mensaje del servidor y no guarda sesion', async (status, error) => {
    apiFalsa({ 'POST /api/login': { status, json: { ok: false, error } } })
    const p = pantalla()
    await completar(p)
    await userEvent.click(p.ingresar())
    expect(await screen.findByRole('alert')).toHaveTextContent(error)
    expect(p.onLogin).not.toHaveBeenCalled()
    expect(leerSesion()).toBeNull()
    // Al corregir el campo el aviso general desaparece.
    await userEvent.type(p.clave, 'x')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('un 400 con errores por campo los muestra en cada campo', async () => {
    apiFalsa({ 'POST /api/login': { status: 400, json: { ok: false, error: 'x', campos: { clave: 'Completá la contraseña.' } } } })
    const p = pantalla()
    await completar(p)
    await userEvent.click(p.ingresar())
    expect(await screen.findByText('Completá la contraseña.')).toHaveAttribute('id', 'login-clave-error')
  })

  test('un error sin mensaje muestra uno generico', async () => {
    apiFalsa({ 'POST /api/login': { status: 500, json: {} } })
    const p = pantalla()
    await completar(p)
    await userEvent.click(p.ingresar())
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo iniciar sesión.')
  })

  test('un 200 sin ok tampoco deja entrar', async () => {
    apiFalsa({ 'POST /api/login': { ok: false, error: 'Cuenta desactivada' } })
    const p = pantalla()
    await completar(p)
    await userEvent.click(p.ingresar())
    expect(await screen.findByRole('alert')).toHaveTextContent('Cuenta desactivada')
    expect(p.onLogin).not.toHaveBeenCalled()
  })

  test('sin conexion (o respuesta que no es JSON) avisa que no se pudo conectar', async () => {
    apiFalsa({ 'POST /api/login': new TypeError('Failed to fetch') })
    const p = pantalla()
    await completar(p)
    await userEvent.click(p.ingresar())
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo conectar con el servidor.')
    expect(screen.getByRole('button', { name: 'Ingresar' })).toBeEnabled()
  })

  test('los botones de volver y pedir demo avisan al padre', async () => {
    const p = pantalla()
    await userEvent.click(screen.getByRole('button', { name: '← Volver al inicio' }))
    await userEvent.click(screen.getByRole('button', { name: 'Pedí una demo' }))
    expect(p.onBack).toHaveBeenCalledTimes(1)
    expect(p.onDemo).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: /Cambiar a modo/ })).toBeInTheDocument()
  })
})

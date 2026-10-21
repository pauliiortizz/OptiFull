// Sesion guardada en el navegador y vigilancia de 401 de la API (ver useSesion.js).
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { leerSesion, guardarSesion, borrarSesion, vigilarSesion, EVENTO_SESION_VENCIDA } from './useSesion.js'
import { apiFalsa } from '../test/apiFalsa.js'

const CLAVE = 'optifull-sesion'
const ADMIN = { usuario: 'ana', nombre: 'Ana Pérez', rol: 'administrador' }

describe('leerSesion / guardarSesion / borrarSesion', () => {
  test('sin nada guardado no hay sesion', () => {
    expect(leerSesion()).toBeNull()
  })

  test('con "mantener" se guarda en localStorage y se recupera', () => {
    guardarSesion(ADMIN, true)
    expect(JSON.parse(localStorage.getItem(CLAVE))).toMatchObject(ADMIN)
    expect(sessionStorage.getItem(CLAVE)).toBeNull()
    expect(leerSesion()).toMatchObject(ADMIN)
  })

  test('sin "mantener" se guarda solo en sessionStorage', () => {
    guardarSesion({ ...ADMIN, rol: 'usuario' }, false)
    expect(localStorage.getItem(CLAVE)).toBeNull()
    expect(leerSesion()).toMatchObject({ usuario: 'ana', rol: 'usuario' })
  })

  test('guarda la marca de tiempo del inicio de sesion', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1234)
    guardarSesion(ADMIN, true)
    expect(leerSesion().ts).toBe(1234)
  })

  test('una sesion vieja del modo demo (sin rol) se descarta y se borra', () => {
    localStorage.setItem(CLAVE, JSON.stringify({ usuario: 'demo' }))
    sessionStorage.setItem(CLAVE, JSON.stringify({ usuario: 'x', rol: 'admin' }))
    expect(leerSesion()).toBeNull()
    expect(localStorage.getItem(CLAVE)).toBeNull()
    expect(sessionStorage.getItem(CLAVE)).toBeNull()
  })

  test('un valor dañado no rompe la app', () => {
    localStorage.setItem(CLAVE, '{no es json')
    sessionStorage.setItem(CLAVE, JSON.stringify(ADMIN))
    expect(leerSesion()).toMatchObject(ADMIN)
  })

  test('si el almacenamiento lanza (ventana privada) no hay sesion y nada explota', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloqueado') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloqueado') })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('bloqueado') })
    expect(() => guardarSesion(ADMIN, true)).not.toThrow()
    expect(leerSesion()).toBeNull()
    expect(() => borrarSesion()).not.toThrow()
  })

  test('borrarSesion limpia los dos almacenes', () => {
    localStorage.setItem(CLAVE, JSON.stringify(ADMIN))
    sessionStorage.setItem(CLAVE, JSON.stringify(ADMIN))
    localStorage.setItem('optifull-theme', 'dark')
    borrarSesion()
    expect(localStorage.getItem(CLAVE)).toBeNull()
    expect(sessionStorage.getItem(CLAVE)).toBeNull()
    expect(localStorage.getItem('optifull-theme')).toBe('dark')
  })
})

describe('vigilarSesion', () => {
  let api, vencida
  beforeEach(() => {
    delete window.__optifullVigilaSesion
    api = apiFalsa({
      '/api/stats': { status: 401, json: { error: 'sesion vencida' } },
      'POST /api/login': { status: 401, json: { ok: false, error: 'Contraseña incorrecta' } },
      '/api/health': { db: 'ok' },
      '/otra/cosa': { status: 401, json: {} },
    })
    vencida = vi.fn()
    window.addEventListener(EVENTO_SESION_VENCIDA, vencida)
    vigilarSesion()
  })
  afterEach(() => {
    window.removeEventListener(EVENTO_SESION_VENCIDA, vencida)
    delete window.__optifullVigilaSesion
  })

  test('un 401 de la API avisa que la sesion vencio y devuelve la respuesta igual', async () => {
    const r = await window.fetch('/api/stats?desde=2026-01-01')
    expect(r.status).toBe(401)
    expect(vencida).toHaveBeenCalledTimes(1)
  })

  test('tambien con un Request en vez de un string', async () => {
    await window.fetch(new Request('http://localhost/api/stats'))
    expect(vencida).toHaveBeenCalledTimes(1)
  })

  test('un 401 de /api/login es contraseña incorrecta, no sesion vencida', async () => {
    const r = await window.fetch('/api/login', { method: 'POST', body: '{}' })
    expect(r.status).toBe(401)
    expect(vencida).not.toHaveBeenCalled()
    expect(api.hechos('/api/login', 'POST')).toHaveLength(1)
  })

  test('respuestas OK o 401 fuera de /api/ no avisan', async () => {
    await window.fetch('/api/health')
    await window.fetch('/otra/cosa')
    expect(vencida).not.toHaveBeenCalled()
  })

  test('llamarla dos veces no envuelve fetch dos veces', async () => {
    const envuelto = window.fetch
    vigilarSesion()
    expect(window.fetch).toBe(envuelto)
    await window.fetch('/api/stats')
    expect(vencida).toHaveBeenCalledTimes(1)
  })
})

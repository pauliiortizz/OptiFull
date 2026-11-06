// Pruebas de src/push.js: activar, probar y desactivar las notificaciones push en este navegador (ver
// frontend/api/push.py y public/sw.js). El navegador se simula con pushFalso y la API con apiFalsa.
import { describe, test, expect, afterEach } from 'vitest'
import { apiFalsa } from './test/apiFalsa.js'
import { pushFalso } from './test/pushFalso.js'
import { activarPush, claveABytes, desactivarPush, estadoPush, probarPush, pushSoportado } from './push.js'

let nav
afterEach(() => nav?.desinstalar())

const API = { 'GET /api/push/clave': { clave: 'BAEC' }, 'POST /api/push/suscripcion': { status: 201, json: { ok: true } },
              'DELETE /api/push/suscripcion': { ok: true }, 'POST /api/push/prueba': { ok: true } }

describe('push.js', () => {
  test('sin service worker ni PushManager no está soportado', async () => {
    expect(pushSoportado()).toBe(false)
    expect(await estadoPush()).toBe('no_soportado')
    await expect(activarPush()).rejects.toThrow('no admite notificaciones push')
  })

  test('la clave VAPID en base64url se pasa a bytes', () => {
    expect(Array.from(claveABytes('BAEC'))).toEqual([4, 1, 2])
    expect(Array.from(claveABytes('-_8'))).toEqual([251, 255])
  })

  test('activar: pide permiso, registra el service worker, se suscribe con la clave y la guarda en el servidor', async () => {
    nav = pushFalso()
    const api = apiFalsa(API)
    expect(await estadoPush()).toBe('inactivo')
    await activarPush()
    expect(nav.Notification.requestPermission).toHaveBeenCalled()
    expect(nav.registros).toEqual(['/sw.js'])
    expect(nav.registro.pushManager.subscribe).toHaveBeenCalledWith(
      { userVisibleOnly: true, applicationServerKey: new Uint8Array([4, 1, 2]) })
    const guardado = api.pedidos.find((p) => p.metodo === 'POST' && p.ruta === '/api/push/suscripcion')
    expect(guardado.cuerpo).toEqual({ endpoint: nav.suscripcion.endpoint, keys: { p256dh: 'BPclave', auth: 'secreto' } })
    expect(await estadoPush()).toBe('activo')
  })

  test('si el usuario bloquea el permiso no se suscribe y explica cómo habilitarlo', async () => {
    nav = pushFalso({ respuestaPermiso: 'denied' })
    const api = apiFalsa(API)
    await expect(activarPush()).rejects.toThrow('bloqueadas para este sitio')
    expect(nav.suscripcion).toBeNull()
    expect(api.pedidos).toEqual([])
    expect(await estadoPush()).toBe('bloqueado')
  })

  test('si el servidor no tiene las claves configuradas avisa con su mensaje', async () => {
    nav = pushFalso()
    apiFalsa({ 'GET /api/push/clave': { status: 503, json: { error: 'Las notificaciones push no están configuradas en el servidor.' } } })
    await expect(activarPush()).rejects.toThrow('no están configuradas en el servidor')
    expect(nav.suscripcion).toBeNull()
  })

  test('probar: pide la notificación de prueba para este navegador', async () => {
    nav = pushFalso({ permiso: 'granted', suscripto: true })
    const api = apiFalsa(API)
    await probarPush()
    expect(api.pedidos.at(-1)).toMatchObject({ metodo: 'POST', ruta: '/api/push/prueba', cuerpo: { endpoint: nav.suscripcion.endpoint } })
  })

  test('probar sin estar suscripto pide activar primero', async () => {
    nav = pushFalso({ permiso: 'granted' })
    await expect(probarPush()).rejects.toThrow('Primero activá')
  })

  test('desactivar: borra la suscripción del servidor y del navegador', async () => {
    nav = pushFalso({ permiso: 'granted', suscripto: true })
    const api = apiFalsa(API)
    const endpoint = nav.suscripcion.endpoint
    await desactivarPush()
    expect(api.pedidos).toMatchObject([{ metodo: 'DELETE', ruta: '/api/push/suscripcion', cuerpo: { endpoint } }])
    expect(nav.suscripcion).toBeNull()
    expect(await estadoPush()).toBe('inactivo')
  })
})

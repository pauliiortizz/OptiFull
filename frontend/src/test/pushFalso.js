// Navegador falso con Web Push para los tests (jsdom no tiene service workers ni notificaciones): instala
// navigator.serviceWorker, PushManager y Notification, y deja ver que se registro y a que se suscribio.
//
//   const nav = pushFalso({ permiso: 'default', respuestaPermiso: 'granted' })
//   nav.suscripcion   -> la suscripcion actual (null si no hay)
//   nav.registros     -> URLs de service worker registradas
//   nav.desinstalar() -> deja el navegador como estaba
import { vi } from 'vitest'

export function pushFalso({ permiso = 'default', respuestaPermiso = 'granted', registrado = false, suscripto = false } = {}) {
  const estado = { permiso, suscripcion: null, registros: [], oyentes: new Set() }

  const crearSuscripcion = (opciones) => {
    const sub = {
      endpoint: 'https://fcm.googleapis.com/fcm/send/navegador-de-prueba',
      opciones,
      toJSON: () => ({ endpoint: sub.endpoint, keys: { p256dh: 'BPclave', auth: 'secreto' } }),
      unsubscribe: vi.fn(async () => { estado.suscripcion = null; return true }),
    }
    return sub
  }
  if (suscripto) estado.suscripcion = crearSuscripcion({})

  const registro = {
    pushManager: {
      getSubscription: async () => estado.suscripcion,
      subscribe: vi.fn(async (opciones) => { estado.suscripcion = crearSuscripcion(opciones); return estado.suscripcion }),
    },
  }
  let hayRegistro = registrado || suscripto
  const serviceWorker = {
    getRegistration: async () => (hayRegistro ? registro : undefined),
    register: vi.fn(async (url) => { estado.registros.push(url); hayRegistro = true; return registro }),
    ready: Promise.resolve(registro),
    addEventListener: (tipo, f) => { if (tipo === 'message') estado.oyentes.add(f) },
    removeEventListener: (tipo, f) => { if (tipo === 'message') estado.oyentes.delete(f) },
  }
  const Notification = {
    get permission() { return estado.permiso },
    requestPermission: vi.fn(async () => { estado.permiso = respuestaPermiso; return respuestaPermiso }),
  }

  const previo = { sw: Object.getOwnPropertyDescriptor(navigator, 'serviceWorker'), pm: window.PushManager,
                   n: window.Notification }
  Object.defineProperty(navigator, 'serviceWorker', { value: serviceWorker, configurable: true })
  window.PushManager = function PushManager() {}
  window.Notification = Notification

  return {
    get suscripcion() { return estado.suscripcion },
    get registros() { return estado.registros },
    registro, Notification,
    // Simula un mensaje del service worker (clic en una notificacion con OptiFull abierto)
    mensaje: (data) => estado.oyentes.forEach((f) => f({ data })),
    desinstalar() {
      if (previo.sw) Object.defineProperty(navigator, 'serviceWorker', previo.sw)
      else delete navigator.serviceWorker
      window.PushManager = previo.pm
      window.Notification = previo.n
      if (previo.pm === undefined) delete window.PushManager
      if (previo.n === undefined) delete window.Notification
    },
  }
}

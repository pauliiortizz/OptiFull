// Sesión de la pantalla de inicio de sesión (ver LoginPage.jsx y /api/login). Se guarda en localStorage si la
// persona eligió "Mantener sesión iniciada" y en sessionStorage si no (se pierde al cerrar la pestaña). Todo está
// envuelto en try/catch: en ventanas privadas o con el almacenamiento bloqueado puede lanzar.
const CLAVE = 'optifull-sesion'

export function leerSesion() {
  for (const almacen of ['localStorage', 'sessionStorage']) {
    try {
      const v = JSON.parse(window[almacen].getItem(CLAVE) || 'null')
      // Solo vale una sesión creada por el login real (trae el rol). Las del modo demo anterior, que solo
      // guardaban el nombre de usuario, se descartan para que se vuelva a pedir el inicio de sesión.
      if (v && v.usuario && (v.rol === 'administrador' || v.rol === 'usuario')) return v
      if (v) window[almacen].removeItem(CLAVE)
    } catch { /* sin almacenamiento o valor dañado */ }
  }
  return null
}

// 'datos' es lo que devuelve /api/login: { usuario, nombre, email, rol, cargo, sucursales }.
export function guardarSesion(datos, mantener) {
  const valor = JSON.stringify({ ...datos, ts: Date.now() })
  try { (mantener ? window.localStorage : window.sessionStorage).setItem(CLAVE, valor) } catch { /* sin almacenamiento */ }
}

export function borrarSesion() {
  for (const almacen of ['localStorage', 'sessionStorage']) {
    try { window[almacen].removeItem(CLAVE) } catch { /* sin almacenamiento */ }
  }
}

// La sesión la valida el servidor con una cookie (ver frontend/api/sesion.py): lo guardado acá solo sirve para
// mostrar el nombre y el rol. Si el servidor responde 401 a un pedido de la API (la cookie venció, se cerró
// la sesión en otro lado o es una sesión guardada antes de que existiera la cookie), se avisa con este evento
// y la app vuelve al inicio de sesión. /api/login queda afuera: ahí un 401 es "contraseña incorrecta".
export const EVENTO_SESION_VENCIDA = 'optifull:sesion-vencida'

export function vigilarSesion() {
  if (window.__optifullVigilaSesion) return
  window.__optifullVigilaSesion = true
  const fetchOriginal = window.fetch.bind(window)
  window.fetch = async (recurso, opciones) => {
    const respuesta = await fetchOriginal(recurso, opciones)
    const url = typeof recurso === 'string' ? recurso : recurso?.url || ''
    const ruta = new URL(url, window.location.origin).pathname
    if (respuesta.status === 401 && ruta.startsWith('/api/') && ruta !== '/api/login') {
      window.dispatchEvent(new Event(EVENTO_SESION_VENCIDA))
    }
    return respuesta
  }
}

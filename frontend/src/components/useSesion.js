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

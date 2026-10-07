// Permisos por rol (el rol viene de /api/login, ver frontend/api/login.py y la tabla 'roles').
//   administrador (dueño y gerente): todas las secciones del panel.
//   usuario (empleado): solo Stock y Alertas.
// OJO: esto controla lo que se MUESTRA en el panel; los endpoints /api/* todavía no verifican el rol.
export const PAGINAS_POR_ROL = {
  administrador: ['dashboard', 'stock', 'productos', 'reports', 'alerts', 'settings'],
  usuario: ['stock', 'alerts'],
}

// Sección con la que arranca cada rol al iniciar sesión.
const PAGINA_INICIAL = { administrador: 'dashboard', usuario: 'stock' }

// Un rol desconocido (o ninguno) no tiene acceso a nada: mejor negar que dejar pasar.
export function paginasPermitidas(rol) {
  return PAGINAS_POR_ROL[rol] || []
}

export function puedeVer(rol, pagina) {
  return paginasPermitidas(rol).includes(pagina)
}

export function paginaInicial(rol) {
  return PAGINA_INICIAL[rol] || 'stock'
}

// Si 'pagina' no está permitida para el rol, devuelve la sección inicial de ese rol.
export function paginaPermitida(rol, pagina) {
  return puedeVer(rol, pagina) ? pagina : paginaInicial(rol)
}

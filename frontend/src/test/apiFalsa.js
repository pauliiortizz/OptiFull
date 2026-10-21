// API falsa para los tests: reemplaza window.fetch y responde segun la URL, como BDFalsa en los tests de Python.
//
//   const api = apiFalsa({
//     'GET /api/stats': { total: 3 },                     // JSON con status 200
//     'POST /api/login': { status: 401, json: {...} },    // status y cuerpo a mano
//     '/api/alertas': (req) => ({ json: [...] }),         // funcion: recibe { url, metodo, cuerpo }
//   })
//   api.pedidos  -> lista de { url, metodo, cuerpo } en el orden en que se hicieron
//
// La clave puede llevar metodo o no; se compara contra el pathname (sin query) y si no hay coincidencia exacta,
// contra el prefijo mas largo. Una URL sin regla responde 404 (asi un pedido inesperado no pasa desapercibido).
import { vi } from 'vitest'

function respuesta(valor) {
  const r = valor && typeof valor === 'object' && ('status' in valor || 'json' in valor || 'texto' in valor || 'blob' in valor)
    ? valor : { json: valor }
  const status = r.status ?? 200
  const cuerpo = r.texto ?? (r.json === undefined ? '' : JSON.stringify(r.json))
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(r.headers || { 'Content-Type': r.texto ? 'text/plain' : 'application/json' }),
    json: async () => (r.json !== undefined ? structuredClone(r.json) : JSON.parse(cuerpo)),
    text: async () => cuerpo,
    blob: async () => r.blob || new Blob([cuerpo]),
    clone() { return respuesta(valor) },
  }
}

export function apiFalsa(reglas = {}) {
  const pedidos = []
  const buscar = (metodo, ruta) => {
    for (const clave of [`${metodo} ${ruta}`, ruta]) if (clave in reglas) return reglas[clave]
    let mejor = null
    for (const clave of Object.keys(reglas)) {
      const [m, r] = clave.includes(' ') ? clave.split(' ') : [null, clave]
      if ((m === null || m === metodo) && ruta.startsWith(r) && (!mejor || r.length > mejor[0].length)) mejor = [r, reglas[clave]]
    }
    return mejor ? mejor[1] : undefined
  }
  const fetch = vi.fn(async (recurso, opciones = {}) => {
    const url = typeof recurso === 'string' ? recurso : recurso.url
    const u = new URL(url, 'http://localhost')
    const metodo = (opciones.method || 'GET').toUpperCase()
    let cuerpo = opciones.body
    try { cuerpo = cuerpo ? JSON.parse(cuerpo) : cuerpo } catch { /* no era JSON */ }
    const req = { url, ruta: u.pathname, query: Object.fromEntries(u.searchParams), metodo, cuerpo }
    pedidos.push(req)
    let regla = buscar(metodo, u.pathname)
    if (typeof regla === 'function') regla = await regla(req)
    if (regla instanceof Error) throw regla
    if (regla === undefined) return respuesta({ status: 404, json: { error: `sin regla para ${metodo} ${u.pathname}` } })
    return respuesta(regla)
  })
  vi.stubGlobal('fetch', fetch)
  window.fetch = fetch
  return {
    fetch,
    pedidos,
    reglas,
    hechos: (ruta, metodo) => pedidos.filter((p) => p.ruta === ruta && (!metodo || p.metodo === metodo)),
  }
}

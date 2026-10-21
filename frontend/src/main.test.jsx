// Punto de entrada: monta la app en #root y envuelve fetch para detectar la sesion vencida (ver main.jsx).
import { describe, test, expect, vi, afterEach } from 'vitest'
import { screen, act } from '@testing-library/react'
import { apiFalsa } from './test/apiFalsa.js'
import { EVENTO_SESION_VENCIDA } from './components/useSesion.js'

let root
afterEach(() => {
  root?.remove()
  delete window.__optifullVigilaSesion
})

describe('main.jsx', () => {
  test('monta la app en #root y vigila los 401 de la API', async () => {
    window.history.replaceState(null, '', '/')
    root = document.createElement('div')
    root.id = 'root'
    document.body.appendChild(root)
    delete window.__optifullVigilaSesion
    const api = apiFalsa({ '/api/stats': { status: 401, json: {} }, '/api/heatmap/camara': { zonas: {} } })

    await act(async () => { await import('./main.jsx') })

    // La landing se ve dentro de #root.
    expect(await screen.findByRole('button', { name: 'Ya soy cliente' })).toBeInTheDocument()
    expect(root).not.toBeEmptyDOMElement()

    // fetch quedo envuelto: un 401 de la API dispara el evento de sesion vencida.
    expect(window.__optifullVigilaSesion).toBe(true)
    expect(window.fetch).not.toBe(api.fetch)
    const vencida = vi.fn()
    window.addEventListener(EVENTO_SESION_VENCIDA, vencida)
    await window.fetch('/api/stats')
    window.removeEventListener(EVENTO_SESION_VENCIDA, vencida)
    expect(vencida).toHaveBeenCalled()
  })
})

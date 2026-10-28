// Tema dia/noche (ver useTheme.js). El modulo guarda la preferencia al importarse, asi que cada test lo
// vuelve a cargar de cero con vi.resetModules().
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

const KEY = 'optifull-theme'

// matchMedia falso: 'oscuro' controla prefers-color-scheme y 'reducir' prefers-reduced-motion.
function sistema({ oscuro = false, reducir = false } = {}) {
  const oyentes = []
  const mq = (query) => ({
    media: query,
    get matches() { return query.includes('color-scheme') ? sist.oscuro : query.includes('reduced-motion') ? sist.reducir : false },
    addEventListener: (_, f) => oyentes.push(f),
    removeEventListener() {},
  })
  const sist = { oscuro, reducir, cambiar(v) { sist.oscuro = v; oyentes.forEach((f) => f()) } }
  vi.spyOn(window, 'matchMedia').mockImplementation(mq)
  return sist
}

async function cargar() {
  vi.resetModules()
  return import('./useTheme.js')
}

beforeEach(() => {
  delete document.documentElement.dataset.theme
  document.documentElement.classList.remove('theme-fade')
})
afterEach(() => { delete document.startViewTransition })

describe('useTheme', () => {
  test('sin eleccion guardada arranca con el tema del sistema (claro)', async () => {
    sistema({ oscuro: false })
    const { useTheme } = await cargar()
    const { result } = renderHook(() => useTheme())
    expect(result.current.tema).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem(KEY)).toBeNull()
  })

  test('sin eleccion guardada arranca oscuro si el sistema lo esta, pero no lo sigue despues (no hay Automatico)', async () => {
    const s = sistema({ oscuro: true, reducir: true })
    const { useTheme } = await cargar()
    const { result } = renderHook(() => useTheme())
    expect(result.current.tema).toBe('dark')
    act(() => s.cambiar(false))
    expect(result.current.tema).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  test('recupera la eleccion guardada e ignora valores raros', async () => {
    sistema()
    localStorage.setItem(KEY, 'dark')
    let m = await cargar()
    expect(renderHook(() => m.useTheme()).result.current.tema).toBe('dark')
    localStorage.setItem(KEY, 'violeta')
    m = await cargar()
    expect(renderHook(() => m.useTheme()).result.current.tema).toBe('light')
  })

  test('alternar pasa a noche, lo guarda y vuelve a dia', async () => {
    sistema({ reducir: true })
    const { useTheme } = await cargar()
    const { result } = renderHook(() => useTheme())
    act(() => result.current.alternar())
    expect(result.current.tema).toBe('dark')
    expect(localStorage.getItem(KEY)).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    act(() => result.current.alternar())
    expect(result.current.tema).toBe('light')
    expect(localStorage.getItem(KEY)).toBe('light')
  })

  test('un valor que no es Dia ni Noche (como el viejo "auto") se ignora', async () => {
    sistema({ reducir: true })
    localStorage.setItem(KEY, 'dark')
    const { useTheme } = await cargar()
    const { result } = renderHook(() => useTheme())
    act(() => result.current.setTema('auto'))
    expect(localStorage.getItem(KEY)).toBe('dark')
    expect(result.current.tema).toBe('dark')
  })

  test('sin View Transitions usa el fundido por CSS y lo quita despues', async () => {
    vi.useFakeTimers()
    sistema()
    const { useTheme } = await cargar()
    const { result } = renderHook(() => useTheme())
    act(() => result.current.setTema('dark'))
    expect(document.documentElement).toHaveClass('theme-fade')
    act(() => vi.advanceTimersByTime(450))
    expect(document.documentElement).not.toHaveClass('theme-fade')
  })

  test('con View Transitions el cambio se hace dentro de la transicion', async () => {
    sistema()
    document.startViewTransition = vi.fn((f) => f())
    const { useTheme } = await cargar()
    const { result } = renderHook(() => useTheme())
    act(() => result.current.setTema('dark'))
    expect(document.startViewTransition).toHaveBeenCalledTimes(1)
    expect(document.documentElement).not.toHaveClass('theme-fade')
    expect(result.current.tema).toBe('dark')
  })

  test('si otra pestaña cambia el tema, esta lo sigue', async () => {
    sistema({ reducir: true })
    const { useTheme } = await cargar()
    const { result } = renderHook(() => useTheme())
    localStorage.setItem(KEY, 'dark')
    act(() => { window.dispatchEvent(new StorageEvent('storage', { key: KEY })) })
    expect(result.current.tema).toBe('dark')
    act(() => { window.dispatchEvent(new StorageEvent('storage', { key: 'otra' })) })
    expect(result.current.tema).toBe('dark')
  })

  test('sin almacenamiento el tema vale igual para la sesion', async () => {
    sistema({ reducir: true })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloqueado') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloqueado') })
    const { useTheme } = await cargar()
    const { result } = renderHook(() => useTheme())
    expect(result.current.tema).toBe('light')
    act(() => result.current.setTema('dark'))
    expect(result.current.tema).toBe('dark')
  })
})

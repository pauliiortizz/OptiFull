// Alertas reales con re-consulta cada 20 s (ver useAlertas.js).
import { describe, test, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useAlertas } from './useAlertas.js'
import { apiFalsa } from '../test/apiFalsa.js'

const ALERTA = { id: 1, title: 'Posible hurto', status: 'open', sev: 'critical' }

describe('useAlertas', () => {
  beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }) })

  test('carga las alertas de /api/alertas', async () => {
    const api = apiFalsa({ '/api/alertas': [ALERTA] })
    const { result } = renderHook(() => useAlertas())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.alertas).toEqual([ALERTA])
    expect(api.hechos('/api/alertas', 'GET')).toHaveLength(1)
  })

  test('vuelve a consultar cada 20 segundos y deja de hacerlo al desmontar', async () => {
    let n = 0
    const api = apiFalsa({ '/api/alertas': () => ({ json: Array.from({ length: ++n }, (_, i) => ({ ...ALERTA, id: i })) }) })
    const { result, unmount } = renderHook(() => useAlertas())
    await waitFor(() => expect(result.current.alertas).toHaveLength(1))
    await act(() => vi.advanceTimersByTimeAsync(18000))
    expect(api.pedidos).toHaveLength(1)
    await act(() => vi.advanceTimersByTimeAsync(2000))
    await waitFor(() => expect(result.current.alertas).toHaveLength(2))
    unmount()
    await vi.advanceTimersByTimeAsync(60000)
    expect(api.pedidos).toHaveLength(2)
  })

  test('una respuesta que no es lista (error del servidor) deja la lista vacia', async () => {
    apiFalsa({ '/api/alertas': { status: 500, json: { error: 'db caida' } } })
    const { result } = renderHook(() => useAlertas())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.alertas).toEqual([])
  })

  test('si falla la red termina de cargar sin alertas', async () => {
    apiFalsa({ '/api/alertas': new TypeError('sin red') })
    const { result } = renderHook(() => useAlertas())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.alertas).toEqual([])
  })

  test('refresh consulta en el momento', async () => {
    const api = apiFalsa({ '/api/alertas': [] })
    const { result } = renderHook(() => useAlertas())
    await waitFor(() => expect(result.current.loading).toBe(false))
    act(() => result.current.refresh())
    await waitFor(() => expect(api.pedidos).toHaveLength(2))
  })
})

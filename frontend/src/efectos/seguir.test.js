// Pruebas del estirón de los botones (efectos/seguir.js).
import { describe, test, expect, vi } from 'vitest'
import { estira } from './seguir.js'

const conMovimiento = (reducido) => vi.spyOn(window, 'matchMedia').mockImplementation((q) => ({
  matches: reducido && q.includes('prefers-reduced-motion'), media: q, addEventListener() {}, removeEventListener() {},
}))

describe('estira', () => {
  // DEF-020: el estirón se llama dentro del submit del login y de la landing. Sin Web Animations
  // (navegadores viejos) el.animate no existe y la excepción cortaba el envío: no se podía ingresar.
  test('DEF-020: sin Web Animations no hace nada y no tira error', () => {
    conMovimiento(false)
    const boton = document.createElement('button')
    expect(boton.animate).toBeUndefined()   // jsdom tampoco la trae
    expect(() => estira(boton)).not.toThrow()
    expect(() => estira(boton, false, 0.5)).not.toThrow()
  })

  test('adelante se estira 620 ms y atrás se encoge 420 ms', () => {
    conMovimiento(false)
    const boton = { animate: vi.fn() }
    estira(boton)
    estira(boton, false)
    expect(boton.animate.mock.calls.map(([, o]) => o.duration)).toEqual([620, 420])
    expect(boton.animate.mock.calls[0][0][1].transform).toBe('scale(1.07, 0.9)')
  })

  test('la fuerza achica el estirón', () => {
    conMovimiento(false)
    const boton = { animate: vi.fn() }
    estira(boton, true, 0.5)
    const [x, y] = boton.animate.mock.calls[0][0][1].transform.match(/[\d.]+/g).map(Number)
    expect(x).toBeCloseTo(1.035)
    expect(y).toBeCloseTo(0.95)
  })

  test('con movimiento reducido o sin elemento no anima', () => {
    conMovimiento(true)
    const boton = { animate: vi.fn() }
    estira(boton)
    estira(null)
    expect(boton.animate).not.toHaveBeenCalled()
  })
})

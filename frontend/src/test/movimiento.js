// Movimiento reducido para los tests: los gráficos (efectos/graficos.js) animan con requestAnimationFrame la
// llegada de los datos (barras con resorte, cifras que cuentan) y, con prefers-reduced-motion, muestran el valor
// final de una vez, igual que para un usuario que lo tiene activado. Los tests que verifican datos lo usan así:
//
//   conMovimientoReducido()   // a nivel de archivo o dentro de un describe
//
// El spy se deshace solo después de cada test (restoreMocks en vitest.config.js).
import { beforeEach, vi } from 'vitest'

export function conMovimientoReducido() {
  beforeEach(() => {
    vi.spyOn(window, 'matchMedia').mockImplementation((q) => ({
      matches: q.includes('prefers-reduced-motion'), media: q, onchange: null,
      addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
    }))
  })
}

/* =====================================================================
   Gráficos — adaptado de «Pulso» e «Instrumental» · Moxen (moxen.cl/recursos)
   para los gráficos del dashboard.

   De Pulso: la chispa con su punta que late, el globo con el valor bajo el
   cursor y la cifra que cuenta hasta su valor.
   De Instrumental: el solver de resortes (las barras crecen y, al cambiar
   de serie, morfan pasándose un poco), la tira de calor por celdas y el
   anillo de marcas que se llena.

   Diferencias con los originales, por React y por los datos:
   - Dibujan en SVG, no en canvas: los colores salen de las variables CSS
     de la app (--brand-soft, --pos-soft, --fg-*) y el cambio de tema no
     necesita volver a leerlos.
   - Los datos son reales e históricos (no corren solos): lo que se anima es
     la llegada y el cambio de los datos, no un monitor en vivo.
   ===================================================================== */
import { useEffect, useRef, useState } from 'react'

export const reduceMovimiento = () => matchMedia('(prefers-reduced-motion: reduce)').matches

const PASO = 1 / 120

/* Resortes, uno por valor: devuelve los valores actuales, que persiguen a
   `metas` con rigidez k y freno c. Con k alto y c bajo se pasan y vuelven
   (el morfado de Instrumental); al llegar al reposo, el bucle se detiene. */
export function useResortes(metas, { k = 150, c = 17, desde = 0 } = {}) {
  const r = useRef(null)
  if (!r.current || r.current.x.length !== metas.length) {
    r.current = { x: metas.map(() => desde), v: metas.map(() => 0) }
  }
  const [x, setX] = useState(r.current.x)
  const clave = metas.join('|')
  useEffect(() => {
    const s = r.current
    if (reduceMovimiento()) { s.x = metas.slice(); s.v = metas.map(() => 0); setX(s.x); return }
    let raf = 0, previo = 0, resto = 0
    const cuadro = (ms) => {
      resto += previo ? Math.min(.05, (ms - previo) / 1000) : 0
      previo = ms
      while (resto >= PASO) {
        for (let i = 0; i < metas.length; i++) {
          s.v[i] += (k * (metas[i] - s.x[i]) - c * s.v[i]) * PASO
          s.x[i] += s.v[i] * PASO
        }
        resto -= PASO
      }
      const quieto = metas.every((m, i) => Math.abs(s.v[i]) < .002 * (Math.abs(m) + 1) && Math.abs(m - s.x[i]) < .0006 * (Math.abs(m) + 1))
      if (quieto) s.x = metas.slice()
      setX(s.x.slice())
      if (!quieto) raf = requestAnimationFrame(cuadro)
    }
    raf = requestAnimationFrame(cuadro)
    return () => cancelAnimationFrame(raf)
  }, [clave, k, c]) // eslint-disable-line react-hooks/exhaustive-deps
  return x
}

export const useResorte = (meta, o) => useResortes([meta], o)[0]

/* La cifra cuenta hasta su valor (Pulso): una salida suave en .7 s. Si el
   valor no es un número («—», «N/D»), se muestra tal cual. */
export function useCuenta(valor, decimales = 0) {
  const n = typeof valor === 'number' ? valor : (typeof valor === 'string' && valor.trim() !== '' && !isNaN(+valor) ? +valor : null)
  const [mostrado, setMostrado] = useState(n ?? 0)
  const desde = useRef(0)
  useEffect(() => {
    if (n == null) return
    if (reduceMovimiento()) { setMostrado(n); desde.current = n; return }
    const a = desde.current, t0 = performance.now()
    let raf = 0
    const cuadro = (ms) => {
      const t = Math.min(1, (ms - t0) / 700), v = a + (n - a) * (1 - Math.pow(1 - t, 3))
      desde.current = v
      setMostrado(v)
      if (t < 1) raf = requestAnimationFrame(cuadro)
    }
    raf = requestAnimationFrame(cuadro)
    return () => cancelAnimationFrame(raf)
  }, [n])
  if (n == null) return valor
  return mostrado.toLocaleString('es-AR', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })
}

export const decimalesDe = (v) => {
  const s = String(v ?? '')
  return s.includes('.') ? Math.min(2, s.split('.')[1].length) : 0
}

/* Curva suave con las asas en horizontal (la de Pulso). */
export function curva(pts) {
  let d = 'M' + pts[0][0].toFixed(2) + ' ' + pts[0][1].toFixed(2)
  for (let i = 1; i < pts.length; i++) {
    const xm = (pts[i - 1][0] + pts[i][0]) / 2
    d += 'C' + xm.toFixed(2) + ' ' + pts[i - 1][1].toFixed(2) + ' ' + xm.toFixed(2) + ' ' + pts[i][1].toFixed(2) + ' ' + pts[i][0].toFixed(2) + ' ' + pts[i][1].toFixed(2)
  }
  return d
}

/* =====================================================================
   Seguir — adaptado de «Seguir · Moxen» (moxen.cl/recursos) para el botón
   «Ingresar» del inicio de sesión.
   Al enviar, el botón se estira como una goma; si el ingreso sale bien,
   «Ingresar» se releva en vertical por «¡Listo!» con una palomita que se
   dibuja en verde. Si sale mal, se encoge con un gesto corto y seco.

   Diferencias con el original, por React:
   - No reescribe el innerHTML del botón: el marcado (.sg-fondo, .sg-cara,
     .sg-antes, .sg-despues) lo pone el componente, y el estado de éxito es
     la clase is-sigue que decide React.
   - De acá solo sale el estirón, hecho con Web Animations para que corra
     en el compositor y no recoloque la página (el botón no cambia de ancho).
   ===================================================================== */

export const reduceMovimiento = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/* adelante: se ensancha y se aplasta y vuelve con dos rebotes que se apagan.
   atrás: se encoge un poco, más corto y seco (error o validación).
   fuerza: 1 es el estirón del original; menos, un rebote más sutil (la
   landing usa ~.5 en sus botones y chips). */
export function estira(el, adelante = true, fuerza = 1) {
  if (!el || reduceMovimiento()) return;
  const e = (x, y = x) => ({ transform: 'scale(' + (1 + (x - 1) * fuerza) + ', ' + (1 + (y - 1) * fuerza) + ')' });
  el.animate(adelante ? [
    e(1),
    { ...e(1.07, .9), offset: .22 },
    { ...e(.97, 1.04), offset: .48 },
    { ...e(1.015, .99), offset: .72 },
    e(1),
  ] : [
    e(1),
    { ...e(.95, .96), offset: .3 },
    { ...e(1.01), offset: .65 },
    e(1),
  ], { duration: adelante ? 620 : 420, easing: 'ease-out' });
}

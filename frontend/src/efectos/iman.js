/* =====================================================================
   Imán — adaptado de «Imán · Moxen» (moxen.cl/recursos) para la app.
   Cuando el cursor (o el dedo) entra en el campo de un botón, el botón se
   le acerca, se inclina hacia él y su contenido se adelanta un poco más.
   Un brillo sigue al cursor por la cara del botón. Al pulsarlo se hunde;
   al salir del campo, un resorte lo devuelve con un vaivén corto.

   Diferencias con el original, por React:
   - No toca el árbol del DOM (el original envolvía el botón y movía sus
     hijos, y React pierde la pista de esos nodos). El brillo y el campo son
     ::before y ::after, y el estado va en atributos data-ia*, porque React
     reescribe className en cada render.
   - Un solo motor para todos los botones: un listener y un requestAnimationFrame.
     Solo atrae el botón más cercano, para que en listas densas (sidebar,
     pestañas) no se muevan todos a la vez.
   - Se engancha solo: iniciarImanes() busca los interactivos de la página y
     los que React monte después.

   Uso en el marcado:
     data-sin-iman      excluye el elemento (y sus descendientes)
     data-iman="0.3"    fuerza propia (0 a 1); vacío, la de por defecto
   ===================================================================== */

const SELECTOR = 'button, [role="button"], [role="tab"], nav a, .side-nav-item, a[class*="btn"], a[download], [data-iman]';
const PASO = 1 / 240;
const O = {
  fuerza: .22,      // qué fracción del camino hacia el cursor recorre
  fondo: .38,       // lo que se adelanta el contenido respecto al botón
  giro: 9,          // grados de inclinación como mucho
  margenMax: 48,    // px alrededor del botón donde ya atrae, como mucho
  rigidez: 190,
  freno: 15,
  maxAncho: 360,    // más grande que esto ya no es un botón: no atrae
  maxAlto: 160,
};

const estados = new Map();   // elemento -> estado
let puntero = null;          // { x, y } o null si no hay cursor
let medir = false, raf = 0, ultimo = null, activo = null;

const lim = (v, a) => Math.max(-a, Math.min(a, v));
// separa "a, cubic-bezier(1, 2, 3, 4)" sin cortar dentro de los paréntesis
const partes = (s) => s.split(/,(?![^(]*\))/).map((t) => t.trim());

/* Las transiciones de transform del CSS de la app (los :active con scale)
   frenarían el resorte, que escribe transform en cada cuadro: se anulan
   solo para transform y se conservan las demás. */
function sinTransicionDeTransform(el, cs) {
  const props = partes(cs.transitionProperty);
  if (!props.some((p) => p === 'transform' || p === 'all')) return;
  const dur = partes(cs.transitionDuration), fn = partes(cs.transitionTimingFunction), ret = partes(cs.transitionDelay);
  el.style.transition = props
    .map((p, i) => `${p} ${dur[i % dur.length]} ${fn[i % fn.length]} ${ret[i % ret.length]}`)
    .join(', ') + ', transform 0s';
}

function engancha(el) {
  if (estados.has(el) || el.closest('[data-sin-iman]')) return;
  const cs = getComputedStyle(el);
  if (cs.position === 'static') el.style.position = 'relative';
  if (cs.display === 'inline') el.style.display = 'inline-block';   // transform no aplica a lo inline
  sinTransicionDeTransform(el, cs);
  // si el elemento ya usa sus pseudo-elementos, se respetan
  const marcas = [];
  if (getComputedStyle(el, '::before').content !== 'none') marcas.push('sin-luz');
  if (getComputedStyle(el, '::after').content !== 'none') marcas.push('sin-campo');
  el.setAttribute('data-ia', marcas.join(' '));
  const f = parseFloat(el.dataset.iman);
  estados.set(el, {
    fuerza: Number.isFinite(f) ? f : O.fuerza,
    // posición (x, y), inclinación (gx, gy) y hundimiento (s), cada uno con su resorte
    R: { x: 0, y: 0, gx: 0, gy: 0, s: 1 }, V: { x: 0, y: 0, gx: 0, gy: 0, s: 0 },
    M: { x: 0, y: 0, gx: 0, gy: 0, s: 1 },
    pulsado: false, vivo: false,
  });
}

function busca(raiz) {
  if (raiz.nodeType !== 1) return;
  if (raiz.matches(SELECTOR)) engancha(raiz);
  raiz.querySelectorAll(SELECTOR).forEach(engancha);
}

/* ── la medición ──────────────────────────────────────────────────────
   El centro se mide sin el desplazamiento propio (rect − R): medir el botón
   ya movido haría que persiguiera su propia posición. La rotación y la
   escala son alrededor del centro, así que no lo corren. */
function mide() {
  let elegido = null, mejorFuera = Infinity, mejorCentro = Infinity, datos = null;
  for (const [el, e] of estados) {
    if (!el.isConnected) { estados.delete(el); continue; }
    if (!puntero || el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
    const r = el.getBoundingClientRect();
    if (!r.width) continue;
    const w = el.offsetWidth, h = el.offsetHeight;
    if (w > O.maxAncho || h > O.maxAlto) continue;
    const cx = r.left + r.width / 2 - e.R.x, cy = r.top + r.height / 2 - e.R.y;
    const dx = puntero.x - cx, dy = puntero.y - cy;
    // el campo es el contorno del botón agrandado «margen» píxeles
    const margen = Math.min(O.margenMax, Math.max(14, Math.min(w, h) * .6));
    const fx = Math.max(Math.abs(dx) - w / 2, 0), fy = Math.max(Math.abs(dy) - h / 2, 0);
    const fuera = fx * fx + fy * fy, centro = dx * dx + dy * dy;
    if (fuera >= margen * margen) continue;
    if (fuera < mejorFuera || (fuera === mejorFuera && centro < mejorCentro)) {
      mejorFuera = fuera; mejorCentro = centro;
      elegido = el; datos = { e, dx, dy, w, h, margen };
    }
  }

  if (activo && activo !== elegido) {
    const e = estados.get(activo);
    if (e) { Object.assign(e.M, { x: 0, y: 0, gx: 0, gy: 0 }); e.vivo = true; }
    activo.removeAttribute('data-ia-cerca');
  }
  if (elegido) {
    const { e, dx, dy, w, h, margen } = datos;
    const tope = Math.max(6, Math.min(w, h) * .35);
    e.M.x = lim(dx * e.fuerza, tope);
    e.M.y = lim(dy * e.fuerza, tope);
    /* Se inclina hacia el cursor: el canto más cercano se adelanta. En CSS,
       rotateY positivo aleja el canto derecho y rotateX positivo aleja el
       de arriba; por eso los signos. */
    e.M.gy = -lim(dx / (w / 2 + margen), 1) * O.giro;
    e.M.gx = lim(dy / (h / 2 + margen), 1) * O.giro;
    e.vivo = true;
    const s = elegido.style;
    if (elegido !== activo) {
      const rad = getComputedStyle(elegido).borderTopLeftRadius;
      const radio = rad.endsWith('%') ? Math.min(w, h) / 2 : parseFloat(rad) || 0;
      s.setProperty('--ia-margen', margen + 'px');
      s.setProperty('--ia-radio-campo', (radio + margen) + 'px');
      s.setProperty('--ia-lr', Math.max(36, Math.min(110, Math.max(w, h) * .8)) + 'px');
      elegido.setAttribute('data-ia-cerca', '');
    }
    // el brillo, en coordenadas del botón (ya desplazado hacia el cursor)
    s.setProperty('--ia-lx', (dx + w / 2 - e.R.x).toFixed(1) + 'px');
    s.setProperty('--ia-ly', (dy + h / 2 - e.R.y).toFixed(1) + 'px');
  }
  activo = elegido;
}

/* ── la física ───────────────────────────────────────────────────────── */
function integra(e, dt) {
  e.M.s = e.pulsado ? .94 : 1;
  const { R, V, M } = e;
  for (let t = dt; t > 1e-6; t -= PASO) {
    const h = Math.min(t, PASO);
    for (const k in R) {
      // el hundimiento es más rígido: un clic se siente seco
      const kr = k === 's' ? O.rigidez * 3 : O.rigidez, kf = k === 's' ? O.freno * 1.3 : O.freno;
      V[k] += (-kr * (R[k] - M[k]) - kf * V[k]) * h;
      R[k] += V[k] * h;
    }
  }
  for (const k in R) if (Math.abs(R[k] - M[k]) > .02 || Math.abs(V[k]) > .02) return false;
  for (const k in R) { R[k] = M[k]; V[k] = 0; }
  return true;
}

function pinta(el, e) {
  const { R, M } = e, s = el.style;
  const enReposo = !M.x && !M.y && !M.gx && !M.gy && M.s === 1 && !R.x && !R.y && !R.gx && !R.gy && R.s === 1;
  if (enReposo) {
    // en reposo se devuelve el control al CSS de la app
    s.removeProperty('transform');
    s.removeProperty('--ia-cx');
    s.removeProperty('--ia-cy');
    return;
  }
  s.transform = 'perspective(700px) translate3d(' + R.x.toFixed(2) + 'px, ' + R.y.toFixed(2) + 'px, 0) rotateX('
    + R.gx.toFixed(2) + 'deg) rotateY(' + R.gy.toFixed(2) + 'deg) scale(' + R.s.toFixed(4) + ')';
  s.setProperty('--ia-cx', (R.x * O.fondo).toFixed(2) + 'px');
  s.setProperty('--ia-cy', (R.y * O.fondo).toFixed(2) + 'px');
}

function cuadro(ts) {
  raf = 0;
  if (medir) { medir = false; mide(); }
  const dt = ultimo === null ? 0 : Math.min(1 / 30, (ts - ultimo) / 1000);
  ultimo = ts;
  let sigue = false;
  for (const [el, e] of estados) {
    if (!e.vivo) continue;
    if (integra(e, dt)) e.vivo = false; else sigue = true;
    pinta(el, e);
  }
  if (sigue) raf = requestAnimationFrame(cuadro); else ultimo = null;
}
const anda = () => { if (!raf) raf = requestAnimationFrame(cuadro); };
const remide = () => { medir = true; anda(); };

/* ── los eventos ─────────────────────────────────────────────────────── */
function mueve(ev) {
  if (ev.pointerType === 'touch' && !ev.isPrimary) return;
  puntero = { x: ev.clientX, y: ev.clientY };
  remide();
}
function suelta() { puntero = null; remide(); }
function pulsa(el, si) {
  const e = estados.get(el);
  if (e && e.pulsado !== si) { e.pulsado = si; e.vivo = true; anda(); }
}
function sueltaTodos() { for (const el of estados.keys()) pulsa(el, false); }

let iniciado = false;
export function iniciarImanes() {
  if (iniciado || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  iniciado = true;

  busca(document.body);
  new MutationObserver((ms) => { for (const m of ms) m.addedNodes.forEach(busca); })
    .observe(document.body, { childList: true, subtree: true });

  addEventListener('pointermove', mueve, { passive: true });
  addEventListener('pointerdown', (ev) => {
    if (ev.pointerType !== 'mouse') mueve(ev);
    const el = ev.target.closest?.('[data-ia]');
    if (el) pulsa(el, true);
  }, { passive: true });
  // con el dedo, al levantarlo el botón vuelve a su sitio
  addEventListener('pointerup', (ev) => { sueltaTodos(); if (ev.pointerType !== 'mouse') suelta(); });
  addEventListener('pointercancel', () => { sueltaTodos(); suelta(); });
  document.documentElement.addEventListener('pointerleave', suelta);
  // al hacer scroll el botón se corre bajo un cursor quieto
  addEventListener('scroll', () => { if (puntero) remide(); }, { passive: true, capture: true });
  addEventListener('keydown', (ev) => {
    if ((ev.key === 'Enter' || ev.key === ' ') && !ev.repeat && estados.has(ev.target)) pulsa(ev.target, true);
  });
  addEventListener('keyup', (ev) => { if (estados.has(ev.target)) pulsa(ev.target, false); });
}

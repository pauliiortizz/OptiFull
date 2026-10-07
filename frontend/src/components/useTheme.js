import { useSyncExternalStore } from 'react'

// Tema de la interfaz: 'auto' (sigue al sistema, por defecto), 'light' o 'dark'.
// La HIG pide no ofrecer un ajuste propio de apariencia salvo necesidad (dark-mode.md > Best practices);
// por eso el valor por defecto es 'auto' y solo se guarda algo cuando la persona elige Dia o Noche.
// El tema resuelto vive en <html data-theme> (lo lee index.css) y se aplica tambien desde un script en
// index.html antes de que React pinte, para que no haya un destello claro al abrir en modo noche.
const KEY = 'optifull-theme';
const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null;
const oyentes = new Set();

const leer = () => {
  try { const v = localStorage.getItem(KEY); return v === 'light' || v === 'dark' ? v : 'auto'; }
  catch { return 'auto'; }
};
const resolver = (p) => (p === 'auto' ? (mq?.matches ? 'dark' : 'light') : p);

let pref = leer();

function aplicar() {
  document.documentElement.dataset.theme = resolver(pref);
  oyentes.forEach((f) => f());
}

// Cambio con fundido: View Transitions cruza una captura del tema anterior con el nuevo (anima tambien los
// degradados del fondo, que una transicion CSS de color no puede). Sin soporte se usa un respaldo por
// transiciones de color (.theme-fade en index.css). Con "reducir movimiento" el cambio es inmediato (motion.md).
function aplicarAnimado() {
  const reducir = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducir) { aplicar(); return; }
  if (typeof document.startViewTransition === 'function') {
    document.startViewTransition(aplicar);
    return;
  }
  const html = document.documentElement;
  html.classList.add('theme-fade');
  aplicar();
  setTimeout(() => html.classList.remove('theme-fade'), 450);
}

export function setTema(nueva) {
  pref = nueva;
  try { if (nueva === 'auto') localStorage.removeItem(KEY); else localStorage.setItem(KEY, nueva); } catch { /* sin storage: vale solo para la sesion */ }
  aplicarAnimado();
}

// En 'auto' el sistema puede cambiar mientras la app esta abierta (modo Automatico de macOS/iOS al atardecer).
mq?.addEventListener('change', () => { if (pref === 'auto') aplicarAnimado(); });
// Otra pestaña cambio la preferencia.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => { if (e.key === KEY) { pref = leer(); aplicarAnimado(); } });
  aplicar();
}

const suscribir = (f) => { oyentes.add(f); return () => oyentes.delete(f); };
const instantanea = () => `${pref}|${resolver(pref)}`;

export function useTheme() {
  const [preferencia, resuelto] = useSyncExternalStore(suscribir, instantanea).split('|');
  return {
    preferencia,                                   // 'auto' | 'light' | 'dark'
    tema: resuelto,                                // 'light' | 'dark' (lo que se ve ahora)
    setTema,
    alternar: () => setTema(resuelto === 'dark' ? 'light' : 'dark'),
  };
}

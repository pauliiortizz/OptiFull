import { useSyncExternalStore } from 'react'

// Tema de la interfaz: solo 'light' (Dia) o 'dark' (Noche); no hay modo Automatico.
// Si la persona todavia no eligio, se arranca con el tema del sistema en ese momento (sin seguirlo despues)
// y no se guarda nada hasta que elige Dia o Noche.
// El tema resuelto vive en <html data-theme> (lo lee index.css) y se aplica tambien desde un script en
// index.html antes de que React pinte, para que no haya un destello claro al abrir en modo noche.
const KEY = 'optifull-theme';
const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null;
const oyentes = new Set();

const delSistema = () => (mq?.matches ? 'dark' : 'light');
const leer = () => {
  try { const v = localStorage.getItem(KEY); return v === 'light' || v === 'dark' ? v : delSistema(); }
  catch { return delSistema(); }
};

let pref = leer();

function aplicar() {
  document.documentElement.dataset.theme = pref;
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
  if (nueva !== 'light' && nueva !== 'dark') return;
  pref = nueva;
  try { localStorage.setItem(KEY, nueva); } catch { /* sin storage: vale solo para la sesion */ }
  aplicarAnimado();
}

// Otra pestaña cambio la preferencia.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => { if (e.key === KEY) { pref = leer(); aplicarAnimado(); } });
  aplicar();
}

const suscribir = (f) => { oyentes.add(f); return () => oyentes.delete(f); };
const instantanea = () => pref;

export function useTheme() {
  const tema = useSyncExternalStore(suscribir, instantanea);   // 'light' | 'dark'
  return {
    tema,
    setTema,
    alternar: () => setTema(tema === 'dark' ? 'light' : 'dark'),
  };
}

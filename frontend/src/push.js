// Notificaciones push en ESTE navegador (ver frontend/api/push.py y public/sw.js): registrar el service worker,
// pedir permiso y suscribirse al servicio de push del navegador. La suscripcion se guarda en el backend, que es
// quien manda las alertas. Todo devuelve promesas y nunca deja una excepcion sin mensaje para el usuario.

const SW_URL = '/sw.js';

// Estados posibles de este navegador:
//   'no_soportado'  el navegador no tiene Web Push (o la pagina no es https ni localhost)
//   'bloqueado'     el usuario bloqueo las notificaciones para este sitio
//   'activo'        suscripto: le llegan las alertas
//   'inactivo'      se puede activar
export function pushSoportado() {
  return typeof window !== 'undefined' && window.isSecureContext !== false
    && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

async function registro() {
  return (await navigator.serviceWorker.getRegistration(SW_URL)) || navigator.serviceWorker.register(SW_URL);
}

export async function estadoPush() {
  if (!pushSoportado()) return 'no_soportado';
  if (Notification.permission === 'denied') return 'bloqueado';
  const reg = await navigator.serviceWorker.getRegistration(SW_URL);
  const sub = reg && await reg.pushManager.getSubscription();
  return sub && Notification.permission === 'granted' ? 'activo' : 'inactivo';
}

// La clave publica VAPID viene en base64url; pushManager.subscribe la quiere en bytes.
export function claveABytes(base64url) {
  const relleno = '='.repeat((4 - (base64url.length % 4)) % 4);
  const crudo = atob((base64url + relleno).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(crudo, (c) => c.charCodeAt(0));
}

async function errorDe(r, porDefecto) {
  const d = await r.json().catch(() => ({}));
  return new Error(d.error || porDefecto);
}

export async function activarPush() {
  if (!pushSoportado()) throw new Error('Este navegador no admite notificaciones push.');
  const permiso = await Notification.requestPermission();
  if (permiso !== 'granted') {
    throw new Error(permiso === 'denied'
      ? 'Las notificaciones están bloqueadas para este sitio: habilitalas desde el candado de la barra de direcciones.'
      : 'No se dio permiso para mostrar notificaciones.');
  }
  const rClave = await fetch('/api/push/clave');
  if (!rClave.ok) throw await errorDe(rClave, 'El servidor no tiene configuradas las notificaciones push.');
  const { clave } = await rClave.json();
  const reg = await registro();
  await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: claveABytes(clave) });
  const r = await fetch('/api/push/suscripcion', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sub.toJSON()),
  });
  if (!r.ok) throw await errorDe(r, 'No se pudo guardar la suscripción en el servidor.');
  return sub;
}

export async function desactivarPush() {
  if (!pushSoportado()) return;
  const reg = await navigator.serviceWorker.getRegistration(SW_URL);
  const sub = reg && await reg.pushManager.getSubscription();
  if (!sub) return;
  await fetch('/api/push/suscripcion', {
    method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: sub.endpoint }),
  }).catch(() => {});
  await sub.unsubscribe();
}

export async function probarPush() {
  const reg = pushSoportado() && await navigator.serviceWorker.getRegistration(SW_URL);
  const sub = reg && await reg.pushManager.getSubscription();
  if (!sub) throw new Error('Primero activá las notificaciones en este navegador.');
  const r = await fetch('/api/push/prueba', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: sub.endpoint }),
  });
  if (!r.ok) throw await errorDe(r, 'No se pudo enviar la notificación de prueba.');
}

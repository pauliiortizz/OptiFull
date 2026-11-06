// Service worker de OptiFull: muestra las notificaciones push de las alertas aunque el dashboard este cerrado o
// el usuario este en otra pestana (ver frontend/api/push.py y src/push.js). No cachea nada: solo push y clic.

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (evento) => evento.waitUntil(self.clients.claim()));

// El backend manda {titulo, cuerpo, url, tag} (ver _enviar_a en frontend/api/push.py).
self.addEventListener('push', (evento) => {
  let datos = {};
  try { datos = evento.data ? evento.data.json() : {}; } catch { datos = { cuerpo: evento.data?.text() }; }
  evento.waitUntil(self.registration.showNotification(datos.titulo || 'OptiFull', {
    body: datos.cuerpo || 'Hay una nueva alerta en la tienda.',
    icon: '/icono-notificacion.png',
    badge: '/icono-notificacion.png',
    tag: datos.tag || 'optifull',          // la misma alerta no se apila dos veces
    renotify: true,
    requireInteraction: true,              // en escritorio queda en pantalla hasta que se la cierre
    data: { url: datos.url || '/alertas' },
  }));
});

// Clic en la notificacion: si OptiFull ya esta abierto, se trae al frente y va a la seccion de Alertas; si no,
// se abre en una ventana nueva.
self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  evento.waitUntil((async () => {
    const ventanas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const abierta = ventanas.find((v) => new URL(v.url).origin === self.location.origin);
    if (abierta) {
      abierta.postMessage({ tipo: 'optifull-abrir', seccion: 'alerts' });
      return abierta.focus();
    }
    return self.clients.openWindow('/dashboard?seccion=alerts');
  })());
});

// Agente local (frontend/api/agente.py): en QA y producción el panel corre en internet y la cámara del celular
// está en la red de la caja, así que el video y el detector los da el backend que corre en la compu de la caja
// (`py -3.13 serve_dashboard.py --agente`), en http://127.0.0.1:8080. El video va directo de esa compu a la
// pantalla, sin pasar por internet. Las decisiones y las ventas siguen yendo a la API de producción (Supabase).
export const AGENTE = 'http://127.0.0.1:8080/agente';

// En la compu (localhost) el panel habla con su propio backend, como siempre; en cualquier otro dominio, con el agente.
export function usaAgente() {
  return !['localhost', '127.0.0.1'].includes(window.location.hostname);
}

import { useState, useEffect, useCallback } from 'react'

// Alertas REALES (ver /api/alertas -- tabla 'alertas', generada por
// Persistencia.guardar_evento cuando eventos.clasificar_evento() da
// POSIBLE_HURTO). Se re-consulta cada 20s para reflejar alertas nuevas de
// analisis en curso, sin depender de que el usuario recargue la pagina.
export function useAlertas() {
  const [alertas, setAlertas] = useState([]);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(() => {
    fetch('/api/alertas')
      .then(r => r.json())
      .then(d => { setAlertas(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 20000);
    return () => clearInterval(id);
  }, [refresh]);
  return { alertas, loading, refresh };
}

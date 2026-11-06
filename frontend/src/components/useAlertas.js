import { useState, useEffect, useCallback } from 'react'

// Categoria de cada alerta: solo la actividad sospechosa ('posible_hurto') es 'critical' (Crítica); los posibles
// empleados son 'info' (solo piden una decision) y el resto, 'warn'. Se decide aca por el tipo, sin depender de la
// 'sev' que mande el backend: uno anterior (todavia desplegado) manda la actividad sospechosa como 'warn'.
export function categoria(a) {
  if (a.tipo === 'posible_empleado') return 'info';
  if (a.tipo === 'posible_hurto' || a.sev === 'critical') return 'critical';
  return a.sev === 'info' ? 'info' : 'warn';
}

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
      .then(d => { setAlertas(Array.isArray(d) ? d.map((a) => ({ ...a, sev: categoria(a) })) : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 20000);
    return () => clearInterval(id);
  }, [refresh]);
  return { alertas, loading, refresh };
}

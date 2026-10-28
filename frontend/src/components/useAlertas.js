import { useState, useEffect, useCallback } from 'react'

// Categoria de cada alerta: los posibles empleados son 'info' (solo piden una decision) y los posibles hurtos, y el
// resto de las alertas de seguridad, 'warn' (Warning). Se decide aca por el tipo, sin depender de la 'sev' que mande
// el backend: un backend anterior (todavia desplegado) manda los hurtos como 'critical' y los empleados como 'warn',
// y con eso el filtro "Warning" de Alertas quedaba vacio.
export function categoria(a) {
  if (a.tipo === 'posible_empleado') return 'info';
  if (a.tipo === 'posible_hurto' || a.sev === 'critical') return 'warn';
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

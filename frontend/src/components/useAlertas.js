import { useState, useEffect, useCallback } from 'react'

// Categoria de cada alerta: solo la actividad sospechosa ('posible_hurto') es 'critical' (Crítica); los posibles
// empleados son 'info' (solo piden una decision) y el resto, 'warn'. Se decide aca por el tipo, sin depender de la
// 'sev' que mande el backend: uno anterior (todavia desplegado) manda la actividad sospechosa como 'warn'.
export function categoria(a) {
  if (a.tipo === 'posible_empleado') return 'info';
  if (a.tipo === 'posible_hurto' || a.sev === 'critical') return 'critical';
  return a.sev === 'info' ? 'info' : 'warn';
}

// Abierta = sin resolver. Las alertas calculadas al consultar (espera larga en caja) vienen con status null y cuentan
// como abiertas, igual que en la pagina Alertas.
export const estaAbierta = (a) => (a.status ?? 'open') === 'open';

// Resumen para la campana de notificaciones: no una fila por alerta, sino una por tipo (hay N esperas largas en
// caja, hay N decisiones pendientes...). La actividad sospechosa va primero y en rojo.
export function resumenAlertas(abiertas) {
  const plural = (n, uno, varios) => (n === 1 ? uno : varios.replace('{n}', n));
  const criticas  = abiertas.filter((a) => a.sev === 'critical');
  const esperas   = abiertas.filter((a) => a.sev !== 'critical' && a.tipo === 'espera_excesiva');
  const empleados = abiertas.filter((a) => a.sev !== 'critical' && a.tipo === 'posible_empleado');
  const otras     = abiertas.filter((a) => a.sev !== 'critical' && a.tipo !== 'espera_excesiva' && a.tipo !== 'posible_empleado');
  const items = [];
  if (criticas.length) items.push({ clave: 'critical', sev: 'critical',
    titulo: plural(criticas.length, 'Hay actividad sospechosa', 'Hay {n} actividades sospechosas'), detalle: criticas[0].title });
  if (esperas.length) {
    const umbrales = esperas.map((a) => a.umbral_min).filter(Boolean);
    items.push({ clave: 'espera', sev: 'warn',
      titulo: plural(esperas.length, 'Hay una espera larga en caja', 'Hay {n} esperas largas en caja'),
      detalle: umbrales.length ? `Más de ${String(Math.min(...umbrales)).replace('.', ',')} min, el umbral configurado` : 'Superaron el umbral configurado' });
  }
  if (empleados.length) items.push({ clave: 'empleado', sev: 'info',
    titulo: plural(empleados.length, 'Hay una decisión pendiente', 'Hay {n} decisiones pendientes'), detalle: 'Confirmar si es empleado' });
  if (otras.length) items.push({ clave: 'otras', sev: 'warn',
    titulo: plural(otras.length, 'Hay una alerta por revisar', 'Hay {n} alertas por revisar'), detalle: otras[0].title });
  return items;
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

"""Sucesor de forzar_empleados_zona_caja.py: en vez de marcar empleado a
CUALQUIERA con un solo punto en Zona Caja (lo que fusionaba clientes reales
que solo pasaron a pagar), decide por la MAYORIA de puntos de cada persona y
BORRA los puntos minoritarios que contradicen esa mayoria. Ver
Persistencia.reclasificar_por_mayoria_zona() para el detalle completo de la
regla (incluye el desempate en caso de igualdad).

OJO: este script BORRA datos de 'trayectorias' de forma permanente (los
puntos minoritarios que contradicen la mayoria de cada persona). No es
reversible.

Uso: python -m deteccion.mantenimiento.reclasificar_por_mayoria_zona
"""
from deteccion import config
from deteccion.persistencia import Persistencia


def main() -> None:
    persistencia = Persistencia(
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS,
        config.CAMARA_NOMBRES, config.GRUPOS_CAMARA, config.REID_VENTANA_HORAS,
    )
    if not persistencia.conectar():
        print("[AVISO] No se pudo conectar a la BD.")
        return

    resumen = persistencia.reclasificar_por_mayoria_zona()
    sync = persistencia.sincronizar_es_empleado_trayectorias()
    persistencia.cerrar()
    print(f"Resumen: {resumen}")
    print(f"Trayectorias sincronizadas: {sync}")


if __name__ == "__main__":
    main()

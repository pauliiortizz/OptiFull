"""Corrige el efecto colateral de marcar_empleados_zona_caja.py: una aparicion
que matcheo SOLO contra la tabla de referencia (sin matchear una cadena real
ya conocida) quedaba como raiz de su PROPIA cadena en vez de fusionarse con
el empleado real correspondiente -- inflando el numero de "empleados"
distintos muy por encima de los 3 que existen en la realidad (ver
Persistencia.consolidar_cadenas_empleados()). Reapunta todo lo que ya tiene
empleado_id asignado a la raiz canonica de ESE empleado, y completa
empleado_id en las cadenas que ya estaban bien fusionadas pero sin la
etiqueta.

Uso: python -m deteccion.mantenimiento.consolidar_empleados
"""
from deteccion import config
from deteccion.persistencia import Persistencia

# empleado_id (tabla 'empleados') -> persona_id CANONICO de su cadena real.
RAIZ_POR_EMPLEADO = {1: 81, 2: 109, 3: 114}


def main() -> None:
    persistencia = Persistencia(
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS,
        config.CAMARA_NOMBRES, config.GRUPOS_CAMARA, config.REID_VENTANA_HORAS,
    )
    if not persistencia.conectar():
        print("[AVISO] No se pudo conectar a la BD.")
        return

    resumen = persistencia.consolidar_cadenas_empleados(RAIZ_POR_EMPLEADO)
    sync = persistencia.sincronizar_es_empleado_trayectorias()
    persistencia.cerrar()
    print(f"Resumen: {resumen}")
    print(f"Trayectorias sincronizadas: {sync}")


if __name__ == "__main__":
    main()

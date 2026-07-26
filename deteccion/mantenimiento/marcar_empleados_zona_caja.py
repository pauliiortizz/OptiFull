"""Correccion retroactiva puntual: marca como empleado a toda 'persona' que
tenga un punto de trayectoria en alguna Zona Caja real (zona_id 10, 14, 16 o
19 -- camaras 1, 2, 3 y 4 respectivamente) con es_empleado=false, siempre que
su descripcion_visual matchee contra un empleado conocido (apariciones ya
confirmadas + tabla de referencia 'empleados'). Ver
Persistencia.marcar_empleados_en_zona_caja().

OJO: con la tabla 'empleados' actual (ver deteccion/poblar_empleados.py --
incluye la cadena ex-cliente_id 114, con colores muy inconsistentes) el match
es MUY permisivo: en la practica, casi cualquier persona en Zona Caja
matchea contra alguna de las 139 variantes. Correr esto marca como empleado a
gente que probablemente sea cliente real -- decision consciente, no un bug.

Uso: python -m deteccion.mantenimiento.marcar_empleados_zona_caja
"""
from deteccion import config
from deteccion.persistencia import Persistencia

ZONAS_CAJA = [10, 14, 16, 19]


def main() -> None:
    persistencia = Persistencia(
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS,
        config.CAMARA_NOMBRES, config.GRUPOS_CAMARA, config.REID_VENTANA_HORAS,
    )
    if not persistencia.conectar():
        print("[AVISO] No se pudo conectar a la BD.")
        return

    resumen = persistencia.marcar_empleados_en_zona_caja(ZONAS_CAJA)
    sync = persistencia.sincronizar_es_empleado_trayectorias()
    persistencia.cerrar()
    print(f"Resumen: {resumen}")
    print(f"Trayectorias sincronizadas: {sync}")


if __name__ == "__main__":
    main()

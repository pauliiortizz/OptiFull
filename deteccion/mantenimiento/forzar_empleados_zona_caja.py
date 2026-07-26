"""Regla de negocio: Zona Caja es espacio FISICAMENTE exclusivo de empleados
(detras del mostrador) -- a diferencia de marcar_empleados_zona_caja.py (que
solo marca empleado si la descripcion matchea contra algo conocido, y deja
en paz al resto), este script marca es_empleado=true SI O SI a cualquier
persona con un punto de trayectoria en zona_id 10, 14, 16 o 19, fusionandola
siempre a la cadena canonica real del empleado correspondiente (derivada de
'personas', no hardcodeada): por descripcion coincidente si matchea, por
similitud (mas campos en comun) si no matchea pero hay algo comparable --
guardando esa descripcion como variante NUEVA en empleados_descripciones --
o al empleado por defecto si no hay descripcion. Ver
Persistencia.forzar_empleado_zona_caja().

Uso normal: correr esto UNA vez para corregir retroactivamente. Para que
corra solo tambien despues de cada video nuevo, ver la llamada equivalente
ya agregada a main.py (justo despues de auditar_sesion()).

Uso: python -m deteccion.mantenimiento.forzar_empleados_zona_caja
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

    # zona_ids=None -> se resuelve solo a todas las zonas con tipo='caja'.
    resumen = persistencia.forzar_empleado_zona_caja()
    sync = persistencia.sincronizar_es_empleado_trayectorias()
    persistencia.cerrar()
    print(f"Resumen: {resumen}")
    print(f"Trayectorias sincronizadas: {sync}")


if __name__ == "__main__":
    main()

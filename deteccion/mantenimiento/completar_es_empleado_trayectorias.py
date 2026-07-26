"""Rellena/sincroniza retroactivamente 'trayectorias.es_empleado' (columna
agregada al schema como copia desnormalizada de la fila RAIZ de la cadena de
cliente_id en 'personas') -- ver
Persistencia.sincronizar_es_empleado_trayectorias(). Idempotente: se puede
correr de nuevo sin efecto si ya esta todo sincronizado. Conviene volver a
correrlo despues de marcar/desmarcar empleados manualmente en bloque o de
correr fusionar_dia.py, si no se hizo via el endpoint (que ya sincroniza
la cadena puntual sola).

Uso: python -m deteccion.mantenimiento.completar_es_empleado_trayectorias
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

    actualizados = persistencia.sincronizar_es_empleado_trayectorias()
    persistencia.cerrar()
    print(f"Filas de trayectorias actualizadas: {actualizados}")


if __name__ == "__main__":
    main()

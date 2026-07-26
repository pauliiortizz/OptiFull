"""Rellena retroactivamente 'trayectorias.camara_id' (columna agregada al
schema para no depender de un JOIN via personas -> sesiones_video en cada
consulta que filtra trayectorias por camara) -- ver
Persistencia.completar_camara_id_trayectorias(). Idempotente: se puede
correr de nuevo sin efecto si ya esta todo completo.

Uso: python -m deteccion.mantenimiento.completar_camara_trayectorias
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

    actualizados = persistencia.completar_camara_id_trayectorias()
    persistencia.cerrar()
    print(f"Filas de trayectorias actualizadas: {actualizados}")


if __name__ == "__main__":
    main()

"""Borra puntos de 'trayectorias' que violan la regla de negocio: Zona Caja
es exclusiva de empleados, Zona Gondolas/Salon son exclusivas de clientes --
ver Persistencia.limpiar_trayectorias_fuera_de_zona() para el detalle.

Uso: python -m deteccion.mantenimiento.limpiar_trayectorias_zona
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

    borrados = persistencia.limpiar_trayectorias_fuera_de_zona()
    persistencia.cerrar()
    print(f"Puntos de trayectoria borrados: {borrados}")


if __name__ == "__main__":
    main()

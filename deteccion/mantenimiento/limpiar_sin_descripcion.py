"""Borra 'personas' que nunca llegaron a tener descripcion_visual -- ver
Persistencia.borrar_sin_descripcion() para el detalle de por que y como
reapunta a los dependientes antes de borrar la raiz.

Uso: python -m deteccion.mantenimiento.limpiar_sin_descripcion [YYYY-MM-DD]
     (sin fecha = TODA la base de datos)
"""
import sys
from datetime import date

from deteccion import config
from deteccion.persistencia import Persistencia


def main() -> None:
    fecha = date.fromisoformat(sys.argv[1]) if len(sys.argv) == 2 else None

    persistencia = Persistencia(
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS,
        config.CAMARA_NOMBRES, config.GRUPOS_CAMARA, config.REID_VENTANA_HORAS,
    )
    if not persistencia.conectar():
        print("[AVISO] No se pudo conectar a la BD.")
        sys.exit(1)

    borradas = persistencia.borrar_sin_descripcion(fecha)
    persistencia.cerrar()
    print(f"Borradas ({'TODA la BD' if fecha is None else fecha}): {borradas}")


if __name__ == "__main__":
    main()

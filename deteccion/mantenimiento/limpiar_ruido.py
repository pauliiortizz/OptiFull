"""Borra, para un dia ya analizado, las 'personas' que en realidad son ruido
de deteccion (falsos positivos de un frame o casi) -- ver
Persistencia.limpiar_detecciones_espurias() y PersonTracker.min_frames_confirmacion
(el fix que evita que esto se siga generando en corridas nuevas).

IMPORTANTE: correr SIEMPRE fusionar_dia.py de ese mismo dia ANTES que este
script -- si no, se puede borrar una 'persona' que en realidad es la raiz de
una cadena fusionada valida.

Uso: python -m deteccion.mantenimiento.limpiar_ruido 2026-05-20 [duracion_min_seg]
"""
import sys
from datetime import date

from deteccion import config
from deteccion.persistencia import Persistencia


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Uso: python -m deteccion.mantenimiento.limpiar_ruido YYYY-MM-DD [duracion_min_seg]")
        sys.exit(1)
    fecha = date.fromisoformat(sys.argv[1])
    duracion_min_seg = float(sys.argv[2]) if len(sys.argv) == 3 else 2.0

    persistencia = Persistencia(
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS,
        config.CAMARA_NOMBRES, config.GRUPOS_CAMARA, config.REID_VENTANA_HORAS,
    )
    if not persistencia.conectar():
        print("[AVISO] No se pudo conectar a la BD.")
        sys.exit(1)

    borradas = persistencia.limpiar_detecciones_espurias(fecha, duracion_min_seg)
    persistencia.cerrar()
    print(f"Borradas ({fecha}, <{duracion_min_seg}s): {borradas}")


if __name__ == "__main__":
    main()

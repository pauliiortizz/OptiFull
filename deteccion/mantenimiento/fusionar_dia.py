"""Fusiona retroactivamente, para un dia ya analizado, los clientes vistos por
camaras distintas del mismo grupo fisico (ver GRUPOS_CAMARA en config.py) casi
al mismo instante -- correccion posterior para sesiones que se analizaron
antes de que la sesion de la camara vecina existiera todavia en la BD
(auditar_sesion(), al vuelo, solo compara contra lo que ya estaba guardado en
ese momento). No borra ni recrea nada, solo reapunta cliente_id al canonico
de cada grupo fusionado.

Uso: python -m deteccion.mantenimiento.fusionar_dia 2026-05-20
"""
import sys
from datetime import date

from deteccion import config
from deteccion.persistencia import Persistencia


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python -m deteccion.mantenimiento.fusionar_dia YYYY-MM-DD")
        sys.exit(1)
    fecha = date.fromisoformat(sys.argv[1])

    persistencia = Persistencia(
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS,
        config.CAMARA_NOMBRES, config.GRUPOS_CAMARA, config.REID_VENTANA_HORAS,
    )
    if not persistencia.conectar():
        print("[AVISO] No se pudo conectar a la BD.")
        sys.exit(1)

    continuidad = persistencia.fusionar_continuidad_sesiones(fecha, config.UMBRAL_MISMO_MOMENTO_SEG)
    cross_camara = persistencia.fusionar_cross_camara_dia(fecha, config.UMBRAL_MISMO_MOMENTO_SEG)
    persistencia.cerrar()
    print(f"Resumen ({fecha}): continuidad_misma_camara={continuidad}, cross_camara={cross_camara}")


if __name__ == "__main__":
    main()

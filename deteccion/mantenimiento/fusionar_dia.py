"""Fusiona retroactivamente, para un dia ya analizado, (1) personas divididas
por el corte entre videos consecutivos de la MISMA camara y (2) clientes
vistos por camaras distintas del mismo grupo fisico (ver GRUPOS_CAMARA en
config.py) casi al mismo instante -- correccion posterior para sesiones que
se analizaron antes de que la sesion vecina existiera todavia en la BD
(auditar_sesion(), al vuelo, solo compara contra lo que ya estaba guardado en
ese momento). No borra ni recrea nada, solo reapunta cliente_id al canonico
de cada grupo fusionado.

OJO: desde que main.py llama a esto automaticamente al cerrar cada sesion
(ver Persistencia.fusionar_dia_hasta_converger()), este script YA NO HACE
FALTA para el dia a dia -- queda solo para reprocesar retroactivamente un dia
analizado ANTES de ese cambio, o para forzar una corrida manual puntual.

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

    resumen = persistencia.fusionar_dia_hasta_converger(
        fecha, config.CONTINUIDAD_VENTANA_SEG, config.CONTINUIDAD_ALTA_CONFIANZA_SEG,
        config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS,
    )
    persistencia.cerrar()
    print(f"Resumen ({fecha}): continuidad_misma_camara={resumen['continuidad']}, "
          f"cross_camara={resumen['cross_camara']} (en {resumen['pasadas']} pasada(s)).")


if __name__ == "__main__":
    main()

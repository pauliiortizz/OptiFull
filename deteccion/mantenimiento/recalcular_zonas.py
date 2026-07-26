"""Corrige retroactivamente el sesgo de perspectiva en 'trayectorias': hasta
ahora la posicion guardada era el CENTRO geometrico del bounding box (altura
del pecho), que desde una camara elevada en angulo no representa bien donde
esta parada la persona en el piso -- ver el comentario en
PersonTracker.procesar_frame() (tracking.py). Este script:

1) recalcula centroide_x/y y zona_id de CADA punto de trayectoria ya
   guardado, usando la base del bbox (bbox_x1/x2/y2) en vez del centro;
2) recalcula personas.zona_id (zona dominante) con los datos ya corregidos;
3) vuelve a correr la limpieza de trayectorias fuera de zona (clientes en
   Zona Caja / empleados en Zona Gondolas o Salon), por si la correccion de
   arriba destapo nuevas violaciones o dejo alguna vieja sin resolver.

Uso: python -m deteccion.mantenimiento.recalcular_zonas
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

    resumen_zonas = persistencia.recalcular_zonas_por_pie()
    personas_actualizadas = persistencia.recalcular_zona_dominante_personas()
    borrados = persistencia.limpiar_trayectorias_fuera_de_zona()

    persistencia.cerrar()
    print()
    print(f"Puntos recalculados por camara : {resumen_zonas}")
    print(f"Personas con zona dominante actualizada: {personas_actualizadas}")
    print(f"Puntos borrados por violar zona tras el recalculo: {borrados}")


if __name__ == "__main__":
    main()

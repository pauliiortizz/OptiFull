"""Backfill retroactivo de 'eventos' (COMPRA_NORMAL/TRANSITO_SIN_COMPRA) para
personas ya analizadas ANTES de que existiera esta clasificacion, usando solo
lo que ya esta guardado en 'trayectorias' -- sin volver a correr YOLO sobre
el video original (que ademas ya no esta disponible para la mayoria de estas
sesiones viejas). Por eso NUNCA genera POSIBLE_HURTO: esa clasificacion
depende de tomo_producto (deteccion de producto por YOLO), que no se puede
reconstruir retroactivamente. Ver Persistencia.analizar_compras_retroactivo()
para el detalle completo de la regla (proximidad a Zona Caja + empleado
presente en la misma ventana de tiempo).

Idempotente: salta personas que YA tienen una fila en 'eventos' (de un
analisis en vivo o de una corrida anterior de este mismo script) -- se puede
correr de nuevo sin duplicar nada.

Uso: python -m deteccion.mantenimiento.analizar_compras_retroactivo
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

    resumen = persistencia.analizar_compras_retroactivo()
    persistencia.cerrar()
    print(f"Resumen: {resumen}")


if __name__ == "__main__":
    main()

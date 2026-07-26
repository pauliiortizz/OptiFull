"""Siembra las tablas 'empleados'/'empleados_descripciones' (referencia para
reconocer a los 3 empleados del local en Zona Caja, ver auditar_sesion() paso
2) a partir de lo que YA esta confirmado en 'personas' (es_empleado = true) --
ver Persistencia.poblar_empleados_desde_personas(). Solo corre si 'empleados'
esta vacia (no duplica en una segunda corrida).

OJO: una de las 3 cadenas detectadas (ex-cliente_id 114 al momento de escribir
esto) tiene colores de ropa MUY inconsistentes entre sus apariciones (rojo,
verde, naranja, negro, gris, beige...) -- eso es indicio de que esa cadena
fusiono a mas de una persona real por error, no de que sea un mismo empleado
visto con luz distinta. Se carga igual (decision del usuario), pero conviene
revisarla despues con /reportes/posibles-empleados o a mano.

Uso: python -m deteccion.mantenimiento.poblar_empleados
"""
from deteccion import config
from deteccion.persistencia import Persistencia

# cliente_id (raiz de la cadena en 'personas') -> nombre a usarle en 'empleados'.
# Una raiz que no aparezca aca se nombra automaticamente 'Empleado <cliente_id>'.
NOMBRES = {}


def main() -> None:
    persistencia = Persistencia(
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS,
        config.CAMARA_NOMBRES, config.GRUPOS_CAMARA, config.REID_VENTANA_HORAS,
    )
    if not persistencia.conectar():
        print("[AVISO] No se pudo conectar a la BD.")
        return

    resumen = persistencia.poblar_empleados_desde_personas(NOMBRES)
    persistencia.cerrar()
    print(f"Resumen: {resumen}")


if __name__ == "__main__":
    main()

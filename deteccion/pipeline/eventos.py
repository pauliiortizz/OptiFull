"""Clasificacion de comportamiento (Escenario A/B/C) a partir de la secuencia
de zonas recorridas y el flag tomar_producto de una VISITA ya cerrada (ver
PersonTracker._cerrar_segmento). Es una maquina de estados en Python pura --
no llama a Gemini/Groq/Claude para esto: la IA en este pipeline se reserva
para Re-ID (comparar descripciones visuales), no para juzgar la secuencia de
zonas, que ya es informacion estructurada y determinista una vez que sabemos
tipo de zona + tomar_producto."""
from typing import Optional


def clasificar_evento(
    secuencia_zonas_ids: list,
    tomo_producto: bool,
    paso_por_caja: bool,
    zona_nombre_por_id: dict,
) -> dict:
    """secuencia_zonas_ids: ids de zona en el orden en que la persona los
    visito durante ESTA visita (deduplicados consecutivos, ver
    PersonTracker.actualizar_zona) -- solo se usa para el detalle legible
    ('secuencia_zonas_recorridas'), no para decidir 'paso_por_caja'.
    zona_nombre_por_id: mapa id->nombre de 'zonas' (ver
    Persistencia.cargar_zonas), para no acoplar esta funcion a los ids
    concretos de una camara en particular.

    'paso_por_caja' viene ya calculado por PersonTracker.marcar_acercamiento_caja
    (ver utils.cerca_de_zona_tipo): en este sistema Zona Caja es el lado del
    EMPLEADO del mostrador, un cliente pagando se ACERCA pero casi nunca pisa
    el poligono -- por eso NO se deriva de si 'caja' aparece en
    secuencia_zonas_ids (eso exigiria point_in_polygon exacto, que en la
    practica casi nunca pasa para un cliente real). Ademas exige que haya
    habido OTRA persona (posible empleado) presente en Zona Caja al mismo
    tiempo -- ver main.py, cerca_de_caja_ids.

    'paso_por_caja' es la condicion DOMINANTE, por encima de tomo_producto:
    en un kiosco/bar real, comprar no siempre implica agarrar algo de una
    gondola/heladera que YOLO pueda detectar -- puede ser un producto que la
    cajera entrega directo en el mostrador (golosinas, cigarrillos) o un
    pedido que se prepara en cocina (cafe, tostado, hamburguesa) y el cliente
    espera parado cerca de caja. En NINGUNO de esos casos hay un objeto
    fisico que la deteccion por YOLO pueda confirmar -- pero el cliente SI
    pago, y eso es lo que paso_por_caja captura de forma directa (via
    posicion, no via deteccion de objetos).

    Reglas (ver especificacion original, extendida):
    - ESCENARIO A (COMPRA_NORMAL): se acerco a Zona Caja con alguien mas
      presente (paso_por_caja=True) -- sin importar si tambien hubo
      tomo_producto o no (cubre compra en gondola, compra en mostrador, y
      pedido preparado en cocina).
    - ESCENARIO B (POSIBLE_HURTO): tomo_producto=True (agarro algo de
      gondola/heladera) pero NUNCA se acerco a pagar -- se retiro (a Salon/
      Entrada-Salida) sin pasar por caja.
    - ESCENARIO C (TRANSITO_SIN_COMPRA): ni tomo_producto ni paso_por_caja en
      toda la visita, sin importar por donde haya caminado.
    """
    if paso_por_caja:
        accion = "COMPRA_NORMAL"
    elif tomo_producto:
        accion = "POSIBLE_HURTO"
    else:
        accion = "TRANSITO_SIN_COMPRA"

    es_sospechoso = accion == "POSIBLE_HURTO"

    return {
        "accion_detectada":            accion,
        "es_sospechoso":               es_sospechoso,
        "nivel_alerta":                "ALTA" if es_sospechoso else "NINGUNA",
        "tomo_producto":               tomo_producto,
        "paso_por_caja":               paso_por_caja,
        "secuencia_zonas_recorridas":  [
            zona_nombre_por_id.get(zid, f"zona_{zid}") for zid in secuencia_zonas_ids
        ],
    }


def resumen_evento(evento: dict) -> str:
    """Texto breve para 'alertas.descripcion' / logging -- no se manda a
    ningun modelo, es solo una interpolacion legible del resultado ya
    calculado por clasificar_evento()."""
    recorrido = " -> ".join(evento["secuencia_zonas_recorridas"]) or "(sin zonas registradas)"
    if evento["accion_detectada"] == "COMPRA_NORMAL":
        origen = "tomo un producto y" if evento["tomo_producto"] else "compro en el mostrador y"
        return f"Compra normal: {origen} paso por caja. Recorrido: {recorrido}."
    if evento["accion_detectada"] == "POSIBLE_HURTO":
        return f"Tomo un producto y se retiro SIN pasar por caja. Recorrido: {recorrido}."
    return f"Transito sin compra (no tomo ningun producto ni paso por caja). Recorrido: {recorrido}."

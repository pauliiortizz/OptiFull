"""
CashierInterfaceAgent
---------------------
Abstrae la interacción con la cajera. La cajera SIEMPRE tiene la
última palabra: el sistema identifica al producto, se lo muestra,
ella confirma o corrige, e ingresa la cantidad de unidades. Recién
ahí el StockAgent descuenta.

Por qué es importante:
  - El mismo producto puede venir en varias unidades (cliente compra
    3 Cocas iguales, la cámara ve una sola vez).
  - La cajera es responsable legal del ticket, tiene que poder
    corregir errores del sistema.
  - Para la tesis: mantener a la persona "in the loop" es un patrón
    fundamental cuando el sistema no es 100% confiable.

Este agente tiene 3 métodos según el caso:
  - confirmar_producto:   producto identificado con confianza, cajera
                          confirma + carga cantidad
  - elegir_entre_candidatos: matching ambiguo, cajera elige de una
                          lista + carga cantidad
  - producto_manual:      matching falló, cajera carga producto a
                          mano (SKU o busqueda)

Modo de operación:
  - "consola" (default):  usa input() para pruebas rápidas con videos
                          pregrabados. Sirve para el prototipo.
  - En producción se cambia esta clase por una GUI (Tkinter) o
    webapp (Flask + WebSocket), MANTENIENDO LA MISMA INTERFAZ:
    los otros agentes no se enteran del cambio.
"""


class CashierInterfaceAgent:
    def __init__(self, modo="consola"):
        self.modo = modo

    def confirmar_producto(self, producto, confianza_llm):
        """
        El sistema identificó UN producto con confianza suficiente.
        La cajera lo confirma e ingresa cantidad.

        Devuelve: (producto_confirmado, cantidad) o (None, 0) si cancela.
        """
        print(f"\n╔══════════════════════════════════════════════════════")
        print(f"║ PRODUCTO IDENTIFICADO")
        print(f"╠══════════════════════════════════════════════════════")
        print(f"║ {producto['nombre']}")
        print(f"║ SKU: {producto['sku']}  |  Confianza LLM: {confianza_llm:.0%}")
        print(f"╚══════════════════════════════════════════════════════")
        print(f"Ingrese CANTIDAD de unidades (Enter=1, 0=cancelar, c=corregir):")

        respuesta = input("> ").strip().lower()

        if respuesta == "":
            return producto, 1
        if respuesta == "0":
            return None, 0
        if respuesta == "c":
            return self.producto_manual()
        try:
            cantidad = int(respuesta)
            if cantidad < 0:
                print("Cantidad inválida, se cancela.")
                return None, 0
            return producto, cantidad
        except ValueError:
            print("Entrada inválida, se cancela.")
            return None, 0

    def elegir_entre_candidatos(self, candidatos, datos_llm=None):
        """
        El matching quedó ambiguo (varios productos posibles).
        La cajera elige cuál es + ingresa cantidad.

        candidatos: lista de dicts producto
        Devuelve: (producto_elegido, cantidad) o (None, 0) si cancela.
        """
        print(f"\n╔══════════════════════════════════════════════════════")
        print(f"║ VARIOS PRODUCTOS POSIBLES - ELIJA UNO")
        print(f"╠══════════════════════════════════════════════════════")
        if datos_llm:
            print(f"║ El sistema vio: marca={datos_llm.get('marca')}, "
                  f"variante={datos_llm.get('variante')}, "
                  f"tamano={datos_llm.get('tamano')}")
            print(f"╠══════════════════════════════════════════════════════")
        for i, p in enumerate(candidatos, 1):
            print(f"║ {i}) {p['nombre']}  (SKU {p['sku']})")
        print(f"╚══════════════════════════════════════════════════════")
        print(f"Ingrese N° del producto (0=cancelar, m=cargar manual):")

        respuesta = input("> ").strip().lower()

        if respuesta == "0":
            return None, 0
        if respuesta == "m":
            return self.producto_manual()
        try:
            idx = int(respuesta) - 1
            if not 0 <= idx < len(candidatos):
                print("Opción fuera de rango, se cancela.")
                return None, 0
            producto = candidatos[idx]
        except ValueError:
            print("Entrada inválida, se cancela.")
            return None, 0

        # Ya eligió producto, ahora la cantidad
        print(f"Cantidad de {producto['nombre']} (Enter=1, 0=cancelar):")
        respuesta = input("> ").strip()
        if respuesta == "":
            return producto, 1
        if respuesta == "0":
            return None, 0
        try:
            cantidad = int(respuesta)
            return (producto, cantidad) if cantidad > 0 else (None, 0)
        except ValueError:
            return None, 0

    def producto_manual(self):
        """
        El sistema no pudo identificar (o la cajera quiere corregir).
        Carga manual del SKU + cantidad.

        Devuelve: ({"sku": sku_ingresado}, cantidad) o (None, 0).
        En producción esto sería un buscador con auto-completado.
        """
        print(f"\n╔══════════════════════════════════════════════════════")
        print(f"║ CARGA MANUAL")
        print(f"╚══════════════════════════════════════════════════════")
        print(f"Ingrese SKU del producto (Enter=cancelar):")
        sku = input("> ").strip()
        if not sku:
            return None, 0
        print(f"Cantidad (Enter=1):")
        respuesta = input("> ").strip()
        cantidad = 1 if respuesta == "" else int(respuesta) if respuesta.isdigit() else 0
        if cantidad <= 0:
            return None, 0
        # Devolvemos un dict mínimo; el orquestador va a resolver el
        # nombre completo contra la BD antes de descontar.
        return {"sku": sku, "nombre": f"(cargado manualmente: {sku})"}, cantidad

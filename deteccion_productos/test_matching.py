"""
test_matching.py
----------------
Prueba el MatchingAgent SIN llamar al LLM ni usar video.

Simula respuestas del LLM (JSONs hardcodeados) y verifica que el
matching identifica bien el producto. Sirve para calibrar antes de
gastar en llamadas al API.

Correr: python test_matching.py
"""

from agents.matching_agent import MatchingAgent
from agents.stock_agent import StockAgent


CASOS = [
    # (JSON que devolvería el LLM, sku esperado o None)
    (
        {"producto_detectado": True, "marca": "Coca-Cola", "nombre_producto": "Coca-Cola Zero",
         "variante": "Zero", "tamano": {"valor": 500, "unidad": "ml"},
         "categoria": "gaseosa", "confianza": 0.95},
        "SKU002"
    ),
    (
        {"producto_detectado": True, "marca": "Coca-Cola", "nombre_producto": "Coca-Cola",
         "variante": "Original", "tamano": {"valor": 500, "unidad": "ml"},
         "categoria": "gaseosa", "confianza": 0.9},
        "SKU001"
    ),
    (
        # LLM detectó Coca 1.5L pero no supo si era Zero u Original
        {"producto_detectado": True, "marca": "Coca-Cola", "nombre_producto": "Coca-Cola",
         "variante": None, "tamano": {"valor": 1.5, "unidad": "l"},
         "categoria": "gaseosa", "confianza": 0.75},
        "SKU003"  # deberia matchear con Original por default (o pedir confirmar)
    ),
    (
        # Villa del Sur - sin gas y sin variante clara en el envase
        {"producto_detectado": True, "marca": "Villa del Sur", "nombre_producto": "Villa del Sur",
         "variante": "Sin Gas", "tamano": {"valor": 500, "unidad": "ml"},
         "categoria": "agua", "confianza": 0.88},
        "SKU007"
    ),
    (
        # Red Bull
        {"producto_detectado": True, "marca": "Red Bull", "nombre_producto": "Red Bull",
         "variante": "Original", "tamano": {"valor": 250, "unidad": "ml"},
         "categoria": "energizante", "confianza": 0.98},
        "SKU012"
    ),
    (
        # Milka
        {"producto_detectado": True, "marca": "Milka", "nombre_producto": "Chocolate Milka",
         "variante": "Leche", "tamano": {"valor": 100, "unidad": "g"},
         "categoria": "chocolate", "confianza": 0.9},
        "SKU018"
    ),
    (
        # Producto que NO está en la base
        {"producto_detectado": True, "marca": "Pantene", "nombre_producto": "Shampoo Pantene",
         "variante": "Liso Extremo", "tamano": {"valor": 400, "unidad": "ml"},
         "categoria": "higiene", "confianza": 0.95},
        None
    ),
    (
        # LLM no vio producto
        {"producto_detectado": False},
        None
    ),
    (
        # LLM con confianza baja
        {"producto_detectado": True, "marca": "Coca-Cola", "nombre_producto": "?",
         "variante": None, "tamano": {"valor": 500, "unidad": "ml"},
         "categoria": "gaseosa", "confianza": 0.4},
        None  # confianza < UMBRAL_CONFIANZA_LLM
    ),
    (
        # Typo del LLM en la marca ("Tofti" en vez de "Tofi"). Con el
        # matching viejo (cascada + umbral % sobre marca) esto se
        # perdía del todo, aunque el resto del producto coincida.
        {"producto_detectado": True, "marca": "Tofti", "nombre_producto": "Alfajor Tofti Negro",
         "variante": "Chocolate Negro", "tamano": {"valor": 46, "unidad": "g"},
         "categoria": "alfajor", "confianza": 0.9},
        "SKU025"
    ),
    (
        # Mismo caso, otra variante de typo (letra duplicada: "Toffi")
        {"producto_detectado": True, "marca": "Toffi", "nombre_producto": "Alfajor Toffi Negro",
         "variante": "Chocolate Negro", "tamano": {"valor": 46, "unidad": "g"},
         "categoria": "alfajor", "confianza": 0.9},
        "SKU025"
    ),
    (
        # Typo en la VARIANTE en vez de la marca ("Orignal" sin la "i")
        {"producto_detectado": True, "marca": "Red Bull", "nombre_producto": "Red Bull",
         "variante": "Orignal", "tamano": {"valor": 250, "unidad": "ml"},
         "categoria": "energizante", "confianza": 0.95},
        "SKU012"
    ),
    (
        # TAMAÑO mal leído: el envase dice 100g, el LLM leyó 92g
        # (~8% de error). Antes esto rompía el matching por completo
        # (filtro duro de tamaño); ahora sigue reconociendo el producto.
        {"producto_detectado": True, "marca": "Milka", "nombre_producto": "Chocolate Milka Leche",
         "variante": "Leche", "tamano": {"valor": 92, "unidad": "g"},
         "categoria": "chocolate", "confianza": 0.9},
        "SKU018"
    ),
    (
        # Caso más exigente: hay DOS SKUs de la misma marca/variante que
        # solo se distinguen por tamaño (Lays Clasicas 100g vs 134g). Con
        # un tamaño leído "88g" (más cerca de 100g), tiene que elegir el
        # de 100g y no confundirlo con el de 134g.
        {"producto_detectado": True, "marca": "Lays", "nombre_producto": "Papas Lays Clasicas",
         "variante": "Clasicas", "tamano": {"valor": 88, "unidad": "g"},
         "categoria": "snack", "confianza": 0.9},
        "SKU016"
    ),
    (
        # Caso real reportado: el LLM invirtió los campos (puso la
        # categoría "Alfajor" en 'marca' y la marca real "Toffi" en
        # 'nombre_producto'), variante abreviada ("negro" en vez de
        # "Chocolate Negro") y tamaño con error de lectura (40g en vez
        # de 46g). Antes esto daba "sin_coincidencia_suficiente".
        {"producto_detectado": True, "marca": "Alfajor", "nombre_producto": "Toffi",
         "variante": "negro", "tamano": {"valor": 40, "unidad": "g"},
         "categoria": "Golosinas", "confianza": 0.95},
        "SKU025"
    ),
    (
        {"producto_detectado": True, "marca": "Saladix", "nombre_producto": "Saladix Salame",
         "variante": "Salame", "tamano": {"valor": 92, "unidad": "g"},
         "categoria": "snack", "confianza": 0.95},
        "SKU026"
    ),
    (
        # Marca CORRECTA ("Saladix"), pero variante que no está en la
        # base ("Calabresa" vs. el único Saladix real, "Salame") y
        # tamaño bastante alejado (40g vs 100g real). Sin relación de
        # texto entre "calabresa" y "salame" (ni typo ni contención),
        # el score de variante da 0 y el combinado no alcanza para
        # sugerir nada — mejor "no reconocido" (carga manual) que
        # sugerirle a la cajera un producto que probablemente no es
        # el correcto y arriesgar que lo confirme sin fijarse bien.
        {"producto_detectado": True, "marca": "Saladix", "nombre_producto": "Saladix Calabresa",
         "variante": "Calabresa", "tamano": {"valor": 40, "unidad": "g"},
         "categoria": "snack", "confianza": 0.95},
        None
    ),
    (
        # Caso real reportado: marca CORRECTA ("Lays") y sin lectura de
        # tamaño (envase no legible). "Lays" y "Ades" son dos marcas de
        # 4 letras sin relación, pero por casualidad de letras el %
        # clásico les daba 50% de similitud, coincidencia suficiente
        # para colar "Ades Manzana" como candidato. No debería aparecer.
        {"producto_detectado": True, "marca": "Lays", "nombre_producto": "Lays Clásicas",
         "variante": "Clásicas", "tamano": None,
         "categoria": "snack", "confianza": 0.85},
        "SKU016"
    ),
    (
        # Caso real reportado: marca CORRECTA ("Chuker") pero tamaño
        # mal leído (150ml en vez de 200ml). "Chuker" comparte letras
        # sueltas con "Cofler" (50%) y con "Hileret" (46%) por pura
        # casualidad, sin relación real — no deberían aparecer como
        # candidatos.
        {"producto_detectado": True, "marca": "Chuker", "nombre_producto": "Chuker",
         "variante": None, "tamano": {"valor": 150, "unidad": "ml"},
         "categoria": "condimento", "confianza": 0.75},
        "SKU028"
    ),
    (
        # Caso real reportado: dos frames del mismo Alicante Esencia de
        # Vainilla, a 1 segundo de diferencia, daban resultados
        # distintos. Acá el LLM no detectó la variante (None) y además
        # leyó mal el tamaño (30ml en vez de 100ml). Antes, variante
        # None se asumía "original" y penalizaba de más (Alicante no
        # tiene variante "Original", tiene "Vainilla") -> no_reconocido.
        # Ahora variante sin dato es neutro, no una suposición.
        {"producto_detectado": True, "marca": "Alicante", "nombre_producto": "Esencia de Vainilla",
         "variante": None, "tamano": {"valor": 30, "unidad": "ml"},
         "categoria": "esencia", "confianza": 0.85},
        "SKU038"
    ),
]


def main():
    stock = StockAgent()
    productos = stock.cargar_productos()
    matcher = MatchingAgent(productos)
    print(f"Base con {len(productos)} productos\n" + "-" * 80)

    aciertos = 0
    for datos_llm, sku_esperado in CASOS:
        r = matcher.identificar(datos_llm)
        estado = r["estado"]
        if estado == "no_reconocido":
            sku_obt = None
            det = f"NO reconocido ({r['razon']})"
        else:
            sku_obt = r["producto"]["sku"]
            det = f"{r['producto']['nombre']} ({estado})"
        ok = sku_obt == sku_esperado
        aciertos += int(ok)
        marca = "✔" if ok else "✘"
        tam = datos_llm.get('tamano') or {}
        entrada = f"{datos_llm.get('marca', '?')} {datos_llm.get('variante') or ''} " \
                   f"{tam.get('valor', '?')}" \
                   f"{tam.get('unidad', '')}"
        print(f"{marca} LLM: {entrada:40s} -> {det}")
    print("-" * 80 + f"\nAciertos: {aciertos}/{len(CASOS)}")
    stock.close()


if __name__ == "__main__":
    main()

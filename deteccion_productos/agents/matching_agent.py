"""
MatchingAgent
-------------
Recibe el JSON estructurado del VisionAgent y busca el producto
correspondiente en la base de datos.

Diseño (marca como piso + score combinado):

  1. La MARCA sigue siendo el índice primario: un producto solo entra
     a competir si su marca supera un piso mínimo de similitud
     (`UMBRAL_MARCA_MINIMO`), calculado con la misma función tolerante
     a typos que se usa para todo el texto. El piso es deliberadamente
     bajo: un typo real pasa sin problema (puntúa 80-95); lo que
     excluye son marcas genuinamente distintas.
  2. Entre los que pasaron ese piso, se calcula un puntaje 0-100 en
     las tres dimensiones (marca, variante, tamaño) y se combinan en
     un score único ponderado. Se elige el producto con mejor score,
     y según qué tan alto es y qué tan lejos está el segundo:

       - Score alto y sin ambigüedad -> reconocido.
       - Score razonable pero no tan alto, o varios candidatos
         parejos -> confirmar (la cajera elige).
       - Score muy bajo, o ningún producto pasó el piso de marca
         -> no reconocido.

Por qué la marca SÍ actúa como piso pero tamaño/variante NO:
  Todo lo que sabemos del producto viene de una lectura del LLM sobre
  una imagen, y una lectura puede fallar en cualquier campo (marca,
  variante o tamaño). Por eso ninguno de los tres exige una
  coincidencia perfecta. Pero el tamaño en particular puede coincidir
  por pura casualidad entre productos de marcas totalmente distintas
  (un snack de 40g y un alfajor de 46g pesan parecido sin ser
  parecidos en nada más). Si se puntuara todo junto sin ningún piso,
  esa coincidencia podría "rescatar" un producto de otra marca y
  meterlo como candidato — un problema que crece con el tamaño del
  catálogo, no algo puntual de dos productos. El piso de marca evita
  eso sin perder la tolerancia a typos que motivó sacar los filtros
  duros en primer lugar (ver `UMBRAL_MARCA_MINIMO` en `config.py`).

Funciones de score:
  - `similitud(a, b)`: para texto (marca, variante). Tolera una
    cantidad ABSOLUTA de ediciones según el largo del string (un typo
    real pasa sin problema). Si NO entra en esa tolerancia, NO se usa
    un % de similitud genérico (tipo `fuzz.ratio`). Se probó y es poco
    confiable en este dominio, en cualquier largo: dos palabras sin
    ninguna relación real pueden compartir letras sueltas en un orden
    parecido y sacar un % alto igual por pura casualidad — "Lays" vs
    "Ades" comparten 'a' y 's' y dan 50%; "Chuker" vs "Cofler"
    comparten 'c'..'e'..'r' y también dan 50%. Ninguno de los dos
    pares tiene relación real. En cambio, se usa una señal más
    específica: si una palabra está CONTENIDA dentro de la otra (ej:
    "negro" dentro de "chocolate negro" — packaging real donde una es
    parte literal de la otra), se puntúa proporcional a cuánto cubre.
    Si no hay ni tolerancia de typo ni contención, no es un match.
  - `_score_tamano(...)`: para el tamaño. Proporcional a la diferencia
    relativa entre el valor leído y el del producto, no un corte
    exacto ± tolerancia.
"""

import unicodedata

from rapidfuzz.distance import Levenshtein

from config import (
    UMBRAL_CONFIANZA_LLM,
    TOLERANCIA_EDICION_CORTA,
    TOLERANCIA_EDICION_MEDIA,
    TOLERANCIA_EDICION_LARGA,
    PENALIZACION_TAMANO,
    UMBRAL_MARCA_MINIMO,
    UMBRAL_RESPALDO_NOMBRE,
    SCORE_VARIANTE_SIN_DATO,
    PESO_MARCA,
    PESO_VARIANTE,
    PESO_TAMANO,
    UMBRAL_AUTOACEPTAR,
    UMBRAL_DESCARTE,
    MARGEN_AMBIGUEDAD,
)


def normalizar(texto):
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.replace("-", " ")
    return " ".join(texto.lower().split())


def _tolerancia_por_largo(largo):
    if largo <= 5:
        return TOLERANCIA_EDICION_CORTA
    if largo <= 9:
        return TOLERANCIA_EDICION_MEDIA
    return TOLERANCIA_EDICION_LARGA


def similitud(a, b):
    """
    Similitud 0-100 entre dos strings ya normalizados.

    Tolera una cantidad ABSOLUTA de ediciones (insertar/borrar/cambiar
    una letra) según el largo del string más largo. Si la distancia
    de edición entra en esa tolerancia, se considera prácticamente el
    mismo texto (typo del LLM leyendo el envase).

    Si NO entra en esa tolerancia, NO se usa un % de similitud genérico
    (tipo `fuzz.ratio`). Se probó y es poco confiable en este dominio,
    en cualquier largo: dos palabras sin ninguna relación real pueden
    compartir letras sueltas en un orden parecido y sacar un % alto
    igual por pura casualidad — "Lays" vs "Ades" comparten 'a' y 's' y
    dan 50%; "Chuker" vs "Cofler" comparten 'c'..'e'..'r' y también dan
    50%. Ninguno de los dos pares tiene relación real.

    En cambio, se usa una señal más específica: si una palabra está
    CONTENIDA dentro de la otra (ej: "negro" dentro de "chocolate
    negro" — packaging real donde una es parte literal de la otra), se
    puntúa proporcional a cuánto cubre. Si no hay ni tolerancia de
    typo ni contención, no es un match.
    """
    if not a or not b:
        return 0
    distancia = Levenshtein.distance(a, b)
    largo = max(len(a), len(b))
    if distancia <= _tolerancia_por_largo(largo):
        return 100 - distancia * 5
    corto, extenso = (a, b) if len(a) <= len(b) else (b, a)
    if corto in extenso:
        return 100 * len(corto) / len(extenso)
    return 0


def _mejor_similitud_contra_tokens(texto, objetivo):
    """
    Compara 'objetivo' contra cada palabra de 'texto' y devuelve el
    mejor score. Sirve de respaldo para cuando el LLM invirtió los
    campos y puso la marca real dentro de 'nombre_producto' (ej:
    devolvió marca="Alfajor" y nombre_producto="Toffi"): buscamos la
    marca ahí también, palabra por palabra, en vez de comparar la
    frase completa contra un nombre de marca corto.
    """
    if not texto:
        return 0
    return max((similitud(tok, objetivo) for tok in texto.split()), default=0)


def convertir_a_ml(valor, unidad):
    """
    Normaliza tamaños a una unidad común para poder comparar.
    Todos los líquidos -> ml, todos los sólidos -> g.
    Devuelve (valor_normalizado, tipo) donde tipo es 'volumen' o 'peso'.
    """
    if valor is None or unidad is None:
        return None, None
    unidad = unidad.lower().strip()
    if unidad in ("ml", "cc"):
        return valor, "volumen"
    if unidad in ("l", "lt", "litro", "litros"):
        return valor * 1000, "volumen"
    if unidad in ("g", "gr"):
        return valor, "peso"
    if unidad in ("kg",):
        return valor * 1000, "peso"
    if unidad in ("unidades", "u", "un"):
        return valor, "unidades"
    return valor, "otro"


def _score_tamano(prod, valor_llm, unidad_llm):
    """
    Score 0-100 de qué tan parecido es el tamaño informado por el LLM
    al del producto. Es proporcional a la diferencia relativa, no un
    corte exacto: un desvío chico (46g leído como 40g) sigue sumando
    puntos altos, uno grande (500ml leído como 1.5L) cae a casi 0.
    Mismo motivo que en `similitud`: la lectura del envase no es
    perfecta y no queremos perder el match entero por eso.
    """
    val_prod, tipo_prod = convertir_a_ml(prod.get("tamano_valor"), prod.get("tamano_unidad"))
    val_llm, tipo_llm = convertir_a_ml(valor_llm, unidad_llm)
    if val_prod is None or val_llm is None:
        return 0
    if tipo_prod != tipo_llm:
        return 0
    diff_relativa = abs(val_prod - val_llm) / val_prod
    return max(0, 100 - diff_relativa * PENALIZACION_TAMANO)


class MatchingAgent:
    def __init__(self, productos):
        """
        productos: lista de dicts desde la BD, con columnas:
            sku, nombre, marca, variante, tamano_valor, tamano_unidad, categoria
        """
        self.productos = productos

    def identificar(self, datos_llm):
        """
        datos_llm: dict devuelto por VisionAgent.analizar()
        Devuelve:
          {"estado": "reconocido",    "producto": {...}, "confianza": 0.92}
          {"estado": "confirmar",     "producto": {...}, "candidatos": [...], "motivo": "..."}
          {"estado": "no_reconocido", "razon": "...", "datos_llm": {...}}
        """
        # Caso 1: el LLM no vio producto
        if not datos_llm.get("producto_detectado"):
            return {"estado": "no_reconocido", "razon": "sin_producto", "datos_llm": datos_llm}

        conf_llm = datos_llm.get("confianza", 0)
        if conf_llm < UMBRAL_CONFIANZA_LLM:
            return {"estado": "no_reconocido", "razon": "confianza_llm_baja",
                    "datos_llm": datos_llm}

        marca_llm = normalizar(datos_llm.get("marca"))
        nombre_llm = normalizar(datos_llm.get("nombre_producto"))
        # Si el LLM no vio la variante, es "no sé", no "es Original":
        # asumir "original" penaliza productos de un solo sabor que no
        # tienen ninguna variante llamada así (ej. una esencia de
        # vainilla). variante_llm queda None y se puntúa aparte.
        variante_raw = datos_llm.get("variante")
        variante_llm = normalizar(variante_raw) if variante_raw else None
        tam = datos_llm.get("tamano") or {}
        valor_llm = tam.get("valor")
        unidad_llm = tam.get("unidad")

        # Piso de marca primero (ver docstring del módulo): un producto
        # de otra marca no debería poder "colarse" solo porque el
        # tamaño coincide por casualidad. El piso es bajo y usa la
        # misma función tolerante a typos, así que un error de lectura
        # real en la marca sigue pasando sin problema.
        scoreados = []
        for p in self.productos:
            marca_db = normalizar(p["marca"])
            score_marca = similitud(marca_llm, marca_db)
            score_respaldo = _mejor_similitud_contra_tokens(nombre_llm, marca_db)
            # El respaldo busca en más lugares (cada palabra de
            # nombre_producto), así que tiene más chances de un choque
            # casual: solo se lo deja "ganar" si el parecido es lo
            # bastante alto como para ser la marca real, no una
            # coincidencia de letras con la variante u otra palabra.
            if score_respaldo >= UMBRAL_RESPALDO_NOMBRE:
                score_marca = max(score_marca, score_respaldo)
            if score_marca < UMBRAL_MARCA_MINIMO:
                continue

            if variante_llm is None:
                score_variante = SCORE_VARIANTE_SIN_DATO
            else:
                score_variante = similitud(
                    variante_llm, normalizar(p.get("variante") or "original"))
            score_tam = _score_tamano(p, valor_llm, unidad_llm)
            score_total = (score_marca * PESO_MARCA
                           + score_variante * PESO_VARIANTE
                           + score_tam * PESO_TAMANO)
            scoreados.append((p, score_total))

        if not scoreados:
            return {"estado": "no_reconocido", "razon": "marca_no_esta_en_base",
                    "datos_llm": datos_llm}

        scoreados.sort(key=lambda x: x[1], reverse=True)
        mejor, score_mejor = scoreados[0]

        if score_mejor < UMBRAL_DESCARTE:
            return {
                "estado": "no_reconocido",
                "razon": "sin_coincidencia_suficiente",
                "datos_llm": datos_llm,
                "candidato_mas_cercano": mejor["sku"],
                "score_mas_cercano": round(score_mejor, 1),
            }

        margen = (score_mejor - scoreados[1][1]) if len(scoreados) > 1 else 999

        if score_mejor >= UMBRAL_AUTOACEPTAR and margen >= MARGEN_AMBIGUEDAD:
            return {"estado": "reconocido", "producto": mejor, "confianza": conf_llm}

        return {
            "estado": "confirmar",
            "producto": mejor,
            "candidatos": [s[0] for s in scoreados[:3]],
            "motivo": "similitud_baja" if score_mejor < UMBRAL_AUTOACEPTAR else "multiples_matches",
            "datos_llm": datos_llm,
        }

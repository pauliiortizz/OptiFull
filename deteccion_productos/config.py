"""
config.py
---------
Parámetros de calibración y configuración del pipeline, centralizados
en un solo lugar. Cuando ajustes umbrales con pruebas reales (cámara,
video real, etc.), tocás este archivo únicamente en vez de buscar
constantes repartidas en cada agente.
"""

# --- Rutas ---
DB_PATH = "data/stock.db"
CSV_PATH = "data/productos.csv"

# --- Captura ---
# fps a procesar. El MotionAgent filtra más aún, así que con 3-5
# alcanza para una estación de caja.
TARGET_FPS = 5

# --- VisionAgent (LLM) ---
MODEL = "claude-haiku-4-5-20251001"

# --- MotionAgent: detección de estabilidad y escena nueva ---

# Cuántos frames consecutivos tienen que ser "parecidos" para
# considerar la escena estable. A ~3 fps de procesamiento, 3 frames
# son 1 segundo. Bajar a 2 si la cajera es muy rápida; subir a 4-5
# si hay mucho movimiento espurio.
FRAMES_PARA_ESTABLE = 3

# Diferencia media máxima entre frames consecutivos para considerarlos
# "parecidos" (escena estable). Valores 0-255.
# ~5-10 tolera micro-vibraciones y cambios de luz sutiles.
# ~15+ tolera bastante movimiento (peligroso).
UMBRAL_ESTABILIDAD = 8

# Diferencia media mínima entre el frame actual y el ÚLTIMO analizado
# para considerar que estamos frente a una escena nueva (producto
# distinto, o cajera cambió de producto).
# ~25 evita disparar cuando el mismo producto rota levemente o se
# desplaza en la mano. Solo dispara con cambios grandes (producto
# nuevo o retiro de escena).
UMBRAL_ESCENA_NUEVA = 25

# --- MatchingAgent: confianza mínima del LLM para procesar ---
UMBRAL_CONFIANZA_LLM = 0.7

# --- MatchingAgent: comparación de texto (marca / variante) ---
# Tolerancia de edición ABSOLUTA (cantidad de letras insertadas /
# borradas / cambiadas), no porcentual. Un nombre corto como "Tofi"
# pierde un % enorme de similitud con un solo typo del LLM ("Tofti",
# "Toffi"); tolerar un número fijo de ediciones según el largo evita
# ese sesgo contra marcas/variantes cortas, sea cual sea la palabra.
TOLERANCIA_EDICION_CORTA = 1   # strings de hasta 5 caracteres
TOLERANCIA_EDICION_MEDIA = 2   # strings de 6 a 9 caracteres
TOLERANCIA_EDICION_LARGA = 3   # strings de 10+ caracteres

# --- MatchingAgent: comparación de tamaño ---
# El tamaño también es una lectura del LLM sobre el envase, y también
# se puede leer mal (ej: "40g" en vez de "46g"). En vez de un corte
# exacto (± tolerancia chica) que descarta TODO si no entra, se
# puntúa proporcional a la diferencia relativa. PENALIZACION_TAMANO
# controla qué tan rápido cae el score por cada % de diferencia: con
# 150, un desvío del 13% (46g leído como 40g) todavía puntúa ~80;
# un desvío del 100% (500ml leído como 1L) cae a 0.
PENALIZACION_TAMANO = 150

# --- MatchingAgent: piso mínimo de marca (gate previo a puntuar) ---
# El tamaño puede coincidir por PURA casualidad entre productos de
# marcas totalmente distintas (un snack de 40g y un alfajor de 46g no
# tienen nada que ver, pero pesan parecido). Si se puntuara todo junto
# sin este piso, esa coincidencia de tamaño podría "rescatar" un
# producto de otra marca y meterlo como candidato. Por eso la marca
# sigue siendo el índice primario: un producto ni siquiera entra a
# competir por variante/tamaño si su marca no supera este piso.
# Es DELIBERADAMENTE bajo y usa la misma función tolerante a typos
# (`similitud`) que el resto del matching: un typo real ("Tofti" por
# "Tofi") puntúa 80-95 y pasa sin problema; lo que este piso excluye
# son marcas genuinamente distintas ("Saladix" vs "Guaymallen"), no
# errores de lectura.
UMBRAL_MARCA_MINIMO = 40

# --- MatchingAgent: respaldo de marca vía nombre_producto ---
# Cuando la marca no matchea directo, se busca la marca también entre
# las palabras de 'nombre_producto' (por si el LLM invirtió los
# campos). Pero ese camino busca en MÁS lugares (cada palabra, contra
# cada marca de la base), así que tiene más chances de un choque
# casual: una variante como "Calabresa" puede parecerse a "Lays" sin
# tener nada que ver. Por eso este respaldo exige un umbral más alto
# que la comparación directa — un acierto real (la marca de verdad
# metida en 'nombre_producto', ej. "Toffi" por "Tofi") puntúa 80-95;
# una coincidencia de palabras al azar se queda casi siempre por
# debajo de esto.
UMBRAL_RESPALDO_NOMBRE = 70

# --- MatchingAgent: variante no reportada por el LLM ---
# Si el LLM no vio/determinó la variante (None), NO se asume
# "Original": eso penaliza productos de un solo sabor que no tienen
# ninguna variante llamada así (ej. una esencia de vainilla, que solo
# tiene "Vainilla"). Se usa un score neutro — ni premia ni castiga —
# en vez de comparar contra un valor asumido que puede estar mal.
SCORE_VARIANTE_SIN_DATO = 50

# --- MatchingAgent: score combinado marca + variante + tamaño ---
# Ningún campo descarta un candidato por sí solo: se puntúan los tres
# y se decide según el mejor puntaje combinado. Un typo de marca, una
# variante mal leída o un tamaño con error de lectura pueden compensarse
# entre sí si el resto del producto encaja.
PESO_MARCA = 0.40
PESO_VARIANTE = 0.25
PESO_TAMANO = 0.35
UMBRAL_AUTOACEPTAR = 85    # score combinado para aceptar sin preguntar
UMBRAL_DESCARTE = 50       # por debajo de esto, no se considera ni como candidato
MARGEN_AMBIGUEDAD = 12     # diferencia mínima 1° vs 2° para no pedir confirmación

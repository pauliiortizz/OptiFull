"""Configuracion central del pipeline de deteccion + Re-ID + heatmap."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[.env] python-dotenv no instalado; se usan solo variables de entorno del sistema.")

try:
    from tqdm import tqdm  # noqa: F401
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import psycopg2  # noqa: F401
    import psycopg2.extras  # noqa: F401
    HAS_DB = True
except ImportError:
    HAS_DB = False
    print("[DB] psycopg2-binary no instalado. No se podra persistir en Supabase.")

try:
    from google import genai  # noqa: F401
    from google.genai import types  # noqa: F401
    from google.genai.errors import ClientError  # noqa: F401
    from PIL import Image  # noqa: F401
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    print("[Gemini] Dependencias no instaladas (google-genai/pillow). ReID en la nube desactivado.")

try:
    import groq  # noqa: F401
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False
    print("[Groq] Dependencias no instaladas (paquete 'groq'). ReID en la nube desactivado.")

try:
    import anthropic  # noqa: F401
    HAS_CLAUDE = True
except ImportError:
    HAS_CLAUDE = False
    print("[Claude] Dependencias no instaladas (paquete 'anthropic'). ReID en la nube desactivado.")

# ── Configuracion de video / tracking ──────────────────────────────────────────
VIDEO_PATH = r"D:\FACU 2026\Videos\D01_20260521170024.mp4"
FRAME_SKIP        = 5
CONF              = 0.7
MAX_DIST_RATIO    = 0.15
QUICK_EXPIRY_SEC  = 15.0
LONG_EXPIRY_SEC   = 1800.0
APPEARANCE_THRESH = 0.72
MAX_APP_SAMPLES   = 20
MIN_FRAMES_CONFIRMACION = 3  # frames PROCESADOS consecutivos que un id debe sobrevivir
                             # antes de crear su fila en 'personas' -- filtra falsos
                             # positivos de un solo frame (ver PersonTracker.__init__)

GAUSSIAN_RADIUS   = 60
HEATMAP_GRID      = 64      # resolucion de la matriz comprimida que se guarda en BD
HEATMAP_UMBRAL    = 0.05    # % del maximo para considerar un pixel "activo"
SHOW_PREVIEW      = False
PREVIEW_CADA_N    = 5       # actualizar ventana cada N frames procesados

DATABASE_URL         = os.environ.get("DATABASE_URL")
CAMARA_ID_OVERRIDE   = None
GUARDAR_TRAYECTORIAS = True

# Modo de prueba: se conecta a la BD SOLO para leer 'zonas' (necesarias para
# clasificar Escenario A/B/C, ver pipeline/eventos.py) y corta la conexion
# ANTES de crear la sesion -- todo Persistencia.* es no-op sin conexion (ver
# docstring del modulo), asi que el resto del analisis corre entero (heatmap,
# tracking, clasificacion por consola) sin escribir NINGUNA fila en la BD.
# Pensado para correr main.py contra un video de prueba sin tocar datos
# reales. Dejar en False para el uso normal (persiste todo como siempre).
SOLO_LEER_ZONAS = False
TRAYECTORIAS_FLUSH_CADA_N_FRAMES = 1000  # frames PROCESADOS (no crudos) entre cada
                                          # guardado incremental de trayectorias en la BD
TRAYECTORIA_INTERVALO_SEG = 10.0  # cada cuanto tiempo de video se guarda un punto de
                                   # posicion por persona (antes: en cada frame procesado)

# ── Supabase Storage (imagenes de heatmap) ─────────────────────────────────────
# Solo se sube el heatmap "puro" (PNG con canal alfa = intensidad, sin overlay
# con el frame de fondo) -- pesa una fraccion de lo que pesaria un overlay a
# color completo, asi entran muchas mas imagenes en el plan gratuito.
SUPABASE_URL          = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY  = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET       = os.environ.get("SUPABASE_BUCKET", "heatmaps")
HAS_SUPABASE_STORAGE  = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
if not HAS_SUPABASE_STORAGE:
    print("[Storage] SUPABASE_URL/SUPABASE_SERVICE_KEY no configurados en .env; "
          "las imagenes de heatmap se guardaran localmente.")

CAMARA_NOMBRES = {
    1: ("Camara Caja Derecha",   "Caja"),
    2: ("Camara Esquina Full",   "Esquina"),
    3: ("Camara Caja Frente",    "Caja"),
    4: ("Camara Caja Izquierda", "Caja"),
}

# Grupos de camaras que apuntan al MISMO espacio fisico desde angulos
# distintos (ej. 1, 3 y 4 son todas camaras de la zona de cajas). Se usa para
# la Re-ID entre camaras: una persona nueva detectada en una camara de un
# grupo se compara primero contra los candidatos ya descritos por CUALQUIER
# OTRA camara del MISMO grupo (nunca contra una camara de otro grupo, aunque
# sea el mismo dia) -- evita que se cuenten como "personas nuevas" clientes
# que ya fueron vistos por otra camara que mira el mismo lugar. Una camara no
# listada aca queda en su propio grupo (solo se compara consigo misma).
GRUPOS_CAMARA = {
    1: [1, 3, 4],
    3: [1, 3, 4],
    4: [1, 3, 4],
}

# OJO: GRUPOS_CAMARA solo controla candidatos de Re-ID en vivo (ayuda a que
# el tracking reconozca a alguien ya visto por otra camara del grupo). NO
# alcanza para que las 3 camaras converjan al mismo conteo total -- Re-ID por
# descripcion de texto (color de ropa, etc.) nunca fusiona el 100% de los
# casos reales (ver historial: 424 personas combinando 1/3/4 vs ~185 de
# camara 4 sola, para el mismo dia y el mismo publico). Por eso los reportes
# del frontend (frontend/api.py, CAMARAS_EXCLUIDAS_DE_CONTEO) cuentan
# personas de ESTE grupo usando solo camara 4 como fuente de verdad, y
# excluyen 1 y 3 del conteo (aunque se sigan analizando igual para heatmap/
# zonas). Si el grupo cambia aca, hay que actualizar esa constante tambien.

# Ventana de tiempo (+/- horas) alrededor del momento actual del video dentro
# de la cual se buscan candidatos de Re-ID entre camaras del mismo grupo. Sin
# esto se compararia (por error) a alguien visto a las 9am con alguien visto
# a las 5pm solo por ser el mismo dia calendario.
REID_VENTANA_HORAS = 1.0

# Umbral (segundos) para considerar que dos detecciones en camaras DISTINTAS
# del mismo grupo fisico son "el mismo instante" -- las camaras 1/3/4, por
# ejemplo, miran el mismo mostrador desde angulos distintos, asi que aparecer
# casi al mismo tiempo en dos de ellas es evidencia fuerte de ser la misma
# persona, aun si un angulo le tapa a Gemini/Groq alguna prenda que el otro
# si ve. Se usa tanto en GeminiReID/GroqReID.clasificar() (matching en vivo)
# como en Persistencia.auditar_sesion() (auditoria post-analisis).
UMBRAL_MISMO_MOMENTO_SEG = 90.0

# Ventana de tiempo (segundos, hueco de ambos lados del corte sumado) para
# Persistencia.fusionar_continuidad_sesiones(): distinto de
# UMBRAL_MISMO_MOMENTO_SEG (ese es para personas vistas por CAMARAS
# DISTINTAS "al mismo instante"; este es para la MISMA camara partida por el
# corte automatico de archivo del DVR, donde el hueco esperado es de
# segundos, no minutos). CONTINUIDAD_ALTA_CONFIANZA_SEG es el hueco por
# debajo del cual la coincidencia se marca 'Alta' en vez de 'Media' --
# practicamente el mismo instante, solo pudo pasar por el corte del archivo.
CONTINUIDAD_VENTANA_SEG          = 60.0
CONTINUIDAD_ALTA_CONFIANZA_SEG   = 15.0

# Minimo de coincidencias de _comparar_descriptores para Persistencia.
# _fusionar_por_proximidad() (usada por auditar_sesion() y
# fusionar_cross_camara_dia()) -- el color de ropa superior obligatorio por
# si solo NO alcanza como filtro (es un campo de muy pocas categorias
# posibles, ej. 'negro' es carisimo -- ver docstring de _fusionar_por_proximidad
# sobre el bug de sobre-fusion que esto causo en produccion). Mismo criterio
# que GEMINI_COINCIDENCIAS_MINIMAS/GROQ_COINCIDENCIAS_MINIMAS/
# CLAUDE_COINCIDENCIAS_MINIMAS.
FUSION_COINCIDENCIAS_MINIMAS = 3

# ── Configuracion Re-ID hibrido con Gemini, Groq o Claude ───────────────────────
# REID_PROVIDER elige que proveedor de vision en la nube usa PersonTracker para
# el fallback de Re-ID ("gemini", "groq" o "claude") -- son intercambiables, los
# tres clientes (GeminiReID / GroqReID / ClaudeReID) exponen la misma interfaz.
# Groq tiene cuotas gratuitas mas generosas hoy (30 req/min, 1000 req/dia en
# llama-4-scout) que el limite diario que le esta pegando a Gemini (20 req/dia
# por proyecto en el modelo actual), asi que puede convenir cambiarlo si Gemini
# se queda sin cupo. Claude (Opus) no tiene cuota gratuita -- es de pago por
# token, pero sin el limite diario que Gemini/Groq imponen en sus free tiers.
REID_PROVIDER    = "claude"  # "gemini", "groq" o "claude"
USAR_GEMINI_REID = True  # apagar para correr solo tracking+heatmap sin gastar cupo de API
USAR_GROQ_REID   = True  # idem, para cuando REID_PROVIDER = "groq"
USAR_CLAUDE_REID = True  # idem, para cuando REID_PROVIDER = "claude"

def _cargar_api_keys(prefijo: str) -> list:
    """Junta todas las <PREFIJO>_API_KEY_N definidas en .env (1, 2, 3, ...),
    sin limite fijo -- alcanza con agregar _3, _4, etc. al .env. Tambien
    acepta una unica <PREFIJO>_API_KEY (sin sufijo numerico) como primera
    clave -- Gemini/Groq rotan muchas keys de free tier, pero un proveedor de
    pago (ej. Claude) tipicamente solo necesita una."""
    clave_unica = os.environ.get(f"{prefijo}_API_KEY")
    claves = [clave_unica] if clave_unica else []
    n = 1
    while True:
        clave = os.environ.get(f"{prefijo}_API_KEY_{n}")
        if not clave:
            break
        claves.append(clave)
        n += 1
    return claves


GEMINI_API_KEYS = _cargar_api_keys("GEMINI") if HAS_GEMINI else []

GEMINI_MODEL              = "gemini-flash-latest"  # alias de Google al flash estable vigente
GEMINI_MIN_INTERVALO_SEG  = 4.0   # piso de seguridad: ~15 req/min del free tier -> 1 cada 4s
GEMINI_RAFAGA_UMBRAL      = 3     # a partir de N eventos en 10s se considera "rafaga" (ej. grupo entrando)
GEMINI_PAUSA_RAFAGA_SEG   = 8.0   # pausa extra que se suma al intervalo minimo durante una rafaga
GEMINI_VENTANA_RAFAGA_SEG = 10.0  # ventana de tiempo usada para contar eventos recientes
DESCRIPCION_STREAK_FRAMES = 25    # frames procesados consecutivos para "confirmar" un ID y describirlo 1 sola vez
GEMINI_COINCIDENCIAS_MINIMAS = 3  # de 5 campos del descriptor; minimo que deben coincidir para aceptar una coincidencia
                                  # (ademas, color_ropa_superior es obligatorio: ver gemini_reid.py)

GROQ_API_KEYS = _cargar_api_keys("GROQ") if HAS_GROQ else []

GROQ_MODEL                = "qwen/qwen3.6-27b"  # modelo de vision vigente en Groq (llama-4-scout dado de baja el 17/07/2026)
GROQ_MIN_INTERVALO_SEG    = 2.5   # piso de seguridad: 30 req/min del free tier -> 1 cada 2s, con margen
GROQ_RAFAGA_UMBRAL        = 3
GROQ_PAUSA_RAFAGA_SEG     = 6.0
GROQ_VENTANA_RAFAGA_SEG   = 10.0
GROQ_COINCIDENCIAS_MINIMAS = 3    # mismo criterio que Gemini (ver groq_reid.py: color superior obligatorio)

CLAUDE_API_KEYS = _cargar_api_keys("CLAUDE") if HAS_CLAUDE else []

CLAUDE_MODEL                = "claude-haiku-4-5"  # modelo mas barato de la familia actual ($1/$5 por MTok);
                                                    # alcanza de sobra para esta extraccion corta y estructurada
CLAUDE_MIN_INTERVALO_SEG    = 2.5   # piso de seguridad similar a Groq; sin free tier que agotar,
                                     # pero igual evita saturar de golpe en una rafaga
CLAUDE_RAFAGA_UMBRAL        = 3
CLAUDE_PAUSA_RAFAGA_SEG     = 6.0
CLAUDE_VENTANA_RAFAGA_SEG   = 10.0
CLAUDE_COINCIDENCIAS_MINIMAS = 3  # mismo criterio que Gemini/Groq (ver claude_reid.py: color superior obligatorio)

# ── Deteccion de interaccion con producto (tomar_producto) ─────────────────────
# Clases COCO (indices de yolov8n.pt, entrenado sobre COCO) que se toman como
# "producto" para la heuristica de tomar_producto -- YOLOv8n stock no conoce
# productos especificos del local, asi que se aproxima con las clases COCO mas
# parecidas a mercaderia de kiosco/minimarket (bebidas, comida, etc.). Ajustar
# esta lista si el catalogo real del local no se parece a esto (ver
# deteccion/utils.py:detectar_productos y pipeline/eventos.py).
PRODUCTO_CLASES_COCO = [39, 40, 41, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55]
# 39 bottle, 40 wine glass, 41 cup, 45 bowl, 46 banana, 47 apple, 48 sandwich,
# 49 orange, 50 broccoli, 51 carrot, 52 hot dog, 53 pizza, 54 donut, 55 cake

PRODUCTO_CONF = 0.4  # mas bajo que CONF (personas): los objetos son chicos y
                     # parciales, exigir 0.7 dejaria pasar casi todo por alto

# Cuantos px se agranda el box de la persona (de cada lado) antes de chequear
# si el CENTRO de un box de producto cae adentro -- el objeto en la mano/brazo
# normalmente queda apenas afuera del box ajustado de la persona.
INTERACCION_MARGEN_PX = 20

# Frames PROCESADOS consecutivos con un producto "cerca" de la persona (ver
# utils.producto_cerca_de_persona) necesarios para confirmar tomar_producto =
# True -- filtra flickers de un solo frame (objeto ya en la gondola detras de
# la persona que por un instante cae dentro del margen). Una vez confirmado,
# tomar_producto queda en True para el resto de la visita (no se re-evalua
# frame a frame: la persona puede guardarlo en el bolsillo/bolsa y dejar de
# "tocarlo" sin que eso signifique que lo devolvio).
INTERACCION_FRAMES_MINIMOS = 3

# Zona Caja en este sistema es el lado del EMPLEADO del mostrador (ver
# Persistencia.limpiar_trayectorias_fuera_de_zona) -- un cliente pagando se
# ACERCA al mostrador desde el lado de enfrente, pero casi nunca pisa el
# poligono en si. CAJA_APROXIMACION_RATIO define, como fraccion del ANCHO del
# frame (mismo criterio que MAX_DIST_RATIO), cuan cerca del borde de una zona
# tipo='caja' alcanza para contar como "paso por caja" en la clasificacion
# Escenario A/B/C (ver utils.cerca_de_zona_tipo / pipeline/eventos.py). Es mas
# generoso que el max_dist_borde de get_zona_id (ese es para el borde del
# FRAME, no para "se acerco al mostrador a pagar").
CAJA_APROXIMACION_RATIO = 0.08

# Segundos CONSECUTIVOS que el cliente tiene que quedarse cerca de Zona Caja
# para confirmar paso_por_caja=True -- discrimina "se quedo a pagar/esperar
# el pedido" de "paso caminando cerca del mostrador de largo". Se probo antes
# exigir que hubiera OTRA persona (posible empleado) presente al mismo tiempo,
# pero en un local con empleados fijos en Zona Caja esa condicion se cumple
# casi siempre este o no en curso una transaccion real -- no discriminaba
# nada. La permanencia SI lo hace: alguien de paso no se queda parado ahi
# varios segundos. Se convierte a frames PROCESADOS (fps/FRAME_SKIP) en
# main.py, mismo criterio que INTERACCION_FRAMES_MINIMOS pero en segundos en
# vez de frames (esta zona importa menos la cantidad exacta de frames y mas
# cuanto tiempo real paso).
CAJA_PERMANENCIA_MINIMA_SEG = 3.0

# ── Camara en vivo (webcam) ─────────────────────────────────────────────────
# Ver deteccion/pipeline/video_source.py:WebcamVideoSource y el flag --webcam
# de main.py. La camara en vivo usa el mismo pipeline de deteccion/tracking/
# heatmap que un video, pero NUNCA persiste en la BD ni sube nada a Supabase
# Storage (main.py corta esa seccion entera cuando modo_camara=True) -- es
# solo para validar el pipeline en vivo antes de decidir si se persiste.
WEBCAM_DEVICE_INDEX    = 0     # indice de camara por default para --webcam sin argumento
WEBCAM_RESOLUTION      = None  # (ancho, alto) o None = la resolucion default de la camara
WEBCAM_TARGET_FPS      = None  # fps pedido a la camara, o None = el que de por default
WEBCAM_USAR_REID_NUBE  = False  # False = tracking local + heatmap sin gastar cupo de Gemini/Groq/Claude
WEBCAM_CAMARA_ID_ZONAS = None  # id de camara (ver CAMARA_NOMBRES) para cargar SUS zonas en modo
                                # solo lectura -- nunca escribe (mismo patron que SOLO_LEER_ZONAS).
                                # None = corre sin zonas (heatmap/tracking igual funcionan).

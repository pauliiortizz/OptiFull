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

# ── Configuracion de video / tracking ──────────────────────────────────────────
VIDEO_PATH        = "D:\\D03_20260520172620.mp4"
FRAME_SKIP        = 5
CONF              = 0.3
MAX_DIST_RATIO    = 0.15
QUICK_EXPIRY_SEC  = 15.0
LONG_EXPIRY_SEC   = 1800.0
APPEARANCE_THRESH = 0.72
MAX_APP_SAMPLES   = 20

GAUSSIAN_RADIUS   = 60
HEATMAP_GRID      = 64      # resolucion de la matriz comprimida que se guarda en BD
HEATMAP_UMBRAL    = 0.05    # % del maximo para considerar un pixel "activo"
SHOW_PREVIEW      = False
PREVIEW_CADA_N    = 5       # actualizar ventana cada N frames procesados

DATABASE_URL         = os.environ.get("DATABASE_URL")
CAMARA_ID_OVERRIDE   = None
GUARDAR_TRAYECTORIAS = True
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

# ── Configuracion Re-ID hibrido con Gemini o Groq ───────────────────────────────
# REID_PROVIDER elige que proveedor de vision en la nube usa PersonTracker para
# el fallback de Re-ID ("gemini" o "groq") -- son intercambiables, ambos clientes
# (GeminiReID / GroqReID) exponen la misma interfaz. Groq tiene cuotas gratuitas
# mas generosas hoy (30 req/min, 1000 req/dia en llama-4-scout) que el limite
# diario que le esta pegando a Gemini (20 req/dia por proyecto en el modelo
# actual), asi que puede convenir cambiarlo si Gemini se queda sin cupo.
REID_PROVIDER    = "gemini"  # "gemini" o "groq"
USAR_GEMINI_REID = True  # apagar para correr solo tracking+heatmap sin gastar cupo de API
USAR_GROQ_REID   = True  # idem, para cuando REID_PROVIDER = "groq"

def _cargar_api_keys(prefijo: str) -> list:
    """Junta todas las <PREFIJO>_API_KEY_N definidas en .env (1, 2, 3, ...),
    sin limite fijo -- alcanza con agregar _3, _4, etc. al .env."""
    claves = []
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
GEMINI_COINCIDENCIAS_MINIMAS = 4  # de 5 campos del descriptor; minimo que deben coincidir para aceptar una coincidencia
                                  # (ademas, color_ropa_superior y color_ropa_inferior son obligatorios: ver gemini_reid.py)

GROQ_API_KEYS = _cargar_api_keys("GROQ") if HAS_GROQ else []

GROQ_MODEL                = "qwen/qwen3.6-27b"  # modelo de vision vigente en Groq (llama-4-scout dado de baja el 17/07/2026)
GROQ_MIN_INTERVALO_SEG    = 2.5   # piso de seguridad: 30 req/min del free tier -> 1 cada 2s, con margen
GROQ_RAFAGA_UMBRAL        = 3
GROQ_PAUSA_RAFAGA_SEG     = 6.0
GROQ_VENTANA_RAFAGA_SEG   = 10.0
GROQ_COINCIDENCIAS_MINIMAS = 4    # mismo criterio que Gemini (ver groq_reid.py: colores obligatorios)

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

# ── Configuracion de video / tracking ──────────────────────────────────────────
VIDEO_PATH        = "D:\\D04_20260520061524.mp4"
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

CAMARA_NOMBRES = {
    1: ("Camara 01", "Entrada principal"),
    2: ("Camara 02", "Caja"),
    3: ("Camara 03", "Gondolas"),
    4: ("Camara 04", "Deposito / exterior"),
}

# ── Configuracion Re-ID hibrido con Gemini ─────────────────────────────────────
USAR_GEMINI_REID = True  # apagar para correr solo tracking+heatmap sin gastar cupo de API

def _cargar_gemini_api_keys() -> list:
    """Junta todas las GEMINI_API_KEY_N definidas en .env (1, 2, 3, ...), sin
    limite fijo -- alcanza con agregar GEMINI_API_KEY_3, _4, etc. al .env."""
    claves = []
    n = 1
    while True:
        clave = os.environ.get(f"GEMINI_API_KEY_{n}")
        if not clave:
            break
        claves.append(clave)
        n += 1
    return claves


GEMINI_API_KEYS = _cargar_gemini_api_keys() if HAS_GEMINI else []

GEMINI_MODEL              = "gemini-flash-latest"  # alias de Google al flash estable vigente
GEMINI_MIN_INTERVALO_SEG  = 4.0   # piso de seguridad: ~15 req/min del free tier -> 1 cada 4s
GEMINI_RAFAGA_UMBRAL      = 3     # a partir de N eventos en 10s se considera "rafaga" (ej. grupo entrando)
GEMINI_PAUSA_RAFAGA_SEG   = 8.0   # pausa extra que se suma al intervalo minimo durante una rafaga
GEMINI_VENTANA_RAFAGA_SEG = 10.0  # ventana de tiempo usada para contar eventos recientes
DESCRIPCION_STREAK_FRAMES = 25    # frames procesados consecutivos para "confirmar" un ID y describirlo 1 sola vez
GEMINI_COINCIDENCIAS_MINIMAS = 3  # de 5 campos del descriptor; minimo que deben coincidir para aceptar una coincidencia

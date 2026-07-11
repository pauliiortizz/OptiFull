import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import numpy as np
import cv2
import csv
import re
import json
from datetime import timedelta, datetime
from pathlib import Path
from typing import Optional

from ultralytics import YOLO

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[.env] python-dotenv no instalado; se usan solo variables de entorno del sistema.")

try:
    import psycopg2
    import psycopg2.extras
    HAS_DB = True
except ImportError:
    HAS_DB = False
    print("[DB] psycopg2-binary no instalado. Solo se guardara en CSV.")

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError
    from PIL import Image
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    print("[Gemini] Dependencias no instaladas (google-genai/pillow). ReID en la nube desactivado.")

# ── Configuracion ──────────────────────────────────────────────────────────────
VIDEO_PATH        = "D:\\D04_20260520061524.mp4"
FRAME_SKIP        = 5
CONF              = 0.3
MAX_DIST_RATIO    = 0.15
QUICK_EXPIRY_SEC  = 15.0
LONG_EXPIRY_SEC   = 1800.0
APPEARANCE_THRESH = 0.72
MAX_APP_SAMPLES   = 20
OUTPUT_CSV        = "permanencia.csv"

GAUSSIAN_RADIUS   = 60
HEATMAP_GRID      = 64      # resolucion de la matriz comprimida que se guarda en BD
HEATMAP_UMBRAL    = 0.05    # % del maximo para considerar un pixel "activo"
SHOW_PREVIEW      = False
PREVIEW_CADA_N    = 5       # actualizar ventana cada N frames procesados

DATABASE_URL = os.environ.get("DATABASE_URL")
CAMARA_ID_OVERRIDE   = None
GUARDAR_TRAYECTORIAS = True

# ── Configuracion Re-ID hibrido con Gemini ─────────────────────────────────────
USAR_GEMINI_REID = True  # apagar para correr solo tracking+heatmap sin gastar cupo de API

GEMINI_API_KEYS = [
    clave
    for clave in (os.environ.get("GEMINI_API_KEY_1"), os.environ.get("GEMINI_API_KEY_2"))
    if clave
] if HAS_GEMINI else []

if USAR_GEMINI_REID and HAS_GEMINI and not GEMINI_API_KEYS:
    print("[Gemini] No hay API keys configuradas (revisa .env). ReID en la nube desactivado.")
    USAR_GEMINI_REID = False
elif USAR_GEMINI_REID and not HAS_GEMINI:
    USAR_GEMINI_REID = False

GEMINI_MODEL              = "gemini-2.5-flash" # probar con el 3
GEMINI_MIN_INTERVALO_SEG  = 4.0   # piso de seguridad: ~15 req/min del free tier -> 1 cada 4s
GEMINI_RAFAGA_UMBRAL      = 3     # a partir de N eventos en 10s se considera "rafaga" (ej. grupo entrando)
GEMINI_PAUSA_RAFAGA_SEG   = 8.0   # pausa extra que se suma al intervalo minimo durante una rafaga
GEMINI_VENTANA_RAFAGA_SEG = 10.0  # ventana de tiempo usada para contar eventos recientes
DESCRIPCION_STREAK_FRAMES = 25    # frames procesados consecutivos para "confirmar" un ID y describirlo 1 sola vez

# ── Helpers de video / filename ────────────────────────────────────────────────
def parse_camara_id(video_path: str) -> int:
    name = Path(video_path).stem.upper()
    m = re.match(r"D(\d{2})", name)
    if m:
        return int(m.group(1))
    raise ValueError(
        f"No se pudo determinar la camara desde '{Path(video_path).name}'. "
        f"Formato esperado: D01_..., D04_... "
        f"O seteá CAMARA_ID_OVERRIDE manualmente."
    )

def parse_inicio(video_path: str) -> datetime:
    name = Path(video_path).stem
    m = re.search(r"(\d{8})_?(\d{6})", name)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return datetime.fromtimestamp(Path(video_path).stat().st_mtime)

def frame_to_dt(frame_num: int, fps: float, inicio: datetime) -> datetime:
    return inicio + timedelta(seconds=frame_num / fps)

def to_timestamp(frame_num, fps):
    return str(timedelta(seconds=int(frame_num / fps)))

# ── Helpers de zona ────────────────────────────────────────────────────────────
def point_in_polygon(cx, cy, polygon) -> bool:
    n, inside, j = len(polygon), False, len(polygon) - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > cy) != (yj > cy)) and (cx < (xj - xi) * (cy - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside

def get_zona_id(cx, cy, zonas: list):
    for z in zonas:
        if point_in_polygon(cx, cy, z["poligono"]):
            return z["id"]
    return None

# ── Helpers de apariencia ──────────────────────────────────────────────────────
def safe_crop(frame: np.ndarray, box) -> np.ndarray:
    """Recorta el frame segun el bbox, clampeando a los bordes de la imagen
    para que nunca falle (slice vacio o negativo) en los margenes de la pantalla."""
    h, w = frame.shape[:2]
    x1 = max(0, min(int(box[0]), w))
    y1 = max(0, min(int(box[1]), h))
    x2 = max(0, min(int(box[2]), w))
    y2 = max(0, min(int(box[3]), h))
    return frame[y1:y2, x1:x2]

def compute_appearance(frame, box):
    crop = safe_crop(frame, box)
    if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 10:
        return None
    torso = crop[: crop.shape[0] // 2, :]
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0], None, [18], [0, 180]).flatten()
    s = cv2.calcHist([hsv], [1], None, [8],  [0, 256]).flatten()
    hist = np.concatenate([h, s]).astype(np.float32)
    hist /= hist.sum() + 1e-6
    return hist

def appearance_sim(h1, h2):
    dist = cv2.compareHist(h1.reshape(-1, 1), h2.reshape(-1, 1), cv2.HISTCMP_BHATTACHARYYA)
    return 1.0 - dist

def centroid_dist(box1, box2):
    cx1, cy1 = (box1[0] + box1[2]) / 2, (box1[1] + box1[3]) / 2
    cx2, cy2 = (box2[0] + box2[2]) / 2, (box2[1] + box2[3]) / 2
    return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5

# ── Registro de Clientes Activos del Dia (historial en memoria) ───────────────
# sid -> {"primera_deteccion_frame", "ultima_deteccion_frame", "estado", "descripcion"}
registro_clientes: dict[int, dict] = {}

def registrar_o_actualizar_cliente(
    sid: int, frame_num: int, estado: str, descripcion: Optional[str] = None
) -> None:
    """Crea o actualiza la entrada de un cliente en el registro en memoria del dia."""
    entrada = registro_clientes.setdefault(sid, {
        "primera_deteccion_frame": frame_num,
        "descripcion": None,
    })
    entrada["ultima_deteccion_frame"] = frame_num
    entrada["estado"] = estado
    if descripcion is not None:
        entrada["descripcion"] = descripcion

# ── Rate limiter local para la API de Gemini (gestion de rafagas) ─────────────
_ultima_llamada_gemini: float = 0.0
_eventos_recientes_ts: list[float] = []

def _registrar_evento_y_medir_rafaga() -> int:
    """Registra la ocurrencia de un evento 'ID nuevo sospechoso' y devuelve cuantos
    eventos hubo dentro de la ventana de rafaga (ej. un grupo entrando junto)."""
    ahora = time.monotonic()
    _eventos_recientes_ts.append(ahora)
    corte = ahora - GEMINI_VENTANA_RAFAGA_SEG
    while _eventos_recientes_ts and _eventos_recientes_ts[0] < corte:
        _eventos_recientes_ts.pop(0)
    return len(_eventos_recientes_ts)

def esperar_turno_api() -> None:
    """Aplica un intervalo minimo entre llamadas a Gemini y, si se detecta una
    rafaga de eventos (varios IDs nuevos casi juntos), agrega una pausa extra
    para no exceder el rate limit del free tier sin colgar el procesamiento."""
    global _ultima_llamada_gemini
    eventos_en_rafaga = _registrar_evento_y_medir_rafaga()

    intervalo_min = GEMINI_MIN_INTERVALO_SEG
    if eventos_en_rafaga >= GEMINI_RAFAGA_UMBRAL:
        intervalo_min += GEMINI_PAUSA_RAFAGA_SEG
        print(f"[Gemini] Rafaga detectada ({eventos_en_rafaga} eventos en "
              f"{GEMINI_VENTANA_RAFAGA_SEG:.0f}s) -> pausa extra de {GEMINI_PAUSA_RAFAGA_SEG:.0f}s")

    transcurrido = time.monotonic() - _ultima_llamada_gemini
    if transcurrido < intervalo_min:
        time.sleep(intervalo_min - transcurrido)
    _ultima_llamada_gemini = time.monotonic()

def _generar_contenido_gemini(imagen: "Image.Image", prompt: str, json_response: bool = False) -> Optional[str]:
    """Prueba cada API key de Gemini en orden; si una se queda sin cupo (429),
    pasa a la siguiente. Devuelve el texto crudo de la respuesta, o None si
    fallan todas las keys o hay un error de red/cliente."""
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json" if json_response else None,
    )
    ultimo_error: Optional[Exception] = None
    for indice, api_key in enumerate(GEMINI_API_KEYS, start=1):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=[imagen, prompt], config=config,
            )
            return response.text
        except ClientError as error:
            if getattr(error, "code", None) == 429:
                print(f"[Gemini] API key {indice} sin cupo, probando con la siguiente...")
                ultimo_error = error
                continue
            print(f"[Gemini] Error de cliente en la llamada: {error}")
            return None
        except Exception as error:
            print(f"[Gemini] Error inesperado en la llamada: {error}")
            return None

    print(f"[Gemini] Todas las API keys sin cupo, se omite la llamada. Ultimo error: {ultimo_error}")
    return None

def _crop_a_imagen(crop_bgr: np.ndarray) -> Optional["Image.Image"]:
    try:
        return Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
    except Exception as error:
        print(f"[Gemini] No se pudo preparar el crop: {error}")
        return None

def generar_descripcion_gemini(crop_bgr: np.ndarray) -> Optional[str]:
    """Genera UNA UNICA VEZ por cliente una descripcion visual breve y
    estandarizada (vestimenta, colores, complexion), para guardarla en
    registro_clientes y poder comparar contra ella mas adelante sin tener
    que volver a describir a la misma persona."""
    if not USAR_GEMINI_REID:
        return None

    imagen = _crop_a_imagen(crop_bgr)
    if imagen is None:
        return None

    esperar_turno_api()
    prompt = (
        "Describe la vestimenta y caracteristicas fisicas de esta persona de forma "
        "breve y estandarizada (colores de ropa, tipo de prenda, complexion, cabello). "
        "Responde en una sola oracion corta, sin rodeos ni suposiciones sobre identidad."
    )
    texto = _generar_contenido_gemini(imagen, prompt, json_response=False)
    return texto.strip() if texto else None

def clasificar_con_gemini(crop_bgr: np.ndarray, candidatos: list[dict]) -> Optional[int]:
    """Le pregunta a Gemini si la persona del crop coincide con alguno de los
    clientes recientemente perdidos (candidatos). Devuelve el sid del candidato
    si hay coincidencia, o None si Gemini considera que es una persona nueva
    (o si la llamada de red falla / no hay cupo en ninguna key)."""
    if not USAR_GEMINI_REID or not candidatos:
        return None

    imagen = _crop_a_imagen(crop_bgr)
    if imagen is None:
        return None

    esperar_turno_api()
    lista_candidatos = [
        {"id": c["sid"], "descripcion": c.get("descripcion") or "sin descripcion registrada"}
        for c in candidatos
    ]
    prompt = (
        "La imagen muestra una persona detectada por una camara de seguridad de un local. "
        "Esta es una lista de clientes que estuvieron antes en el local y que el sistema de "
        "tracking perdio de vista (pudieron salir de cuadro o pasar a otra camara):\n"
        f"{json.dumps(lista_candidatos, ensure_ascii=False)}\n"
        "Compara la ropa, los colores y la complexion de la persona en la imagen contra estas "
        "descripciones. Si es muy probablemente la misma persona que una de la lista, responde "
        "unicamente en formato JSON: {\"id_coincidente\": <id>}. "
        "Si no coincide con ninguna o no estas seguro, responde {\"id_coincidente\": null}."
    )

    texto = _generar_contenido_gemini(imagen, prompt, json_response=True)
    if texto is None:
        return None
    try:
        return json.loads(texto).get("id_coincidente")
    except (json.JSONDecodeError, AttributeError) as error:
        print(f"[Gemini] Respuesta no parseable al clasificar identidad: {error}")
        return None

# ── Helpers de heatmap ─────────────────────────────────────────────────────────
def make_gaussian(radius: int) -> np.ndarray:
    size = radius * 2 + 1
    x = np.arange(size) - radius
    g = np.exp(-(x ** 2) / (2 * (radius / 3) ** 2))
    kernel = np.outer(g, g)
    return (kernel / kernel.max()).astype(np.float32)

def stamp_heat(accumulator: np.ndarray, cx: int, cy: int, kernel: np.ndarray, kr: int) -> None:
    h, w = accumulator.shape
    ky1, ky2 = max(0, cy - kr), min(h, cy + kr + 1)
    kx1, kx2 = max(0, cx - kr), min(w, cx + kr + 1)
    gy1 = ky1 - (cy - kr)
    gy2 = gy1 + (ky2 - ky1)
    gx1 = kx1 - (cx - kr)
    gx2 = gx1 + (kx2 - kx1)
    accumulator[ky1:ky2, kx1:kx2] += kernel[gy1:gy2, gx1:gx2]

def render_heatmap(accumulator: np.ndarray, background=None, alpha_bg: float = 0.5) -> np.ndarray:
    hm = accumulator.copy()
    if hm.max() > 0:
        hm /= hm.max()
    hm_color = cv2.applyColorMap((hm * 255).astype(np.uint8), cv2.COLORMAP_JET)
    if background is not None:
        return cv2.addWeighted(background, alpha_bg, hm_color, 1 - alpha_bg, 0)
    return hm_color

def resize_for_display(frame: np.ndarray, max_w: int = 1280, max_h: int = 720) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        return cv2.resize(frame, (int(w * scale), int(h * scale)))
    return frame

# ── DB helpers ─────────────────────────────────────────────────────────────────
def db_connect():
    if not HAS_DB or not DATABASE_URL:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("[DB] Conexion exitosa.")
        return conn
    except Exception as e:
        print(f"[DB] No se pudo conectar: {e}")
        return None

def db_load_zonas(conn, camara_id: int) -> list:
    if not conn:
        return []
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, nombre, tipo, poligono FROM zonas WHERE camara_id = %s",
        (camara_id,)
    )
    zonas = []
    for row in cur.fetchall():
        pol = row["poligono"]
        if isinstance(pol, str):
            pol = json.loads(pol)
        zonas.append({"id": row["id"], "nombre": row["nombre"], "tipo": row["tipo"], "poligono": pol})
    cur.close()
    return zonas

CAMARA_NOMBRES = {
    1: ("Camara 01", "Entrada principal"),
    2: ("Camara 02", "Caja"),
    3: ("Camara 03", "Gondolas"),
    4: ("Camara 04", "Deposito / exterior"),
}

def db_asegurar_camara(conn, camara_id: int):
    if not conn:
        return
    cur = conn.cursor()
    cur.execute("SELECT id FROM camaras WHERE id = %s", (camara_id,))
    if cur.fetchone() is None:
        nombre, ubicacion = CAMARA_NOMBRES.get(camara_id, (f"Camara {camara_id:02d}", "Sin ubicacion"))
        cur.execute(
            "INSERT INTO camaras (id, nombre, ubicacion, rtsp_url) VALUES (%s, %s, %s, %s)",
            (camara_id, nombre, ubicacion, f"rtsp://192.168.1.{9 + camara_id}:554/stream1")
        )
        conn.commit()
        print(f"[DB] Camara {camara_id} creada: '{nombre}'")
    cur.close()

def db_crear_sesion(conn, camara_id: int, inicio: datetime, archivo_path: str):
    if not conn:
        return None
    db_asegurar_camara(conn, camara_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sesiones_video (camara_id, inicio, archivo_path) VALUES (%s, %s, %s) RETURNING id",
        (camara_id, inicio, str(Path(archivo_path).resolve()))
    )
    sesion_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    print(f"[DB] Sesion creada -> id={sesion_id}, camara_id={camara_id}, inicio={inicio}")
    return sesion_id

def db_cerrar_sesion(conn, sesion_id, fin: datetime):
    if not conn or not sesion_id:
        return
    cur = conn.cursor()
    cur.execute("UPDATE sesiones_video SET fin = %s WHERE id = %s", (fin, sesion_id))
    conn.commit()
    cur.close()
    print(f"[DB] Sesion cerrada -> fin={fin}")

def db_guardar_personas(conn, sesion_id, rows_data: list, traj_buffer: list, fps: float, inicio: datetime):
    if not conn or not sesion_id:
        return
    cur = conn.cursor()
    stable_to_db = {}
    for r in rows_data:
        sid   = r["id"]
        p_ini = frame_to_dt(r["_first_frame"], fps, inicio)
        p_fin = frame_to_dt(r["_last_frame"],  fps, inicio)
        cur.execute(
            "INSERT INTO personas "
            "(sesion_id, primera_deteccion, ultima_deteccion, metodo_reid, descripcion_visual) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (sesion_id, p_ini, p_fin, r.get("metodo_reid"), r.get("descripcion"))
        )
        stable_to_db[sid] = cur.fetchone()[0]
    conn.commit()
    print(f"[DB] {len(rows_data)} personas insertadas.")

    if GUARDAR_TRAYECTORIAS and traj_buffer:
        batch = []
        for t in traj_buffer:
            persona_db_id = stable_to_db.get(t["sid"])
            if persona_db_id is None:
                continue
            ts = frame_to_dt(t["frame"], fps, inicio)
            batch.append((
                persona_db_id, t["zona_id"], ts,
                round(t["cx"], 2), round(t["cy"], 2),
                round(t["box"][0], 2), round(t["box"][1], 2),
                round(t["box"][2], 2), round(t["box"][3], 2),
            ))
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO trayectorias "
            "(persona_id, zona_id, timestamp, centroide_x, centroide_y, "
            " bbox_x1, bbox_y1, bbox_x2, bbox_y2) "
            "VALUES %s",
            batch,
        )
        conn.commit()
        print(f"[DB] {len(batch)} trayectorias insertadas.")
    cur.close()

def db_guardar_heatmap(conn, camara_id, sesion_id, inicio_dt, fin_dt,
                        accumulator, zonas, frame_w, frame_h,
                        total_detecciones, frames_procesados, last_frame):
    if not conn:
        return None
    if accumulator.max() == 0:
        print("[Heatmap] Acumulador vacio, no se guarda en BD.")
        return None

    valor_maximo = float(accumulator.max())
    hm_norm      = accumulator / valor_maximo

    # Punto con mayor calor acumulado
    flat_idx              = accumulator.argmax()
    punto_max_y, punto_max_x = np.unravel_index(flat_idx, accumulator.shape)

    # Porcentaje del frame con actividad detectada
    umbral          = valor_maximo * HEATMAP_UMBRAL
    area_activa_pct = float((accumulator > umbral).sum() / accumulator.size * 100)

    # Concentracion: que tanto del calor total cae en el top 10% de pixeles activos
    flat    = accumulator.flatten()
    activos = flat[flat > 0]
    if len(activos) > 0:
        top_umbral    = np.percentile(activos, 90)
        concentracion = float(flat[flat >= top_umbral].sum() / flat.sum())
    else:
        concentracion = 0.0

    # Zona con mayor calor acumulado
    zona_id_mas_caliente = None
    if zonas:
        max_calor, mejor_zona = -1, None
        for z in zonas:
            mask = np.zeros((frame_h, frame_w), dtype=np.uint8)
            pts  = np.array(z["poligono"], dtype=np.int32)
            cv2.fillPoly(mask, [pts], 1)
            calor = float((accumulator * mask).sum())
            if calor > max_calor:
                max_calor, mejor_zona = calor, z["id"]
        zona_id_mas_caliente = mejor_zona

    # Matriz comprimida para guardar en BD (HEATMAP_GRID x HEATMAP_GRID)
    matriz_small = cv2.resize(hm_norm, (HEATMAP_GRID, HEATMAP_GRID))
    matriz_json  = json.dumps([[round(float(v), 4) for v in row] for row in matriz_small])

    # Guardar imagenes PNG
    hm_uint8     = (hm_norm * 255).astype(np.uint8)
    hm_color     = cv2.applyColorMap(hm_uint8, cv2.COLORMAP_JET)
    ts_str       = inicio_dt.strftime("%Y%m%d_%H%M%S")
    img_puro     = f"heatmap_puro_{camara_id}_{ts_str}.png"
    img_overlay  = f"heatmap_overlay_{camara_id}_{ts_str}.png"
    cv2.imwrite(img_puro, hm_color)
    if last_frame is not None:
        overlay = cv2.addWeighted(last_frame, 0.4, hm_color, 0.6, 0)
        cv2.imwrite(img_overlay, overlay)
        print(f"[Heatmap] Guardado: {img_overlay}")
    print(f"[Heatmap] Guardado: {img_puro}")

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO mapas_calor
            (camara_id, sesion_id, periodo_inicio, periodo_fin, granularidad,
             matriz, resolucion_x, resolucion_y, imagen_path,
             punto_max_x, punto_max_y, valor_maximo,
             area_activa_pct, concentracion, zona_id_mas_caliente,
             total_detecciones, frames_procesados)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (camara_id, periodo_inicio, granularidad) DO UPDATE SET
            sesion_id             = EXCLUDED.sesion_id,
            periodo_fin           = EXCLUDED.periodo_fin,
            matriz                = EXCLUDED.matriz,
            imagen_path           = EXCLUDED.imagen_path,
            punto_max_x           = EXCLUDED.punto_max_x,
            punto_max_y           = EXCLUDED.punto_max_y,
            valor_maximo          = EXCLUDED.valor_maximo,
            area_activa_pct       = EXCLUDED.area_activa_pct,
            concentracion         = EXCLUDED.concentracion,
            zona_id_mas_caliente  = EXCLUDED.zona_id_mas_caliente,
            total_detecciones     = EXCLUDED.total_detecciones,
            frames_procesados     = EXCLUDED.frames_procesados
        RETURNING id
    """, (
        camara_id, sesion_id, inicio_dt, fin_dt, "dia",
        matriz_json, HEATMAP_GRID, HEATMAP_GRID, img_overlay or img_puro,
        int(punto_max_x), int(punto_max_y), round(valor_maximo, 4),
        round(area_activa_pct, 2), round(concentracion, 4), zona_id_mas_caliente,
        total_detecciones, frames_procesados,
    ))
    heatmap_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    print(f"[DB] Heatmap guardado -> id={heatmap_id}  "
          f"| punto_max=({int(punto_max_x)},{int(punto_max_y)})  "
          f"| area_activa={area_activa_pct:.1f}%  "
          f"| concentracion={concentracion:.2f}")
    return heatmap_id

# ── Determinar camara e inicio de grabacion ────────────────────────────────────
try:
    camara_id = CAMARA_ID_OVERRIDE or parse_camara_id(VIDEO_PATH)
    inicio_dt = parse_inicio(VIDEO_PATH)
    print(f"Camara detectada : {camara_id}  (desde '{Path(VIDEO_PATH).name}')")
    print(f"Inicio grabacion : {inicio_dt}")
except ValueError as e:
    print(f"[AVISO] {e}")
    camara_id = None
    inicio_dt = datetime.now()

# ── Conexion a BD, zonas y sesion ──────────────────────────────────────────────
conn      = db_connect() if camara_id else None
zonas     = db_load_zonas(conn, camara_id) if conn else []
sesion_id = db_crear_sesion(conn, camara_id, inicio_dt, VIDEO_PATH) if conn else None

if zonas:
    print(f"[DB] {len(zonas)} zonas cargadas para camara {camara_id}: {[z['nombre'] for z in zonas]}")
else:
    print(f"[DB] Sin zonas definidas para camara {camara_id}.")

# ── Inicializacion modelo y video ──────────────────────────────────────────────
model        = YOLO("yolov8n.pt")
cap          = cv2.VideoCapture(VIDEO_PATH)
fps          = cap.get(cv2.CAP_PROP_FPS) or 30
frame_w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

MAX_DIST            = frame_w * MAX_DIST_RATIO
QUICK_EXPIRY_FRAMES = int(QUICK_EXPIRY_SEC * fps)
LONG_EXPIRY_FRAMES  = int(LONG_EXPIRY_SEC * fps)
frames_a_procesar   = total_frames // FRAME_SKIP

print(f"\nVideo           : {VIDEO_PATH}")
print(f"Resolucion      : {frame_w}x{frame_h}  |  {fps:.0f}fps  |  {total_frames:,} frames")
print(f"Frames a leer   : {frames_a_procesar:,}  (frame_skip={FRAME_SKIP})")
print()

# ── Heatmap init ───────────────────────────────────────────────────────────────
heatmap_accumulator = np.zeros((frame_h, frame_w), dtype=np.float32)
kernel              = make_gaussian(GAUSSIAN_RADIUS)
total_detecciones   = 0
preview_counter     = 0

# ── Tracking init ──────────────────────────────────────────────────────────────
frame_count         = 0
max_personas        = 0
next_stable_id      = 1
bytetrack_to_stable = {}
lost_tracks         = {}
active_boxes        = {}
app_samples         = {}
first_seen          = {}
last_seen           = {}
streak_frames       = {}
metodo_reid         = {}   # sid -> metodo de la ultima (re)identificacion: nuevo/posicion/apariencia/gemini
conteo_metodo_reid  = {"nuevo": 0, "posicion": 0, "apariencia": 0, "gemini": 0}
traj_buffer         = []
last_frame          = None

pbar = tqdm(total=frames_a_procesar, unit="fr", desc="Analizando") if HAS_TQDM else None

# ── Loop principal ─────────────────────────────────────────────────────────────
while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    if frame_count % FRAME_SKIP != 0:
        continue

    last_frame = frame

    if pbar:
        pbar.update(1)
    elif frame_count % (FRAME_SKIP * 500) == 0:
        pct = frame_count / total_frames * 100
        print(f"  {pct:.1f}%  [{to_timestamp(frame_count, fps)}]", end="\r")

    results = model.track(
        frame,
        classes=[0],
        conf=CONF,
        tracker="bytetrack_custom.yaml",
        persist=True,
        verbose=False,
    )

    r = results[0]
    current_stable_ids = set()

    if r.boxes is not None and r.boxes.id is not None:
        ids   = r.boxes.id.int().tolist()
        boxes = r.boxes.xyxy.tolist()

        if len(ids) > max_personas:
            max_personas = len(ids)

        for bt_id, box in zip(ids, boxes):
            if bt_id not in bytetrack_to_stable:
                new_app        = compute_appearance(frame, box)
                best_sid       = None
                best_metodo    = None
                best_pos_score = -1
                best_app_score = -1

                for sid, info in lost_tracks.items():
                    frames_perdido = frame_count - info["last_frame"]
                    if frames_perdido > LONG_EXPIRY_FRAMES:
                        continue
                    if frames_perdido <= QUICK_EXPIRY_FRAMES:
                        d = centroid_dist(box, info["last_box"])
                        if d < MAX_DIST:
                            score = 1.0 - (d / MAX_DIST)
                            if score > best_pos_score:
                                best_pos_score = score
                                best_sid = sid
                                best_metodo = "posicion"
                    elif new_app is not None and info.get("mean_app") is not None:
                        sim = appearance_sim(new_app, info["mean_app"])
                        if sim >= APPEARANCE_THRESH and sim > best_app_score:
                            best_app_score = sim
                            best_sid = sid
                            best_metodo = "apariencia"

                if best_sid is not None:
                    bytetrack_to_stable[bt_id] = best_sid
                    del lost_tracks[best_sid]
                    metodo_resolucion = best_metodo
                else:
                    # Disparador: el matching local (posicion/apariencia) fallo.
                    # Antes de darlo por un cliente nuevo, se lo comparamos a
                    # Gemini contra los candidatos perdidos que ya tienen descripcion.
                    candidatos_gemini = [
                        {"sid": cand_sid, "descripcion": registro_clientes[cand_sid]["descripcion"]}
                        for cand_sid, info in lost_tracks.items()
                        if frame_count - info["last_frame"] <= LONG_EXPIRY_FRAMES
                        and registro_clientes.get(cand_sid, {}).get("descripcion")
                    ]

                    sid_gemini = None
                    if candidatos_gemini:
                        crop_nuevo = safe_crop(frame, box)
                        if crop_nuevo.size > 0:
                            resultado = clasificar_con_gemini(crop_nuevo, candidatos_gemini)
                            try:
                                sid_gemini = int(resultado) if resultado is not None else None
                            except (TypeError, ValueError):
                                sid_gemini = None
                            if sid_gemini is not None and sid_gemini not in lost_tracks:
                                sid_gemini = None  # Gemini alucino un id que no era candidato valido

                    if sid_gemini is not None:
                        print(f"[Gemini] bytetrack {bt_id} reidentificado como cliente {sid_gemini}")
                        bytetrack_to_stable[bt_id] = sid_gemini
                        del lost_tracks[sid_gemini]
                        metodo_resolucion = "gemini"
                    else:
                        bytetrack_to_stable[bt_id] = next_stable_id
                        next_stable_id += 1
                        metodo_resolucion = "nuevo"

                sid_resuelto = bytetrack_to_stable[bt_id]
                metodo_reid[sid_resuelto] = metodo_resolucion
                conteo_metodo_reid[metodo_resolucion] = conteo_metodo_reid.get(metodo_resolucion, 0) + 1

            sid = bytetrack_to_stable[bt_id]
            current_stable_ids.add(sid)
            active_boxes[sid] = box

            if sid not in first_seen:
                first_seen[sid] = frame_count
            if last_seen.get(sid) == frame_count - FRAME_SKIP:
                streak_frames[sid] = streak_frames.get(sid, 0) + 1
            else:
                streak_frames[sid] = 1
            last_seen[sid] = frame_count

            # Generacion UNICA de la descripcion visual: recien cuando el ID
            # lleva suficientes frames consecutivos confirmados (buen recorte,
            # sin oclusiones raras) y todavia no tiene descripcion guardada.
            descripcion_nueva = None
            if (USAR_GEMINI_REID
                    and streak_frames[sid] == DESCRIPCION_STREAK_FRAMES
                    and not registro_clientes.get(sid, {}).get("descripcion")):
                crop_confirmado = safe_crop(frame, box)
                if crop_confirmado.size > 0:
                    descripcion_nueva = generar_descripcion_gemini(crop_confirmado)
                    if descripcion_nueva:
                        print(f"[Gemini] Cliente {sid} descrito: {descripcion_nueva}")
            registrar_o_actualizar_cliente(sid, frame_count, estado="activo", descripcion=descripcion_nueva)

            app = compute_appearance(frame, box)
            if app is not None:
                if sid not in app_samples:
                    app_samples[sid] = []
                samples = app_samples[sid]
                if len(samples) < MAX_APP_SAMPLES:
                    samples.append(app)
                else:
                    samples[frame_count % MAX_APP_SAMPLES] = app

            cx = (box[0] + box[2]) / 2
            cy = (box[1] + box[3]) / 2

            # Acumular calor en la posicion del centroide
            stamp_heat(heatmap_accumulator, int(cx), int(cy), kernel, GAUSSIAN_RADIUS)
            total_detecciones += 1

            if conn:
                traj_buffer.append({
                    "sid":     sid,
                    "frame":   frame_count,
                    "cx":      cx,
                    "cy":      cy,
                    "box":     box,
                    "zona_id": get_zona_id(cx, cy, zonas),
                })

    for sid in list(active_boxes.keys()):
        if sid not in current_stable_ids:
            samples  = app_samples.get(sid, [])
            mean_app = np.mean(samples, axis=0).astype(np.float32) if samples else None
            lost_tracks[sid] = {
                "last_box":   active_boxes[sid],
                "last_frame": frame_count,
                "mean_app":   mean_app,
            }
            del active_boxes[sid]
            registrar_o_actualizar_cliente(sid, frame_count, estado="perdido")

    expirados = [s for s, i in lost_tracks.items()
                 if frame_count - i["last_frame"] > LONG_EXPIRY_FRAMES]
    for sid in expirados:
        del lost_tracks[sid]

    # Preview del heatmap en tiempo real
    if SHOW_PREVIEW:
        preview_counter += 1
        if preview_counter % PREVIEW_CADA_N == 0:
            overlay = render_heatmap(heatmap_accumulator, frame, alpha_bg=0.5)
            if r.boxes is not None:
                for box in r.boxes.xyxy.tolist():
                    x1, y1, x2, y2 = map(int, box)
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
            pct = frame_count / total_frames * 100 if total_frames else 0
            cv2.putText(overlay, f"Frame {frame_count}/{total_frames} ({pct:.0f}%)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.imshow("OptiFull - Deteccion + Heatmap", resize_for_display(overlay))
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

if pbar:
    pbar.close()
if SHOW_PREVIEW:
    cv2.destroyAllWindows()
cap.release()

frames_procesados = frame_count // FRAME_SKIP

# ── Cerrar sesion ──────────────────────────────────────────────────────────────
fin_dt = frame_to_dt(total_frames, fps, inicio_dt)
db_cerrar_sesion(conn, sesion_id, fin_dt)

# ── Construir resultados de permanencia ────────────────────────────────────────
rows = []
for sid in sorted(first_seen.keys()):
    dur_sec = (last_seen[sid] - first_seen[sid] + 1) / fps
    rows.append({
        "id":           sid,
        "_first_frame": first_seen[sid],
        "_last_frame":  last_seen[sid],
        "entrada":      to_timestamp(first_seen[sid], fps),
        "salida":       to_timestamp(last_seen[sid],  fps),
        "duracion_seg": round(dur_sec, 1),
        "duracion_min": round(dur_sec / 60, 2),
        "metodo_reid":  metodo_reid.get(sid, "nuevo"),
        "descripcion":  registro_clientes.get(sid, {}).get("descripcion"),
    })

# ── Guardar personas y trayectorias en BD ──────────────────────────────────────
db_guardar_personas(conn, sesion_id, rows, traj_buffer, fps, inicio_dt)

# ── Guardar heatmap en BD ──────────────────────────────────────────────────────
db_guardar_heatmap(
    conn, camara_id, sesion_id, inicio_dt, fin_dt,
    heatmap_accumulator, zonas, frame_w, frame_h,
    total_detecciones, frames_procesados, last_frame,
)

if conn:
    conn.close()

# ── Guardar CSV ────────────────────────────────────────────────────────────────
CSV_FIELDS = ["id", "entrada", "salida", "duracion_seg", "duracion_min", "metodo_reid", "descripcion"]
with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows([{k: v for k, v in r.items() if k in CSV_FIELDS} for r in rows])

# ── Resumen ────────────────────────────────────────────────────────────────────
duraciones = [r["duracion_seg"] for r in rows]
promedio   = sum(duraciones) / len(duraciones) if duraciones else 0

def dist_bucket(sec):
    if sec < 60:   return "< 1 min"
    if sec < 300:  return "1-5 min"
    if sec < 900:  return "5-15 min"
    if sec < 3600: return "15-60 min"
    return "> 1 hora"

buckets = {}
for d in duraciones:
    b = dist_bucket(d)
    buckets[b] = buckets.get(b, 0) + 1

print("\n" + "=" * 52)
print("           RESUMEN DE ANALISIS")
print("=" * 52)
print(f"  Camara                      : {camara_id or 'desconocida'}")
print(f"  Sesion BD                   : {sesion_id or 'no guardada'}")
print(f"  Personas unicas detectadas  : {len(rows)}")
print(f"  Maximas personas simultaneas: {max_personas}")
print(f"  Permanencia promedio        : {promedio/60:.1f} min")
if duraciones:
    idx_max = duraciones.index(max(duraciones))
    idx_min = duraciones.index(min(duraciones))
    print(f"  Permanencia maxima          : {max(duraciones)/60:.1f} min  (ID {rows[idx_max]['id']})")
    print(f"  Permanencia minima          : {min(duraciones)/60:.1f} min  (ID {rows[idx_min]['id']})")
print(f"  Total detecciones heatmap   : {total_detecciones:,}")
print(f"  Frames procesados           : {frames_procesados:,}")
print()
print("  Auditoria de Re-ID (metodo de resolucion por bytetrack id):")
total_resoluciones = sum(conteo_metodo_reid.values())
for metodo in ["nuevo", "posicion", "apariencia", "gemini"]:
    cnt = conteo_metodo_reid.get(metodo, 0)
    pct = (cnt / total_resoluciones * 100) if total_resoluciones else 0
    print(f"    {metodo:<12}: {cnt:>4}  ({pct:.1f}%)")
total_reid = total_resoluciones - conteo_metodo_reid.get("nuevo", 0)
if total_reid > 0:
    pct_gemini = conteo_metodo_reid.get("gemini", 0) / total_reid * 100
    pct_local  = 100 - pct_gemini
    print(f"    -> de las reidentificaciones (excluyendo altas nuevas): "
          f"{pct_local:.1f}% local, {pct_gemini:.1f}% Gemini")
print()
print("  Distribucion:")
for bucket in ["< 1 min", "1-5 min", "5-15 min", "15-60 min", "> 1 hora"]:
    count = buckets.get(bucket, 0)
    print(f"    {bucket:<12}: {count:>4}  {'|' * count}")
print()
print(f"  CSV guardado en : {OUTPUT_CSV}")
if sesion_id:
    print(f"  BD              : sesion={sesion_id}, {len(rows)} personas, {len(traj_buffer)} trayectorias")
print("=" * 52)

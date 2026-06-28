from ultralytics import YOLO
import cv2
import csv
import re
import json
import numpy as np
from datetime import timedelta, datetime
from pathlib import Path

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import mysql.connector
    HAS_DB = True
except ImportError:
    HAS_DB = False
    print("[DB] mysql-connector-python no instalado. Solo se guardara en CSV.")

# ── Configuracion ──────────────────────────────────────────────────────────────
VIDEO_PATH        = "D:\\D04_20260520015800.mp4"
FRAME_SKIP        = 5
CONF              = 0.3
MAX_DIST_RATIO    = 0.15
QUICK_EXPIRY_SEC  = 15.0
LONG_EXPIRY_SEC   = 1800.0
APPEARANCE_THRESH = 0.72
MAX_APP_SAMPLES   = 20
OUTPUT_CSV        = "permanencia.csv"

# ── Base de datos ──────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "root",
    "database": "optifull",
}
# Si el nombre del video no sigue el formato D01_... puedes forzar la camara aqui
CAMARA_ID_OVERRIDE   = None
GUARDAR_TRAYECTORIAS = True   # False ahorra espacio en BD para videos muy largos

# ── Helpers de video / filename ────────────────────────────────────────────────
def parse_camara_id(video_path: str) -> int:
    """D01_... -> 1   |   D04_... -> 4"""
    name = Path(video_path).stem.upper()
    m = re.match(r"D(\d{2})", name)
    if m:
        return int(m.group(1))
    raise ValueError(
        f"No se pudo determinar la camara desde '{Path(video_path).name}'. "
        f"Formato esperado: D01_..., D02_..., D03_..., D04_... "
        f"O seteá CAMARA_ID_OVERRIDE manualmente."
    )

def parse_inicio(video_path: str) -> datetime:
    """Extrae datetime de inicio del nombre o usa mtime.
    Soporta: D04_20260520015800  y  D04_20260520_015800
    """
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
def compute_appearance(frame, box):
    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    crop = frame[y1:y2, x1:x2]
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

# ── DB helpers ─────────────────────────────────────────────────────────────────
def db_connect():
    if not HAS_DB:
        return None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        print("[DB] Conexion exitosa.")
        return conn
    except Exception as e:
        print(f"[DB] No se pudo conectar: {e}")
        return None

def db_load_zonas(conn, camara_id: int) -> list:
    if not conn:
        return []
    cur = conn.cursor(dictionary=True)
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
    """Inserta la camara si todavia no existe en la tabla camaras."""
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
        print(f"[DB] Camara {camara_id} creada automaticamente: '{nombre}'")
    cur.close()

def db_crear_sesion(conn, camara_id: int, inicio: datetime, archivo_path: str):
    if not conn:
        return None
    db_asegurar_camara(conn, camara_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sesiones_video (camara_id, inicio, archivo_path) VALUES (%s, %s, %s)",
        (camara_id, inicio, str(Path(archivo_path).resolve()))
    )
    conn.commit()
    sesion_id = cur.lastrowid
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

def db_guardar_resultados(conn, sesion_id, rows_data: list, traj_buffer: list, fps: float, inicio: datetime):
    if not conn or not sesion_id:
        return
    cur = conn.cursor()

    # 1. Insertar personas y mapear stable_id -> persona_id en BD
    stable_to_db = {}
    for r in rows_data:
        sid   = r["id"]
        p_ini = frame_to_dt(r["_first_frame"], fps, inicio)
        p_fin = frame_to_dt(r["_last_frame"],  fps, inicio)
        cur.execute(
            "INSERT INTO personas (sesion_id, primera_deteccion, ultima_deteccion) VALUES (%s, %s, %s)",
            (sesion_id, p_ini, p_fin)
        )
        stable_to_db[sid] = cur.lastrowid
    conn.commit()
    print(f"[DB] {len(rows_data)} personas insertadas.")

    # 2. Insertar trayectorias en batch
    if GUARDAR_TRAYECTORIAS and traj_buffer:
        batch = []
        for t in traj_buffer:
            persona_db_id = stable_to_db.get(t["sid"])
            if persona_db_id is None:
                continue
            ts = frame_to_dt(t["frame"], fps, inicio)
            batch.append((
                persona_db_id,
                t["zona_id"],
                ts,
                round(t["cx"], 2),
                round(t["cy"], 2),
                round(t["box"][0], 2),
                round(t["box"][1], 2),
                round(t["box"][2], 2),
                round(t["box"][3], 2),
            ))
        cur.executemany(
            "INSERT INTO trayectorias "
            "(persona_id, zona_id, timestamp, centroide_x, centroide_y, "
            " bbox_x1, bbox_y1, bbox_x2, bbox_y2) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            batch,
        )
        conn.commit()
        print(f"[DB] {len(batch)} trayectorias insertadas.")

    cur.close()

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

# ── Inicializacion modelo ──────────────────────────────────────────────────────
model        = YOLO("yolov8n.pt")
cap          = cv2.VideoCapture(VIDEO_PATH)
fps          = cap.get(cv2.CAP_PROP_FPS) or 30
frame_w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

MAX_DIST             = frame_w * MAX_DIST_RATIO
QUICK_EXPIRY_FRAMES  = int(QUICK_EXPIRY_SEC * fps)
LONG_EXPIRY_FRAMES   = int(LONG_EXPIRY_SEC * fps)
frames_a_procesar    = total_frames // FRAME_SKIP

print(f"\nVideo           : {VIDEO_PATH}")
print(f"Duracion        : {to_timestamp(total_frames, fps)}  ({total_frames:,} frames a {fps:.0f}fps)")
print(f"Frames a leer   : {frames_a_procesar:,}  (frame_skip={FRAME_SKIP})")
print()

frame_count    = 0
max_personas   = 0
next_stable_id = 1

bytetrack_to_stable = {}
lost_tracks         = {}
active_boxes        = {}
app_samples         = {}
first_seen          = {}
last_seen           = {}
traj_buffer         = []   # acumula puntos para insertar en trayectorias

pbar = tqdm(total=frames_a_procesar, unit="fr", desc="Analizando") if HAS_TQDM else None

# ── Loop principal ─────────────────────────────────────────────────────────────
while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    if frame_count % FRAME_SKIP != 0:
        continue

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
                best_pos_score = -1
                best_app_score = -1

                for sid, info in lost_tracks.items():
                    frames_perdido = frame_count - info["last_frame"]
                    if frames_perdido > LONG_EXPIRY_FRAMES:
                        continue

                    # Fase 1: oclusiones breves -> re-asociar por posicion
                    if frames_perdido <= QUICK_EXPIRY_FRAMES:
                        d = centroid_dist(box, info["last_box"])
                        if d < MAX_DIST:
                            score = 1.0 - (d / MAX_DIST)
                            if score > best_pos_score:
                                best_pos_score = score
                                best_sid = sid

                    # Fase 2: ausencias largas -> re-identificar por apariencia
                    elif new_app is not None and info.get("mean_app") is not None:
                        sim = appearance_sim(new_app, info["mean_app"])
                        if sim >= APPEARANCE_THRESH and sim > best_app_score:
                            best_app_score = sim
                            best_sid = sid

                if best_sid is not None:
                    bytetrack_to_stable[bt_id] = best_sid
                    del lost_tracks[best_sid]
                else:
                    bytetrack_to_stable[bt_id] = next_stable_id
                    next_stable_id += 1

            sid = bytetrack_to_stable[bt_id]
            current_stable_ids.add(sid)
            active_boxes[sid] = box

            if sid not in first_seen:
                first_seen[sid] = frame_count
            last_seen[sid] = frame_count

            app = compute_appearance(frame, box)
            if app is not None:
                if sid not in app_samples:
                    app_samples[sid] = []
                samples = app_samples[sid]
                if len(samples) < MAX_APP_SAMPLES:
                    samples.append(app)
                else:
                    samples[frame_count % MAX_APP_SAMPLES] = app

            # Acumular punto de trayectoria
            if conn:
                cx = (box[0] + box[2]) / 2
                cy = (box[1] + box[3]) / 2
                traj_buffer.append({
                    "sid":     sid,
                    "frame":   frame_count,
                    "cx":      cx,
                    "cy":      cy,
                    "box":     box,
                    "zona_id": get_zona_id(cx, cy, zonas),
                })

    # Pasar tracks que desaparecieron a lost_tracks
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

    # Limpiar lost_tracks expirados
    expirados = [s for s, i in lost_tracks.items()
                 if frame_count - i["last_frame"] > LONG_EXPIRY_FRAMES]
    for sid in expirados:
        del lost_tracks[sid]

if pbar:
    pbar.close()
cap.release()

# Cerrar sesion con el timestamp real del ultimo frame del video
fin_dt = frame_to_dt(total_frames, fps, inicio_dt)
db_cerrar_sesion(conn, sesion_id, fin_dt)

# ── Construir resultados ───────────────────────────────────────────────────────
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
    })

# Guardar en BD
db_guardar_resultados(conn, sesion_id, rows, traj_buffer, fps, inicio_dt)
if conn:
    conn.close()

# Guardar en CSV (mismas columnas de siempre, sin campos internos _)
CSV_FIELDS = ["id", "entrada", "salida", "duracion_seg", "duracion_min"]
with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows([{k: v for k, v in r.items() if k in CSV_FIELDS} for r in rows])

# ── Resumen por consola ────────────────────────────────────────────────────────
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
print()
print(f"  {'ID':<5} {'Entrada':<12} {'Salida':<12} Duracion")
print("  " + "-" * 44)
for r in rows:
    print(f"  {r['id']:<5} {r['entrada']:<12} {r['salida']:<12} {r['duracion_min']:.1f} min")

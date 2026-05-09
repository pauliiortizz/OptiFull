from ultralytics import YOLO
import cv2
import csv
import numpy as np
from datetime import timedelta

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ── Configuracion ──────────────────────────────────────────────────────────────
VIDEO_PATH        = "videos/video4.MOV"
FRAME_SKIP        = 5
CONF              = 0.3
MAX_DIST_RATIO    = 0.15    # % del ancho del frame para re-asociacion rapida por posicion
QUICK_EXPIRY_SEC  = 15.0   # segundos: re-asociar por posicion (oclusiones por mesas/sillas)
LONG_EXPIRY_SEC   = 1800.0 # segundos (30 min): re-asociar por apariencia (salidas del encuadre)
APPEARANCE_THRESH = 0.72   # similitud minima de apariencia para considerar misma persona (0-1)
MAX_APP_SAMPLES   = 20     # cuantas muestras de apariencia guardar por persona
OUTPUT_CSV        = "permanencia.csv"
# ──────────────────────────────────────────────────────────────────────────────

def centroid_dist(box1, box2):
    cx1, cy1 = (box1[0] + box1[2]) / 2, (box1[1] + box1[3]) / 2
    cx2, cy2 = (box2[0] + box2[2]) / 2, (box2[1] + box2[3]) / 2
    return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5

def to_timestamp(frame_num, fps):
    return str(timedelta(seconds=int(frame_num / fps)))

def compute_appearance(frame, box):
    """
    Histograma HSV del recorte de la persona.
    Captura color de ropa y es robusto a cambios de iluminacion.
    """
    x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 10:
        return None
    # Usar solo el torso (mitad superior del crop) para evitar ruido del suelo
    torso = crop[:crop.shape[0] // 2, :]
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0], None, [18], [0, 180]).flatten()  # tono
    s = cv2.calcHist([hsv], [1], None, [8],  [0, 256]).flatten()  # saturacion
    hist = np.concatenate([h, s]).astype(np.float32)
    hist /= hist.sum() + 1e-6
    return hist

def appearance_sim(h1, h2):
    """
    Similitud de Bhattacharyya: 1.0 = identico, 0.0 = completamente diferente.
    """
    dist = cv2.compareHist(h1.reshape(-1, 1), h2.reshape(-1, 1), cv2.HISTCMP_BHATTACHARYYA)
    return 1.0 - dist

# ── Inicializacion ────────────────────────────────────────────────────────────
model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(VIDEO_PATH)
fps          = cap.get(cv2.CAP_PROP_FPS) or 30
frame_w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

MAX_DIST             = frame_w * MAX_DIST_RATIO
QUICK_EXPIRY_FRAMES  = int(QUICK_EXPIRY_SEC * fps)
LONG_EXPIRY_FRAMES   = int(LONG_EXPIRY_SEC * fps)
frames_a_procesar    = total_frames // FRAME_SKIP

print(f"Video           : {VIDEO_PATH}")
print(f"Duracion        : {to_timestamp(total_frames, fps)}  ({total_frames:,} frames a {fps:.0f}fps)")
print(f"Frames a leer   : {frames_a_procesar:,}  (frame_skip={FRAME_SKIP})")
print()

frame_count    = 0
max_personas   = 0
next_stable_id = 1

bytetrack_to_stable = {}  # bytetrack_id  -> stable_id
lost_tracks         = {}  # stable_id     -> {last_box, last_frame, mean_app}
active_boxes        = {}  # stable_id     -> box actual
app_samples         = {}  # stable_id     -> [lista de histogramas]
first_seen          = {}  # stable_id     -> frame_count
last_seen           = {}  # stable_id     -> frame_count

pbar = tqdm(total=frames_a_procesar, unit="fr", desc="Analizando") if HAS_TQDM else None

# ── Loop principal ────────────────────────────────────────────────────────────
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
        verbose=False
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
                new_app  = compute_appearance(frame, box)
                best_sid = None
                best_pos_score = -1
                best_app_score = -1

                for sid, info in lost_tracks.items():
                    frames_perdido = frame_count - info["last_frame"]
                    if frames_perdido > LONG_EXPIRY_FRAMES:
                        continue

                    # Fase 1: oclusiones breves → re-asociar por posicion
                    if frames_perdido <= QUICK_EXPIRY_FRAMES:
                        d = centroid_dist(box, info["last_box"])
                        if d < MAX_DIST:
                            score = 1.0 - (d / MAX_DIST)
                            if score > best_pos_score:
                                best_pos_score = score
                                best_sid = sid

                    # Fase 2: ausencias largas → re-identificar por apariencia
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

            # Acumular muestras de apariencia para este track
            app = compute_appearance(frame, box)
            if app is not None:
                if sid not in app_samples:
                    app_samples[sid] = []
                samples = app_samples[sid]
                if len(samples) < MAX_APP_SAMPLES:
                    samples.append(app)
                else:
                    # Reemplazar una muestra aleatoria para mantener diversidad temporal
                    samples[frame_count % MAX_APP_SAMPLES] = app

    # Pasar tracks que desaparecieron este frame a lost_tracks
    for sid in list(active_boxes.keys()):
        if sid not in current_stable_ids:
            samples = app_samples.get(sid, [])
            mean_app = np.mean(samples, axis=0).astype(np.float32) if samples else None
            lost_tracks[sid] = {
                "last_box" : active_boxes[sid],
                "last_frame": frame_count,
                "mean_app" : mean_app,
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

# ── Resultados ────────────────────────────────────────────────────────────────
rows = []
for sid in sorted(first_seen.keys()):
    dur_sec = (last_seen[sid] - first_seen[sid] + 1) / fps
    rows.append({
        "id"          : sid,
        "entrada"     : to_timestamp(first_seen[sid], fps),
        "salida"      : to_timestamp(last_seen[sid],  fps),
        "duracion_seg": round(dur_sec, 1),
        "duracion_min": round(dur_sec / 60, 2),
    })

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["id", "entrada", "salida", "duracion_seg", "duracion_min"])
    writer.writeheader()
    writer.writerows(rows)

duraciones = [r["duracion_seg"] for r in rows]
promedio   = sum(duraciones) / len(duraciones) if duraciones else 0

def dist_bucket(sec):
    if sec < 60:     return "< 1 min"
    if sec < 300:    return "1-5 min"
    if sec < 900:    return "5-15 min"
    if sec < 3600:   return "15-60 min"
    return "> 1 hora"

buckets = {}
for d in duraciones:
    b = dist_bucket(d)
    buckets[b] = buckets.get(b, 0) + 1

print("\n" + "=" * 52)
print("           RESUMEN DE ANALISIS")
print("=" * 52)
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
    print(f"    {bucket:<12}: {count:>4}  {'█' * count}")
print()
print(f"  Detalle guardado en: {OUTPUT_CSV}")
print("=" * 52)
print()
print(f"  {'ID':<5} {'Entrada':<12} {'Salida':<12} Duracion")
print("  " + "-" * 44)
for r in rows:
    print(f"  {r['id']:<5} {r['entrada']:<12} {r['salida']:<12} {r['duracion_min']:.1f} min")

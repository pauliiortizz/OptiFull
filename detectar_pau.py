from ultralytics import YOLO
import cv2
import csv
from datetime import timedelta

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ── Configuracion ──────────────────────────────────────────────────────────────
VIDEO_PATH      = "videos/video4.mp4"
FRAME_SKIP      = 5          # procesar 1 de cada 5 frames (ajustar segun necesidad)
CONF            = 0.3
MAX_DIST_RATIO  = 0.15       # distancia maxima para re-asociar persona perdida (% del ancho)
LOST_EXPIRY_SEC = 5.0        # segundos que se guarda una persona "perdida" antes de descartarla
OUTPUT_CSV      = "permanencia.csv"
# ──────────────────────────────────────────────────────────────────────────────

def centroid_dist(box1, box2):
    cx1, cy1 = (box1[0] + box1[2]) / 2, (box1[1] + box1[3]) / 2
    cx2, cy2 = (box2[0] + box2[2]) / 2, (box2[1] + box2[3]) / 2
    return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5

def to_timestamp(frame_num, fps):
    return str(timedelta(seconds=int(frame_num / fps)))

model = YOLO("yolov8n.pt")   # nano: ~5x mas rapido que medium, precision suficiente para personas
cap = cv2.VideoCapture(VIDEO_PATH)
fps          = cap.get(cv2.CAP_PROP_FPS) or 30
frame_w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

MAX_DIST            = frame_w * MAX_DIST_RATIO
LOST_EXPIRY_FRAMES  = int(LOST_EXPIRY_SEC * fps)
frames_a_procesar   = total_frames // FRAME_SKIP

print(f"Video           : {VIDEO_PATH}")
print(f"Duracion        : {to_timestamp(total_frames, fps)}  ({total_frames:,} frames a {fps:.0f}fps)")
print(f"Frames a leer   : {frames_a_procesar:,}  (frame_skip={FRAME_SKIP})")
print()

frame_count    = 0
max_personas   = 0
next_stable_id = 1

bytetrack_to_stable = {}
lost_tracks         = {}
active_boxes        = {}
first_seen          = {}
last_seen           = {}

pbar = tqdm(total=frames_a_procesar, unit="fr", desc="Analizando") if HAS_TQDM else None

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
                best_sid  = None
                best_dist = MAX_DIST
                for sid, info in lost_tracks.items():
                    if frame_count - info["last_frame"] > LOST_EXPIRY_FRAMES:
                        continue
                    d = centroid_dist(box, info["last_box"])
                    if d < best_dist:
                        best_dist = d
                        best_sid  = sid

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

    for sid in list(active_boxes.keys()):
        if sid not in current_stable_ids:
            lost_tracks[sid] = {"last_box": active_boxes[sid], "last_frame": frame_count}
            del active_boxes[sid]

    for sid in [s for s, i in lost_tracks.items() if frame_count - i["last_frame"] > LOST_EXPIRY_FRAMES]:
        del lost_tracks[sid]

if pbar:
    pbar.close()
cap.release()

# ── Calcular y mostrar resultados ──────────────────────────────────────────────
rows = []
for sid in sorted(first_seen.keys()):
    dur_sec = (last_seen[sid] - first_seen[sid] + 1) / fps
    rows.append({
        "id"           : sid,
        "entrada"      : to_timestamp(first_seen[sid], fps),
        "salida"       : to_timestamp(last_seen[sid],  fps),
        "duracion_seg" : round(dur_sec, 1),
        "duracion_min" : round(dur_sec / 60, 2),
    })

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["id", "entrada", "salida", "duracion_seg", "duracion_min"])
    writer.writeheader()
    writer.writerows(rows)

duraciones = [r["duracion_seg"] for r in rows]
promedio   = sum(duraciones) / len(duraciones) if duraciones else 0

def dist_bucket(sec):
    if sec < 60:       return "< 1 min"
    elif sec < 300:    return "1-5 min"
    elif sec < 900:    return "5-15 min"
    elif sec < 3600:   return "15-60 min"
    else:              return "> 1 hora"

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
print(f"  Permanencia maxima          : {max(duraciones)/60:.1f} min  (ID {rows[duraciones.index(max(duraciones))]['id']})")
print(f"  Permanencia minima          : {min(duraciones)/60:.1f} min  (ID {rows[duraciones.index(min(duraciones))]['id']})")
print()
print("  Distribucion:")
for bucket in ["< 1 min", "1-5 min", "5-15 min", "15-60 min", "> 1 hora"]:
    count = buckets.get(bucket, 0)
    bar   = "█" * count
    print(f"    {bucket:<12}: {count:>4}  {bar}")
print()
print(f"  Detalle guardado en: {OUTPUT_CSV}")
print("=" * 52)
print()
print(f"  {'ID':<5} {'Entrada':<12} {'Salida':<12} Duracion")
print("  " + "-" * 44)
for r in rows:
    print(f"  {r['id']:<5} {r['entrada']:<12} {r['salida']:<12} {r['duracion_min']:.1f} min")
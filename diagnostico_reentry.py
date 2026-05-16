from ultralytics import YOLO
import numpy as np

model = YOLO("yolov8s.pt")

# frame_numero -> set de IDs activos
historial = {}

results = model.track(
    source="videos/video2.mp4",
    classes=[0],
    conf=0.25,
    tracker="botsort_custom.yaml",
    stream=True
)

frame_num = 0
for r in results:
    frame_num += 1
    if r.boxes is not None and r.boxes.id is not None:
        ids = set(int(i) for i in r.boxes.id.cpu().numpy())
    else:
        ids = set()
    historial[frame_num] = ids

total_frames = frame_num

# --- analisis de re-entradas ---
# para cada ID: registrar en que frames aparece
apariciones = {}
for f, ids in historial.items():
    for id in ids:
        if id not in apariciones:
            apariciones[id] = []
        apariciones[id].append(f)

print(f"\nTotal frames analizados: {total_frames}")
print(f"IDs unicos asignados: {sorted(apariciones.keys())}\n")

AUSENCIA_MINIMA = 15  # frames sin aparecer para considerar "salio de escena"

reentradas = []
for id, frames in sorted(apariciones.items()):
    # detectar gaps de ausencia
    for i in range(len(frames) - 1):
        gap = frames[i + 1] - frames[i]
        if gap > AUSENCIA_MINIMA:
            reentradas.append({
                "id": id,
                "salio_frame": frames[i],
                "volvio_frame": frames[i + 1],
                "ausente_frames": gap
            })

if reentradas:
    print(f"IDs que salieron y VOLVIERON con el mismo ID ({len(reentradas)} eventos):")
    for e in reentradas:
        seg = e["ausente_frames"] / 30
        print(f"  ID {e['id']:>3}: salio frame {e['salio_frame']:>4}, volvio frame {e['volvio_frame']:>4}  ({e['ausente_frames']} frames ausente = ~{seg:.1f}s)")
else:
    print("Ningun ID reaparecio despues de salir de escena — todos los re-ingresos generaron IDs nuevos.")

# IDs que aparecieron una sola vez brevemente (probablemente falsos positivos)
ids_breves = [id for id, frames in apariciones.items() if len(frames) < 10]
print(f"\nIDs con menos de 10 frames (posibles falsos positivos): {ids_breves}")
print(f"\nIDs consolidados (>= 10 frames): {[id for id, frames in apariciones.items() if len(frames) >= 10]}")

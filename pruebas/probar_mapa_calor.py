import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2
from ultralytics import YOLO

VIDEO_PATH      = "videos/video4.mov"
MODEL_PATH      = "yolov8n.pt"
CONF            = 0.3
FRAME_SKIP      = 3
GAUSSIAN_RADIUS = 60   # radio del blob de calor por persona (px)
SHOW_PREVIEW    = True


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


def resize_for_display(frame: np.ndarray, max_w: int = 1280, max_h: int = 720) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        return cv2.resize(frame, (int(w * scale), int(h * scale)))
    return frame


def render_heatmap(accumulator: np.ndarray, background: np.ndarray | None,
                   alpha_bg: float = 0.5) -> np.ndarray:
    # 1. Copiamos el acumulador para no romper los datos originales
    hm = accumulator.copy()
    
    # 2. Definimos un tope máximo de "sellos" (ajusta este valor si necesitas)
    VALOR_MAX_DESEADO = 300.0  
    
    # 3. Todo lo que supere el tope se clava en ese máximo
    hm = np.clip(hm, 0, VALOR_MAX_DESEADO)
    
    # 4. Normalizamos dividiendo por el tope fijo en lugar de hm.max()
    hm /= VALOR_MAX_DESEADO
    
    # El resto del renderizado queda igual
    hm_color = cv2.applyColorMap((hm * 255).astype(np.uint8), cv2.COLORMAP_JET)
    if background is not None:
        return cv2.addWeighted(background, alpha_bg, hm_color, 1 - alpha_bg, 0)
    return hm_color


# ── Setup ──────────────────────────────────────────────────────────────────────
model  = YOLO(MODEL_PATH)
cap    = cv2.VideoCapture(VIDEO_PATH)

width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps    = cap.get(cv2.CAP_PROP_FPS) or 30
total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

heatmap_accumulator = np.zeros((height, width), dtype=np.float32)
kernel = make_gaussian(GAUSSIAN_RADIUS)

print(f"Video : {VIDEO_PATH}  ({width}x{height}, {fps:.0f}fps, {total} frames)")
print(f"Modelo: {MODEL_PATH}  |  conf={CONF}  |  frame_skip={FRAME_SKIP}")
print("Procesando... (presiona Q en la ventana para salir)\n")

frame_count = 0
last_frame  = None

# ── Loop principal ─────────────────────────────────────────────────────────────
while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    if frame_count % FRAME_SKIP != 0:
        continue

    last_frame = frame

    results = model(frame, classes=[0], conf=CONF, verbose=False)
    boxes   = results[0].boxes.xyxy.tolist() if results[0].boxes else []

    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        stamp_heat(heatmap_accumulator, cx, cy, kernel, GAUSSIAN_RADIUS)

    if SHOW_PREVIEW:
        overlay = render_heatmap(heatmap_accumulator, last_frame, alpha_bg=0.5)
        for box in boxes:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
        pct = frame_count / total * 100 if total else 0
        cv2.putText(overlay, f"Frame {frame_count}/{total}  ({pct:.0f}%)",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        preview = resize_for_display(overlay, max_w=1280, max_h=720)
        cv2.imshow("Mapa de calor - YOLO personas", preview)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()

# ── Resultado final ────────────────────────────────────────────────────────────
processed = frame_count // FRAME_SKIP
print(f"Frames procesados : {processed}")
print("Guardando imagenes finales...")

final_overlay = render_heatmap(heatmap_accumulator, last_frame, alpha_bg=0.4)
heatmap_pure  = render_heatmap(heatmap_accumulator, None)

cv2.imwrite("heatmap_overlay.png", final_overlay)
cv2.imwrite("heatmap_puro.png",    heatmap_pure)
print("  heatmap_overlay.png  (sobre el ultimo frame)")
print("  heatmap_puro.png     (mapa de calor solo)")

if SHOW_PREVIEW:
    cv2.imshow("Mapa de calor final", final_overlay)
    print("Presiona cualquier tecla para cerrar...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()

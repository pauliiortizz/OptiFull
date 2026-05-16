from ultralytics import YOLO
import cv2

# ── Configuración ──────────────────────────────────────────────
VIDEO      = "video5.mp4"
MODELO     = "yolo11m.pt"   # YOLOv11 medium (se descarga automáticamente la primera vez)
FRAME_SKIP = 5              # procesar 1 de cada N frames (ajustar: más alto = más rápido, menos preciso)
CONF_MIN   = 0.45           # umbral de confianza mínima
# ───────────────────────────────────────────────────────────────

model = YOLO(MODELO)
cap   = cv2.VideoCapture(VIDEO)

frame_count    = 0
max_simultaneo = 0
ids_vistos     = set()   # IDs únicos acumulados a lo largo del video

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    if frame_count % FRAME_SKIP != 0:
        continue

    results = model.track(
        frame,
        classes=[0],           # 0 = persona
        conf=CONF_MIN,
        tracker="bytetrack.yaml",
        persist=True,          # mantiene el estado del tracker entre frames
        verbose=False,
    )

    r          = results[0]
    frame_draw = r.plot()
    cantidad_actual = 0

    if r.boxes is not None and r.boxes.id is not None:
        ids_frame       = r.boxes.id.int().tolist()
        cantidad_actual = len(ids_frame)
        ids_vistos.update(ids_frame)
        max_simultaneo  = max(max_simultaneo, cantidad_actual)

    # ── Métricas en pantalla ──
    # "En escena" = personas detectadas en este frame exacto (sin doble conteo)
    # "Max simultáneo" = pico de personas en un único instante del video
    # "IDs únicos" = acumulado de IDs distintos (puede sobrecontar si el tracker
    #                pierde a alguien y le asigna un nuevo ID al reaparecer)
    cv2.putText(frame_draw, f"En escena:      {cantidad_actual}",
                (20,  50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (  0, 255,   0), 2)
    cv2.putText(frame_draw, f"Max simultaneo: {max_simultaneo}",
                (20,  95), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (  0, 200, 255), 2)
    cv2.putText(frame_draw, f"IDs unicos:     {len(ids_vistos)}",
                (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 150,   0), 2)

    cv2.imshow("Deteccion YOLOv11", frame_draw)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()

print("\n── Resultados finales ──────────────────────────────────")
print(f"  Máximo de personas simultáneas : {max_simultaneo}  ← métrica más confiable")
print(f"  IDs únicos acumulados          : {len(ids_vistos)}  ← aprox. visitantes totales")
print(f"  Frames procesados              : {frame_count // FRAME_SKIP} de {frame_count} totales")
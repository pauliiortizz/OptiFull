import cv2

from ultralytics import YOLO

model = YOLO("yolov8m.pt")

cap = cv2.VideoCapture("video5.mp4")

frame_skip = 3
frame_count = 0
max_personas = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1

    # 🚀 saltar frames ANTES de procesar
    if frame_count % frame_skip != 0:
        continue

    results = model.track(frame, classes=[0], conf=0.4, tracker="bytetrack.yaml", persist=True)

    r = results[0]
    frame_draw = r.plot()

    cantidad = 0

    if r.boxes is not None:
        cantidad = len(r.boxes)

        if cantidad > max_personas:
            max_personas = cantidad

    cv2.putText(frame_draw, f"Personas: {cantidad}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow("Deteccion de personas", frame_draw)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()

print("Cantidad maxima de personas:", max_personas)

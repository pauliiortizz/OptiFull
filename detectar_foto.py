from ultralytics import YOLO
import cv2

model = YOLO("yolov8n.pt")

image_path = "imagen.jpeg"
results = model.predict(source=image_path, classes=[0], conf=0.5)

img = cv2.imread(image_path)

for r in results:
    annotated = r.plot()
    cantidad = len(r.boxes) if r.boxes is not None else 0
    print("Personas detectadas:", cantidad)
    cv2.imshow("Deteccion de personas", annotated)
    cv2.waitKey(0)

cv2.destroyAllWindows()
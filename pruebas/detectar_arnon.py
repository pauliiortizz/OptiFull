# Deteccion de personas unicas en un video usando YOLOv8 + ByteTrack
from ultralytics import YOLO
import cv2

model = YOLO("yolov8s.pt")  # 's' detecta mejor poses no estandar (sentado, agachado)

personas_unicas = set()
conteo_frames_por_id = {}  # diccionario para contar frames por ID
min_frames = 10  # minimo de frames para considerar una persona valida

results = model.track(
    source="videos/video2.mp4",
    classes=[0],        # solo personas
    conf=0.25,          # bajado para capturar personas sentadas (menor confianza)
    tracker="botsort_custom.yaml",
    stream=True
)

for r in results:

    frame = r.plot()  # dibuja las cajas en el frame

    if r.boxes is not None and r.boxes.id is not None:
        ids = r.boxes.id.cpu().numpy()
        for id in ids:
            if id in conteo_frames_por_id:
                conteo_frames_por_id[id] += 1
            else:
                conteo_frames_por_id[id] = 1
            
            # agregar al set solo si ha aparecido en suficientes frames
            if conteo_frames_por_id[id] >= min_frames and id not in personas_unicas:
                personas_unicas.add(id)

    cantidad_actual = len(personas_unicas)

    # mostrar cantidad actual en pantalla
    cv2.putText(
        frame,
        f"Personas unicas: {cantidad_actual}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0,255,0),
        2
    )

    cv2.imshow("Deteccion de personas", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cv2.destroyAllWindows()

print("Cantidad total de personas unicas en el video:", len(personas_unicas))
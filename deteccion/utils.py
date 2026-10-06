"""Helpers genericos y sin estado: parsing de video/filename, geometria de zonas,
y recorte seguro de frames."""
import json
import math
import re
from datetime import timedelta, datetime
from pathlib import Path

import numpy as np
import cv2


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


# Reloj de analisis en vivo: relojes_frames[n] = hora REAL en que se proceso el
# frame n. En vivo, 'frame_num / fps' se atrasa respecto del reloj de pared
# apenas la CPU procesa menos fps que el objetivo (y los reportes "en tienda
# ahora" quedan viejos); con este reloj cada timestamp guardado es la hora real.
# None = modo video grabado (se usa frame_num / fps como siempre).
_reloj_frames = None


def set_reloj_vivo(reloj) -> None:
    global _reloj_frames
    _reloj_frames = reloj


def frame_to_dt(frame_num: int, fps: float, inicio: datetime) -> datetime:
    if _reloj_frames is not None and 0 <= frame_num < len(_reloj_frames):
        return _reloj_frames[frame_num]
    return inicio + timedelta(seconds=frame_num / fps)


def to_timestamp(frame_num, fps):
    return str(timedelta(seconds=int(frame_num / fps)))


def escalar_zonas(zonas: list, frame_w: int, frame_h: int, ref_w: int, ref_h: int) -> list:
    """Las zonas se dibujaron sobre video de ref_w x ref_h (config.ZONAS_REF_RESOLUCION).
    Si el video/stream real tiene otro tamano (ej. un RTSP sub-stream de 640x360), los
    poligonos hay que llevarlos a ese tamano -- si no, cada punto cae en la zona
    equivocada. Con el mismo tamano devuelve las zonas tal cual (factor 1)."""
    if not zonas or (frame_w, frame_h) == (ref_w, ref_h):
        return zonas
    fx, fy = frame_w / ref_w, frame_h / ref_h
    escaladas = []
    for z in zonas:
        poligono = z["poligono"]
        if isinstance(poligono, str):
            poligono = json.loads(poligono)
        escaladas.append({**z, "poligono": [[x * fx, y * fy] for x, y in poligono]})
    return escaladas


def point_in_polygon(cx, cy, polygon) -> bool:
    n, inside, j = len(polygon), False, len(polygon) - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > cy) != (yj > cy)) and (cx < (xj - xi) * (cy - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def _dist_punto_segmento(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _dist_a_poligono(cx, cy, polygon) -> float:
    n = len(polygon)
    return min(
        _dist_punto_segmento(cx, cy, polygon[i][0], polygon[i][1], polygon[(i + 1) % n][0], polygon[(i + 1) % n][1])
        for i in range(n)
    )


def get_zona_id(cx, cy, zonas: list, max_dist_borde: float = 20.0):
    """Devuelve el id de la zona cuyo poligono contiene (cx, cy). Si el punto
    no cae DENTRO de ninguna, cae de vuelta a la zona mas cercana por
    distancia al borde (mientras este a <= max_dist_borde px) -- cubre el
    caso de personas cortadas justo en el limite del frame (bbox_y2 pegado a
    la altura del video), cuyo pie estimado queda 5-15px mas abajo que donde
    llega el poligono dibujado a mano, sin ser realmente una posicion fuera
    de zona. Un punto lejos de TODO poligono (fuera de cobertura real, ej.
    fondo sin zona definida) sigue devolviendo None."""
    for z in zonas:
        if point_in_polygon(cx, cy, z["poligono"]):
            return z["id"]
    mejor_id, mejor_dist = None, max_dist_borde
    for z in zonas:
        d = _dist_a_poligono(cx, cy, z["poligono"])
        if d < mejor_dist:
            mejor_id, mejor_dist = z["id"], d
    return mejor_id


def safe_crop(frame: np.ndarray, box) -> np.ndarray:
    """Recorta el frame segun el bbox, clampeando a los bordes de la imagen
    para que nunca falle (slice vacio o negativo) en los margenes de la pantalla."""
    h, w = frame.shape[:2]
    x1 = max(0, min(int(box[0]), w))
    y1 = max(0, min(int(box[1]), h))
    x2 = max(0, min(int(box[2]), w))
    y2 = max(0, min(int(box[3]), h))
    return frame[y1:y2, x1:x2]


def cerca_de_zona_tipo(cx, cy, zonas: list, tipo: str, max_dist: float) -> bool:
    """True si (cx, cy) cae DENTRO de alguna zona de tipo 'tipo', o a menos de
    'max_dist' px de su borde. Pensado para 'Zona Caja': en este sistema esa
    zona representa el LADO DEL EMPLEADO del mostrador (ver
    Persistencia.limpiar_trayectorias_fuera_de_zona, "Zona Caja es exclusiva
    de empleados") -- un cliente pagando casi nunca pisa el poligono en si,
    solo se ACERCA desde el lado de enfrente. Exigir point_in_polygon puro
    (como hace get_zona_id para el resto de las zonas) dejaria a casi
    cualquier compra normal sin 'paso por caja', y la clasificarian como
    POSIBLE_HURTO por error -- ver pipeline/eventos.py."""
    for z in zonas:
        if z["tipo"] != tipo:
            continue
        if point_in_polygon(cx, cy, z["poligono"]):
            return True
        if _dist_a_poligono(cx, cy, z["poligono"]) <= max_dist:
            return True
    return False


def detectar_productos(model, frame: np.ndarray, clases: list, conf: float) -> list:
    """Corre una deteccion SUELTA (sin tracking, sin persist=True) de las
    clases COCO configuradas como 'producto' (ver PRODUCTO_CLASES_COCO en
    config.py) y devuelve sus boxes [x1,y1,x2,y2]. Se llama con un modelo YOLO
    APARTE del que trackea personas -- mezclar clases en el mismo model.track()
    rompe el supuesto de PersonTracker.procesar_frame() de que todo box con id
    de ByteTrack es una persona, y ademas pisaria el estado interno de
    tracking (persist=True) que mantiene ese otro modelo entre frames."""
    if not clases:
        return []
    results = model(frame, classes=clases, conf=conf, verbose=False)
    r = results[0]
    if r.boxes is None:
        return []
    return r.boxes.xyxy.tolist()


def producto_cerca_de_persona(box_persona, boxes_producto: list, margen_px: float = 15.0) -> bool:
    """True si el CENTRO de algun box de producto cae dentro del box de la
    persona expandido 'margen_px' de cada lado. Es una aproximacion barata de
    "lo tiene en la mano/brazo" sin depender de deteccion de pose/manos: no
    exige que el producto quede DENTRO del torso (normalmente esta en el brazo,
    parcialmente afuera del box ajustado) ni usa IoU (un objeto chico como una
    botella casi no solapa area con el box de una persona adulta aunque la
    este sosteniendo)."""
    x1, y1, x2, y2 = box_persona
    x1, y1, x2, y2 = x1 - margen_px, y1 - margen_px, x2 + margen_px, y2 + margen_px
    for bx1, by1, bx2, by2 in boxes_producto:
        cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            return True
    return False


def resize_for_display(frame: np.ndarray, max_w: int = 1280, max_h: int = 720) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        return cv2.resize(frame, (int(w * scale), int(h * scale)))
    return frame

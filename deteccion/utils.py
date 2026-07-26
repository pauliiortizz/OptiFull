"""Helpers genericos y sin estado: parsing de video/filename, geometria de zonas,
y recorte seguro de frames."""
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


def frame_to_dt(frame_num: int, fps: float, inicio: datetime) -> datetime:
    return inicio + timedelta(seconds=frame_num / fps)


def to_timestamp(frame_num, fps):
    return str(timedelta(seconds=int(frame_num / fps)))


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


def resize_for_display(frame: np.ndarray, max_w: int = 1280, max_h: int = 720) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        return cv2.resize(frame, (int(w * scale), int(h * scale)))
    return frame

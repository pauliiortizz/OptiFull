"""Helpers genericos y sin estado: parsing de video/filename, geometria de zonas,
y recorte seguro de frames."""
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


def get_zona_id(cx, cy, zonas: list):
    for z in zonas:
        if point_in_polygon(cx, cy, z["poligono"]):
            return z["id"]
    return None


def es_uniforme_empleado(descripcion, colores_uniforme: list, accesorio_uniforme: str) -> bool:
    """Heuristica de UNIFORME: remera de alguno de 'colores_uniforme'
    combinada con 'accesorio_uniforme' (ej. gorra) en el campo accesorios --
    a diferencia de la heuristica de permanencia (que solo sugiere), este es
    un patron deliberado y estable (el local elige ese uniforme a proposito)
    asi que alcanza para marcar es_empleado automaticamente, sin esperar
    confirmacion manual. Comparacion por substring (no exacta) para que
    matchee tambien colores combinados como 'gris/negro'."""
    if not descripcion:
        return False
    color_superior = str(descripcion.get("color_ropa_superior", "")).strip().lower()
    accesorios     = str(descripcion.get("accesorios", "")).strip().lower()
    if accesorio_uniforme not in accesorios:
        return False
    return any(color in color_superior for color in colores_uniforme)


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

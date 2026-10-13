"""Foto de cada persona detectada, para que el usuario pueda decidir si es empleado o no.

Un ID de persona o un rango de horas no alcanzan para que alguien reconozca a quien vio en pantalla: hace falta
verla. Este modulo se queda, para cada persona que el tracker sigue, con el MEJOR recorte que vio (el de caja mas
grande y sin tocar el borde del cuadro) y, cuando la persona lleva un rato en camara, lo sube a Storage y deja la
URL en personas.foto_url. La subida corre en un hilo aparte para no frenar el analisis.

El frontend usa esa foto en la alerta "Persona posiblemente empleada" (ver frontend/api/alertas.py).
"""
import threading
from typing import Optional

import cv2
import numpy as np

from deteccion.pipeline.evidencia import _guardar

_MARGEN = 0.12        # el recorte incluye un 12% de aire alrededor de la caja de la persona
_ALTO_MAX = 420       # px: la foto es de referencia, no hace falta mas


def recortar_persona(frame_bgr: np.ndarray, box, margen: float = _MARGEN) -> Optional[np.ndarray]:
    """Recorte de la persona con algo de margen, o None si la caja queda vacia/fuera del cuadro."""
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = map(float, box)
    mx, my = (x2 - x1) * margen, (y2 - y1) * margen
    x1, y1 = int(max(0, x1 - mx)), int(max(0, y1 - my))
    x2, y2 = int(min(w, x2 + mx)), int(min(h, y2 + my))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return frame_bgr[y1:y2, x1:x2].copy()


def tocando_borde(box, w: int, h: int, tolerancia: int = 4) -> bool:
    """True si la caja toca el borde del cuadro: la persona esta cortada y el recorte seria peor foto."""
    x1, y1, x2, y2 = box
    return x1 <= tolerancia or y1 <= tolerancia or x2 >= w - tolerancia or y2 >= h - tolerancia


def a_jpg(recorte: np.ndarray, calidad: int = 88) -> Optional[bytes]:
    h = recorte.shape[0]
    if h > _ALTO_MAX:
        escala = _ALTO_MAX / h
        recorte = cv2.resize(recorte, (max(1, int(recorte.shape[1] * escala)), _ALTO_MAX), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", recorte, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    return buf.tobytes() if ok else None


def publicar_foto(storage, database_url: str, persona_db_id: int, jpg: bytes) -> Optional[str]:
    """Sube la foto y la deja en personas.foto_url (solo si la persona todavia no tiene una). Pensada para un hilo
    aparte: usa su PROPIA conexion a la BD."""
    import psycopg2
    try:
        url = _guardar(storage, f"evidencias/personas/persona_{persona_db_id}.jpg", jpg, "image/jpeg")
        conn = psycopg2.connect(database_url)
        try:
            cur = conn.cursor()
            cur.execute("UPDATE personas SET foto_url = %s WHERE id = %s AND foto_url IS NULL", (url, persona_db_id))
            conn.commit()
            cur.close()
        finally:
            conn.close()
        print(f"[Foto] Persona #{persona_db_id}: foto guardada.")
        return url
    except Exception as error:
        print(f"[Foto] No se pudo guardar la foto de la persona #{persona_db_id}: {error}")
        return None


class CapturadorFotos:
    def __init__(self, storage, database_url: str, fps: float, min_seg: float = 120) -> None:
        self.storage = storage
        self.database_url = database_url
        self.min_frames = max(1, round(min_seg * fps))
        self._mejor: dict = {}       # sid -> (area, recorte)
        self._primero: dict = {}     # sid -> primer frame en que se vio
        self._ultimo: dict = {}      # sid -> ultimo frame en que se vio
        self._publicadas: set = set()

    def registrar(self, sid: int, frame_num: int, frame_bgr: np.ndarray, box) -> None:
        """Llamar por cada persona detectada en cada frame: se conserva el mejor recorte visto hasta ahora."""
        self._primero.setdefault(sid, frame_num)
        self._ultimo[sid] = frame_num
        if sid in self._publicadas:
            return
        h, w = frame_bgr.shape[:2]
        if tocando_borde(box, w, h):
            return
        area = (box[2] - box[0]) * (box[3] - box[1])
        previo = self._mejor.get(sid)
        if previo is not None and area <= previo[0]:
            return
        recorte = recortar_persona(frame_bgr, box)
        if recorte is not None:
            self._mejor[sid] = (area, recorte)

    def publicar_pendientes(self, sid_a_persona_db_id: dict, frame_num: int) -> int:
        """Sube la foto de quienes ya estuvieron 'min_seg' en camara y todavia no la tienen; a quienes se fueron
        sin llegar a ese tiempo les libera lo guardado en memoria. Devuelve cuantas subidas lanzo."""
        lanzadas = 0
        for sid, (_, recorte) in list(self._mejor.items()):
            visto = self._ultimo.get(sid, frame_num) - self._primero.get(sid, frame_num)
            if visto < self.min_frames:
                if frame_num - self._ultimo.get(sid, frame_num) > self.min_frames:
                    self.olvidar(sid)           # se fue antes del minimo: no hace falta su foto
                continue
            persona_db_id = sid_a_persona_db_id.get(sid)
            if persona_db_id is None:
                continue
            jpg = a_jpg(recorte)
            self._publicadas.add(sid)
            self._mejor.pop(sid, None)
            if jpg:
                threading.Thread(target=publicar_foto, args=(self.storage, self.database_url, persona_db_id, jpg),
                                 daemon=True).start()
                lanzadas += 1
        return lanzadas

    def olvidar(self, sid: int) -> None:
        """Libera lo guardado en memoria de 'sid'."""
        self._mejor.pop(sid, None)
        self._primero.pop(sid, None)
        self._ultimo.pop(sid, None)

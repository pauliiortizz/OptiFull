"""Evidencia de las alertas de posible hurto: frames clave + clip corto del momento detectado.

En vivo (RTSP) no hay un archivo de video del cual recortar un clip, asi que el pipeline guarda en memoria los
ultimos segundos de imagenes (GrabadorEvidencia) y, cuando una visita termina clasificada como POSIBLE_HURTO,
arma la evidencia con lo que paso alrededor de DOS momentos:

  1. cuando la persona TOMO el producto: unos segundos antes y despues (se reserva en el momento en que se
     confirma tomo_producto, porque cuando la visita termina ese instante puede ya haber salido del buffer);
  2. cuando SE RETIRO sin pasar por caja: los ultimos segundos en que aparecio en camara.

Cada frame sale con la persona marcada (recuadro rojo) y un rotulo con la camara, la hora y el motivo. La subida
a Storage y el armado del clip (ffmpeg) se hacen en un hilo aparte (publicar_evidencia) para no frenar el analisis.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unicodedata
from collections import deque
from typing import Optional

import cv2
import numpy as np


def _ascii(texto: str) -> str:
    """Los rotulos dibujados con cv2.putText no soportan tildes ni enie: se pasan a ASCII."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


class _Entrada:
    __slots__ = ("frame", "dt", "jpg", "cajas")

    def __init__(self, frame: int, dt, jpg: bytes, cajas: dict) -> None:
        self.frame, self.dt, self.jpg, self.cajas = frame, dt, jpg, cajas


class GrabadorEvidencia:
    def __init__(self, fps: float, camara_id: int, buffer_seg: float = 120, pre_seg: float = 6,
                 post_seg: float = 6, salida_seg: float = 10, frames_clave: int = 8,
                 calidad_jpg: int = 85) -> None:
        self.fps = fps
        self.camara_id = camara_id
        self.pre_n = max(1, round(pre_seg * fps))
        self.post_n = max(1, round(post_seg * fps))
        self.salida_n = max(1, round(salida_seg * fps))
        self.frames_clave = frames_clave
        self.calidad_jpg = calidad_jpg
        self._ring: deque = deque(maxlen=max(1, round(buffer_seg * fps)))
        self._tomas: dict = {}      # sid -> {'frame', 'pre': [...], 'post': [...]}

    # ── captura continua ──────────────────────────────────────────────────────────────────────────
    def registrar_frame(self, frame_num: int, dt, frame_bgr: np.ndarray, detecciones: list) -> None:
        """Guarda el frame (comprimido a JPEG) con las cajas de las personas detectadas en el, y lo suma a
        la captura de quienes ya tomaron un producto y siguen esperando sus frames posteriores."""
        ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, self.calidad_jpg])
        if not ok:
            return
        entrada = _Entrada(frame_num, dt, buf.tobytes(), {d["sid"]: tuple(d["box"]) for d in detecciones})
        self._ring.append(entrada)
        for toma in self._tomas.values():
            if len(toma["post"]) < self.post_n:
                toma["post"].append(entrada)

    def tiene_toma(self, sid: int) -> bool:
        return sid in self._tomas

    def marcar_toma(self, sid: int, frame_num: int) -> None:
        """La persona 'sid' acaba de confirmar que tomo un producto: se reservan los frames de unos segundos
        antes (ya estan en el buffer) y se empiezan a juntar los de unos segundos despues."""
        if sid in self._tomas:
            return
        pre = [e for e in self._ring if frame_num - self.pre_n <= e.frame <= frame_num]
        self._tomas[sid] = {"frame": frame_num, "pre": pre, "post": []}

    def liberar(self, sid: int) -> None:
        """La visita de 'sid' termino sin ser sospechosa (o ya se uso su evidencia): se descarta lo reservado."""
        self._tomas.pop(sid, None)

    # ── armado de la evidencia ────────────────────────────────────────────────────────────────────
    def construir(self, sid: int, frame_fin: int) -> Optional[dict]:
        """Evidencia de la visita de 'sid' que termino en 'frame_fin': {'frames': [...], 'clip_jpgs': [...]}
        o None si no hay ninguna imagen disponible. 'frames' son los frames clave (con 'jpg', 'etiqueta' con
        tildes para la pantalla, 'ts' ISO y 'frame'); 'clip_jpgs', todos los frames del clip en orden."""
        toma = self._tomas.pop(sid, None)
        salida = [e for e in self._ring if sid in e.cajas and e.frame <= frame_fin][-self.salida_n:]
        entradas: dict = {}
        etiqueta_de: dict = {}
        if toma:
            for e in toma["pre"]:
                entradas[e.frame] = e
                etiqueta_de[e.frame] = "Se acerca al producto"
            for e in toma["post"]:
                entradas[e.frame] = e
                etiqueta_de[e.frame] = "Se aleja con el producto"
            if toma["frame"] in entradas:
                etiqueta_de[toma["frame"]] = "Toma el producto"
        for e in salida:
            entradas.setdefault(e.frame, e)
            etiqueta_de.setdefault(e.frame, "Se retira sin pasar por caja")
        if not entradas:
            return None
        orden = sorted(entradas)

        # frames clave: repartidos en todo el recorrido, forzando el de la toma y el ultimo
        clave = set(orden[:: max(1, len(orden) // max(1, self.frames_clave))][: self.frames_clave])
        if toma and toma["frame"] in entradas:
            clave.add(toma["frame"])
        clave.add(orden[-1])
        clave.add(orden[0])
        clave = sorted(clave)

        anotadas = {n: self._anotar(entradas[n], sid, etiqueta_de[n]) for n in orden}
        return {
            "frames": [{
                "jpg": anotadas[n], "etiqueta": etiqueta_de[n],
                "ts": entradas[n].dt.isoformat(), "frame": n,
            } for n in clave],
            "clip_jpgs": [anotadas[n] for n in orden],
        }

    def _anotar(self, e: _Entrada, sid: int, etiqueta: str) -> bytes:
        """Frame con la persona marcada y un rotulo (camara, hora, persona, motivo) en la parte superior."""
        img = cv2.imdecode(np.frombuffer(e.jpg, np.uint8), cv2.IMREAD_COLOR)
        caja = e.cajas.get(sid)
        if caja is not None:
            x1, y1, x2, y2 = map(int, caja)
            cv2.rectangle(img, (x1, y1), (x2, y2), (40, 40, 230), 2)
        h, w = img.shape[:2]
        escala = max(0.4, w / 1280 * 1.1)
        barra = int(26 * escala * 1.5)
        sobre = img.copy()
        cv2.rectangle(sobre, (0, 0), (w, barra), (0, 0, 0), -1)
        img = cv2.addWeighted(sobre, 0.55, img, 0.45, 0)
        texto = _ascii(f"CAM {self.camara_id}  {e.dt:%d/%m/%Y %H:%M:%S}  Persona #{sid}  |  {etiqueta}")
        cv2.putText(img, texto, (8, int(barra * 0.7)), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * escala,
                    (255, 255, 255), 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return buf.tobytes()


# ── publicacion (hilo aparte) ────────────────────────────────────────────────────────────────────────

CARPETA_LOCAL = "evidencias"   # respaldo si Storage falla (ignorada por git); el backend la sirve en /api/evidencias/


def armar_clip_mp4(jpgs: list, fps: float = 3.0, ancho: int = 960) -> Optional[bytes]:
    """MP4 (H.264, reproducible en el navegador) a partir de una lista de frames JPEG, via ffmpeg. None si no
    hay ffmpeg o falla el armado -- la alerta igual se muestra con sus frames."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not jpgs:
        return None
    with tempfile.TemporaryDirectory() as carpeta:
        salida = os.path.join(carpeta, "clip.mp4")
        for codec in ("libx264", "mpeg4"):
            try:
                r = subprocess.run(
                    [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(fps),
                     "-i", "-", "-vf", f"scale={ancho}:-2:flags=lanczos", "-c:v", codec, "-pix_fmt", "yuv420p",
                     "-movflags", "+faststart", salida],
                    input=b"".join(jpgs), capture_output=True, timeout=90)
            except (subprocess.TimeoutExpired, OSError):
                return None
            if r.returncode == 0 and os.path.isfile(salida):
                with open(salida, "rb") as f:
                    return f.read()
    return None


def _guardar(storage, ruta: str, contenido: bytes, content_type: str) -> str:
    """Sube a Supabase Storage (con un reintento); si no se puede, lo guarda en CARPETA_LOCAL. Devuelve la
    URL publica o la ruta relativa local (el backend sirve las rutas locales bajo /api/evidencias/)."""
    url = storage.subir(ruta, contenido, content_type)
    if not url and storage.enabled:
        url = storage.subir(ruta, contenido, content_type)
    if url:
        return url
    destino = os.path.join(CARPETA_LOCAL, *ruta.split("/")[1:])
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "wb") as f:
        f.write(contenido)
    return "/".join(ruta.split("/")[1:])


def publicar_evidencia(storage, database_url: str, alerta_id: int, evidencia: dict, clip_fps: float = 3.0) -> Optional[dict]:
    """Sube los frames y el clip de la alerta 'alerta_id' y deja el resultado en alertas.evidencia (JSON). Pensada
    para correr en un hilo aparte: usa su PROPIA conexion a la BD (la del analisis no es segura entre hilos)."""
    import psycopg2
    try:
        carpeta = f"evidencias/alerta_{alerta_id}"
        frames = [{
            "url":      _guardar(storage, f"{carpeta}/frame_{i + 1:02d}.jpg", f["jpg"], "image/jpeg"),
            "etiqueta": f["etiqueta"], "ts": f["ts"],
        } for i, f in enumerate(evidencia["frames"])]
        clip = armar_clip_mp4(evidencia["clip_jpgs"], clip_fps)
        video = _guardar(storage, f"{carpeta}/clip.mp4", clip, "video/mp4") if clip else None
        resultado = {"video": video, "frames": frames}
        conn = psycopg2.connect(database_url)
        try:
            cur = conn.cursor()
            cur.execute("UPDATE alertas SET evidencia = %s::jsonb WHERE id = %s",
                        (json.dumps(resultado, ensure_ascii=False), alerta_id))
            conn.commit()
            cur.close()
        finally:
            conn.close()
        print(f"[Evidencia] Alerta #{alerta_id}: {len(frames)} frames" + (" + clip" if video else " (sin clip)") + " guardados.")
        return resultado
    except Exception as error:
        print(f"[Evidencia] No se pudo guardar la evidencia de la alerta #{alerta_id}: {error}")
        return None

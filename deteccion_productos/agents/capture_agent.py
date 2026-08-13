"""
CaptureAgent
------------
Obtiene frames del video, ya sea de un archivo (pruebas) o cámara
en vivo (producción). El único cambio entre esos modos es el 'source'.
"""

import cv2


class CaptureAgent:
    def __init__(self, source, target_fps=5):
        """
        source:     path a video, URL RTSP, o índice de webcam
        target_fps: cuántos fps procesar. Como el MotionAgent hace
                    filtrado adicional, alcanza con 3-5 fps para caja.
        """
        self.source = source
        self.target_fps = target_fps
        self.cap = None
        self.frame_skip = 1
        self.source_fps = 25.0

    def start(self):
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            raise RuntimeError(f"No se pudo abrir la fuente: {self.source}")
        self.source_fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.frame_skip = max(int(self.source_fps / self.target_fps), 1)
        print(f"[CaptureAgent] Fuente: {self.source} "
              f"(procesando 1 de cada {self.frame_skip} frames)")

    def frames(self):
        if self.cap is None:
            self.start()
        idx = 0
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break
            if idx % self.frame_skip == 0:
                # Timestamp en TIEMPO DE VIDEO (posición del frame / fps),
                # no reloj de PC: así medir "cuánto estuvo quieta la
                # escena" es correcto tanto con un archivo procesado a
                # toda velocidad como con una cámara en vivo.
                yield frame, idx / self.source_fps
            idx += 1

    def release(self):
        if self.cap is not None:
            self.cap.release()

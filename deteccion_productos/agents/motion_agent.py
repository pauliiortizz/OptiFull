"""
MotionAgent
-----------
Decide CUANDO hay que llamar al LLM para identificar un producto.

Diseño: dos señales independientes que tienen que darse SIMULTANEAMENTE:

  Señal 1 - ESTABILIDAD:
    Los últimos N frames son parecidos entre sí -> la cajera dejó de
    mover el producto (o no hay nada moviéndose).

  Señal 2 - ESCENA NUEVA:
    El frame actual es distinto del último frame que YA enviamos a
    identificar -> es un producto nuevo, no el mismo que ya vimos.

  Si estable Y escena_nueva -> ANALIZAR (una única vez).
  Si estable pero misma escena -> ignorar (mismo producto).
  Si no estable -> esperar.

No hay cooldown por tiempo. El sistema se activa al ritmo REAL de la
cajera. Si es rápida (1 producto por segundo), analiza rápido. Si es
lenta (30 segundos por producto), espera 30 segundos. Se adapta.

Uso:
    motion = MotionAgent()
    for frame, ts in capture.frames():
        if motion.deberia_analizar(frame):
            resultado = vision.analizar(frame)
            motion.marcar_analizado(frame)
            # ... procesar resultado
"""

from collections import deque
import cv2
import numpy as np

from config import FRAMES_PARA_ESTABLE, UMBRAL_ESTABILIDAD, UMBRAL_ESCENA_NUEVA


class MotionAgent:
    def __init__(self, roi=None):
        """
        roi: (x1, y1, x2, y2) para limitar el análisis a una región
             del frame. En producción con celular fijo, definir un
             ROI que cubra la zona donde la cajera muestra los
             productos mejora la precisión (ignora el fondo).
        """
        self.roi = roi
        self.frames_recientes = deque(maxlen=FRAMES_PARA_ESTABLE)
        self.gris_ultimo_analizado = None  # grayscale del último frame analizado

    def _extraer_roi(self, frame):
        if self.roi is None:
            return frame
        x1, y1, x2, y2 = self.roi
        return frame[y1:y2, x1:x2]

    def _a_gris(self, frame):
        """
        Convertir a gris + suavizar. El blur reduce el impacto de
        ruido del sensor y pequeños cambios de luz.
        """
        gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gris = cv2.GaussianBlur(gris, (5, 5), 0)
        return gris

    def _diff_media(self, gris_a, gris_b):
        """Diferencia media absoluta entre dos frames en gris (0-255)."""
        return float(np.mean(cv2.absdiff(gris_a, gris_b)))

    def _esta_estable(self):
        """
        Los últimos N frames son parecidos entre sí.
        Compara cada par consecutivo y toma el MÁXIMO diff: si algún
        par tiene mucho movimiento, no está estable (aunque el
        promedio parezca bajo).
        """
        if len(self.frames_recientes) < FRAMES_PARA_ESTABLE:
            return False
        diffs = []
        for i in range(1, len(self.frames_recientes)):
            diffs.append(self._diff_media(
                self.frames_recientes[i - 1],
                self.frames_recientes[i],
            ))
        return max(diffs) < UMBRAL_ESTABILIDAD

    def _es_escena_nueva(self, gris_actual):
        """
        La escena actual es distinta del último frame que analizamos.
        Si no hay último frame (primer análisis del programa), toda
        escena estable cuenta como "nueva".
        """
        if self.gris_ultimo_analizado is None:
            return True
        diff = self._diff_media(gris_actual, self.gris_ultimo_analizado)
        return diff > UMBRAL_ESCENA_NUEVA

    def deberia_analizar(self, frame):
        """
        Devuelve True si es un buen momento para llamar al LLM:
        escena estable + distinta a la última que analizamos.
        """
        region = self._extraer_roi(frame)
        gris = self._a_gris(region)
        self.frames_recientes.append(gris)

        if not self._esta_estable():
            return False
        if not self._es_escena_nueva(gris):
            return False
        return True

    def marcar_analizado(self, frame):
        """
        El orquestador llama esto DESPUES de haber analizado un frame,
        para que ese frame sea la nueva referencia de 'último visto'.

        Se llama sin importar el resultado del análisis (aunque el LLM
        haya dicho 'no producto detectado'): así, si la escena no
        cambia, no volvemos a re-analizar la misma imagen inútilmente.
        """
        region = self._extraer_roi(frame)
        self.gris_ultimo_analizado = self._a_gris(region)

"""
MotionAgent
-----------
Decide CUANDO hay que llamar al LLM para identificar un producto.

Diseño: dos señales independientes que tienen que darse SIMULTANEAMENTE:

  Señal 1 - ESTABILIDAD:
    La escena estuvo QUIETA durante los últimos ESTABLE_MS
    milisegundos -> la cajera dejó de mover el producto (o no hay
    nada moviéndose). Se mide en TIEMPO, no en cantidad de frames:
    la velocidad de cambio de imagen (intensidad/segundo) se mantuvo
    por debajo de UMBRAL_VELOCIDAD durante toda esa ventana.

  Señal 2 - ESCENA NUEVA:
    El frame actual es distinto del último frame que YA enviamos a
    identificar -> es un producto nuevo, no el mismo que ya vimos.

  Si estable Y escena_nueva -> ANALIZAR (una única vez).
  Si estable pero misma escena -> ignorar (mismo producto).
  Si no estable -> esperar.

No hay cooldown por tiempo, y la estabilidad se mide por TIEMPO y
VELOCIDAD (no por cantidad de frames). Por eso el mismo umbral se
adapta solo a cualquier velocidad de cajera y a cualquier TARGET_FPS:
una cajera lenta (pausa larga) y una rápida (pausa corta pero real)
disparan con la misma config, sin retocar nada. El único requisito es
muestrear (TARGET_FPS) lo bastante fino como para "ver" la pausa más
corta que se quiera detectar.

Uso:
    motion = MotionAgent()
    for frame, ts in capture.frames():
        if motion.deberia_analizar(frame, ts):
            resultado = vision.analizar(frame)
            motion.marcar_analizado(frame)
            # ... procesar resultado
"""

from collections import deque
import time

import cv2
import numpy as np

from config import ESTABLE_MS, UMBRAL_VELOCIDAD, UMBRAL_ESCENA_NUEVA


class MotionAgent:
    def __init__(self, roi=None):
        """
        roi: (x1, y1, x2, y2) para limitar el análisis a una región
             del frame. En producción con celular fijo, definir un
             ROI que cubra la zona donde la cajera muestra los
             productos mejora la precisión (ignora el fondo).
        """
        self.roi = roi
        # (gris, ts) de los frames dentro de la ventana de estabilidad.
        self.frames_recientes = deque()
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

    def _esta_estable(self, ts):
        """
        La escena estuvo quieta durante los últimos ESTABLE_MS.
        Para cada par consecutivo dentro de la ventana calcula la
        VELOCIDAD de cambio (diff / segundos transcurridos) y toma el
        MÁXIMO: si en algún tramo hubo mucho movimiento, no está
        estable (aunque el promedio parezca bajo). Además exige que la
        ventana cubra realmente ESTABLE_MS de historia, para no
        disparar apenas arranca con uno o dos frames.
        """
        ventana_s = ESTABLE_MS / 1000.0
        if len(self.frames_recientes) < 2:
            return False
        # ¿Tenemos al menos ESTABLE_MS de historia continua?
        span = ts - self.frames_recientes[0][1]
        if span < ventana_s:
            return False
        max_vel = 0.0
        for i in range(1, len(self.frames_recientes)):
            gris_a, t_a = self.frames_recientes[i - 1]
            gris_b, t_b = self.frames_recientes[i]
            dt = t_b - t_a
            if dt <= 0:
                continue
            vel = self._diff_media(gris_a, gris_b) / dt
            if vel > max_vel:
                max_vel = vel
        return max_vel < UMBRAL_VELOCIDAD

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

    def deberia_analizar(self, frame, ts=None):
        """
        Devuelve True si es un buen momento para llamar al LLM:
        escena estable + distinta a la última que analizamos.

        ts: tiempo (en segundos) del frame. Con archivo de video es el
            tiempo de video (posición/fps); con cámara en vivo puede
            ser el reloj. Si no se pasa, se usa el reloj de la PC.
        """
        if ts is None:
            ts = time.time()
        region = self._extraer_roi(frame)
        gris = self._a_gris(region)
        self.frames_recientes.append((gris, ts))

        # Descartar frames que quedaron fuera de la ventana ESTABLE_MS,
        # dejando siempre uno justo antes del borde para cubrirla entera.
        ventana_s = ESTABLE_MS / 1000.0
        while (len(self.frames_recientes) > 2
               and ts - self.frames_recientes[1][1] >= ventana_s):
            self.frames_recientes.popleft()

        if not self._esta_estable(ts):
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

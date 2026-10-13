"""
CaptureAgent
------------
Obtiene frames del video, ya sea de un archivo (pruebas) o cámara
en vivo (producción). El único cambio entre esos modos es el 'source'.

Con cámara en vivo (URL del celular o índice de webcam) hay dos
diferencias con el archivo:

  - Un hilo en segundo plano lee la cámara todo el tiempo y guarda SOLO
    el frame más reciente. Mientras el programa espera al LLM (~1.5s) o
    a que la cajera confirme, los frames viejos se descartan en vez de
    acumularse: al volver, se analiza lo que el celular ve AHORA y no lo
    que veía hace varios segundos.
  - Si la conexión falla (Wi-Fi inestable), se reintenta abrirla varias
    veces antes de rendirse, tanto al arrancar como si se corta en medio.
"""

import os
import threading
import time

import cv2

# Intentos para abrir la cámara (al arrancar y si se corta en medio) y
# tiempo máximo de espera de red por intento. Sin el timeout, OpenCV
# puede quedarse ~30s colgado esperando a un celular que no responde.
INTENTOS_CONEXION = 4
ESPERA_ENTRE_INTENTOS_SEG = 2.0
TIMEOUT_RED_MS = 5000


def _es_en_vivo(source):
    """Cámara en vivo = URL de red o índice de webcam (no un archivo)."""
    if isinstance(source, int) or str(source).isdigit():
        return True
    return "://" in str(source) and not os.path.exists(str(source))


def _sin_credenciales(source):
    """La URL del celular lleva usuario:clave -- no imprimirla tal cual."""
    s = str(source)
    if "://" in s and "@" in s:
        esquema, resto = s.split("://", 1)
        return f"{esquema}://{resto.split('@', 1)[1]}"
    return s


class CaptureAgent:
    def __init__(self, source, target_fps=5):
        """
        source:     path a video, URL RTSP/HTTP, o índice de webcam
        target_fps: cuántos fps procesar. Como el MotionAgent hace
                    filtrado adicional, alcanza con 3-5 fps para caja.
        """
        self.source = int(source) if str(source).isdigit() else source
        self.target_fps = target_fps
        self.en_vivo = _es_en_vivo(source)
        self.cap = None
        self.frame_skip = 1
        self.source_fps = 25.0

        # Solo en vivo: hilo lector + último frame
        self._thread = None
        self._detener = threading.Event()
        self._frame_nuevo = threading.Event()
        self._lock = threading.Lock()
        self._ultimo_frame = None
        self._camara_perdida = False

    def _abrir_cap(self):
        if self.en_vivo and isinstance(self.source, str):
            try:
                return cv2.VideoCapture(self.source, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, TIMEOUT_RED_MS,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, TIMEOUT_RED_MS,
                ])
            except Exception:
                pass  # OpenCV sin soporte de esos parámetros
        return cv2.VideoCapture(self.source)

    def _conectar(self):
        """Abre la fuente, reintentando si es una cámara en vivo.
        Devuelve True si quedó abierta."""
        intentos = INTENTOS_CONEXION if self.en_vivo else 1
        for intento in range(1, intentos + 1):
            if self.cap is not None:
                self.cap.release()
            t0 = time.perf_counter()
            self.cap = self._abrir_cap()
            if self.cap.isOpened():
                if self.en_vivo:
                    print(f"[CaptureAgent] Conectado en "
                          f"{time.perf_counter() - t0:.1f}s (intento {intento})")
                return True
            if intento < intentos and not self._detener.is_set():
                print(f"[CaptureAgent] No se pudo conectar (intento "
                      f"{intento}/{intentos}), reintentando en "
                      f"{ESPERA_ENTRE_INTENTOS_SEG:.0f}s...")
                time.sleep(ESPERA_ENTRE_INTENTOS_SEG)
        return False

    def start(self):
        if not self._conectar():
            raise RuntimeError(
                f"No se pudo abrir la fuente: {_sin_credenciales(self.source)}")
        self.source_fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        ancho = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if self.en_vivo:
            print(f"[CaptureAgent] Fuente en vivo: {_sin_credenciales(self.source)} "
                  f"({ancho}x{alto} a {self.source_fps:.0f} fps, "
                  f"analizando siempre el último frame, hasta {self.target_fps} por segundo)")
            self._thread = threading.Thread(target=self._leer_en_vivo, daemon=True)
            self._thread.start()
        else:
            self.frame_skip = max(int(self.source_fps / self.target_fps), 1)
            print(f"[CaptureAgent] Fuente: {self.source} "
                  f"({ancho}x{alto} a {self.source_fps:.0f} fps, "
                  f"procesando 1 de cada {self.frame_skip} frames)")

    def _leer_en_vivo(self):
        """Hilo: lee la cámara sin parar y pisa siempre el mismo lugar con
        el frame más reciente. Si la cámara se corta, intenta reconectar."""
        while not self._detener.is_set():
            ret, frame = self.cap.read()
            if ret:
                with self._lock:
                    self._ultimo_frame = frame
                    self._frame_nuevo.set()
                continue
            if self._detener.is_set():
                break
            print("[CaptureAgent] Se cortó la cámara, reconectando...")
            if not self._conectar():
                print("[CaptureAgent] No se pudo reconectar la cámara.")
                self._camara_perdida = True
                self._frame_nuevo.set()  # despertar a frames() para que termine
                break

    def frames(self):
        if self.cap is None:
            self.start()
        if self.en_vivo:
            yield from self._frames_en_vivo()
            return
        idx = 0
        while True:
            ret, frame = self.cap.read()
            if not ret:
                break
            if idx % self.frame_skip == 0:
                # Timestamp en TIEMPO DE VIDEO (posición del frame / fps),
                # no reloj de PC: así medir "cuánto estuvo quieta la
                # escena" es correcto aunque el archivo se procese a
                # toda velocidad.
                yield frame, idx / self.source_fps
            idx += 1

    def _frames_en_vivo(self):
        """Entrega el último frame disponible, nunca el mismo dos veces y
        a lo sumo target_fps por segundo. El timestamp es reloj real: acá
        se saltean frames a propósito, así que contar frames no sirve."""
        t_inicio = time.monotonic()
        intervalo = 1.0 / self.target_fps
        proximo = 0.0
        while not self._detener.is_set():
            if not self._frame_nuevo.wait(timeout=1.0):
                continue
            if self._camara_perdida:
                break
            ahora = time.monotonic()
            if ahora < proximo:
                time.sleep(proximo - ahora)
            with self._lock:
                frame = self._ultimo_frame
                self._frame_nuevo.clear()
            proximo = time.monotonic() + intervalo
            yield frame, time.monotonic() - t_inicio

    def release(self):
        self._detener.set()
        if self._thread is not None:
            # No liberar la cámara mientras el hilo sigue adentro de read()
            self._thread.join(timeout=TIMEOUT_RED_MS / 1000 + 1)
        if self.cap is not None:
            self.cap.release()

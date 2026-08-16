"""Fuentes de video intercambiables para el pipeline de deteccion. El resto
del pipeline (deteccion/main.py) solo conoce esta interfaz -- no le importa
si el frame vino de un archivo (analisis offline, fin conocido) o de una
camara en vivo (webcam local hoy; a futuro cualquier URL de streaming que
cv2.VideoCapture sepa abrir, ej. un iPhone corriendo una app de IP-camera --
ver WebcamVideoSource, pensada para que una futura IphoneVideoSource
reutilice el mismo hilo de captura sin duplicar nada)."""
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple

import cv2
import numpy as np


class VideoSource(ABC):
    """Interfaz comun a toda fuente de frames. 'total_frames' es None
    cuando la fuente no tiene un fin conocido (camara en vivo) -- el codigo
    que calcula 'frames_a_procesar = total_frames // frame_skip' tiene que
    chequear esto antes de dividir. 'is_live' distingue una fuente donde
    perder frames atrasados es CORRECTO (camara: siempre conviene el mas
    reciente) de una donde hay que leer todo en orden (archivo: cada frame
    de un video ya grabado cuenta para el analisis offline)."""

    fps: float
    frame_w: int
    frame_h: int
    total_frames: Optional[int]
    is_live: bool

    @abstractmethod
    def open(self) -> None:
        """Abre la fuente y deja fps/frame_w/frame_h/total_frames listos.
        Lanza RuntimeError con un mensaje claro si la fuente no se pudo
        abrir."""

    @abstractmethod
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Devuelve (True, frame) si hay un frame disponible, o
        (False, None) si la fuente termino (archivo) o dejo de responder
        (camara -- ver WebcamVideoSource.error())."""

    @abstractmethod
    def release(self) -> None:
        """Libera la fuente. Debe poder llamarse mas de una vez sin error
        (ej. una vez al cortar con 'q' y otra vez en el finally)."""


class FileVideoSource(VideoSource):
    """Envuelve un archivo de video. Mismo comportamiento que el
    cv2.VideoCapture(config.VIDEO_PATH) que deteccion/main.py usaba directo
    antes de esta refactorizacion."""

    is_live = False

    def __init__(self, path: str) -> None:
        self.path = path
        self.cap: Optional[cv2.VideoCapture] = None
        self.fps = 0.0
        self.frame_w = 0
        self.frame_h = 0
        self.total_frames: Optional[int] = None

    def open(self) -> None:
        self.cap = cv2.VideoCapture(self.path)
        if not self.cap.isOpened():
            raise RuntimeError(f"No se pudo abrir el archivo de video: '{self.path}'")
        self.fps           = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.frame_w        = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h        = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames   = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.cap is None:
            return False, None
        return self.cap.read()

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class WebcamVideoSource(VideoSource):
    """Camara en vivo (webcam local por indice de dispositivo, o cualquier
    URL que cv2.VideoCapture sepa abrir -- streaming HTTP/RTSP incluido, lo
    que deja listo el camino para un iPhone corriendo una app de IP-camera
    mas adelante sin escribir una clase nueva de threading).

    Un hilo de captura en background lee continuamente y sobreescribe
    SIEMPRE un unico slot con el frame mas reciente (protegido por lock,
    nunca una cola/Queue): si la inferencia es mas lenta que la camara, los
    frames viejos se descartan solos en vez de acumularse -- ver read()."""

    is_live = True
    total_frames = None

    def __init__(
        self,
        device=0,
        resolution: Optional[Tuple[int, int]] = None,
        target_fps: Optional[float] = None,
        max_intentos_lectura: int = 30,
        timeout_primer_frame_seg: float = 5.0,
    ) -> None:
        self.device = device
        self.resolution = resolution
        self.target_fps = target_fps
        self.max_intentos_lectura = max_intentos_lectura
        self.timeout_primer_frame_seg = timeout_primer_frame_seg

        self.cap: Optional[cv2.VideoCapture] = None
        self.fps = 0.0
        self.frame_w = 0
        self.frame_h = 0

        self._thread: Optional[threading.Thread] = None
        self._detener = threading.Event()
        self._frame_listo = threading.Event()
        self._lock = threading.Lock()
        self._ultimo_frame: Optional[np.ndarray] = None
        self._error: Optional[str] = None

    def open(self) -> None:
        self.cap = cv2.VideoCapture(self.device)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"No se pudo abrir la camara '{self.device}'. Verifica que "
                f"este conectada, que no la este usando otra aplicacion, y "
                f"que se le hayan dado permisos de camara."
            )
        if self.resolution:
            w, h = self.resolution
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if self.target_fps:
            self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)

        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps     = self.cap.get(cv2.CAP_PROP_FPS) or 30

        self._detener.clear()
        self._frame_listo.clear()
        self._error = None
        self._thread = threading.Thread(target=self._loop_captura, daemon=True)
        self._thread.start()

        if not self._frame_listo.wait(timeout=self.timeout_primer_frame_seg):
            self.release()
            raise RuntimeError(
                f"La camara '{self.device}' no entrego ningun frame en "
                f"{self.timeout_primer_frame_seg:.0f}s."
            )
        if self._error:
            error, self._error = self._error, None
            self.release()
            raise RuntimeError(error)

    def _loop_captura(self) -> None:
        intentos_fallidos = 0
        while not self._detener.is_set():
            ok, frame = self.cap.read()
            if not ok:
                intentos_fallidos += 1
                if intentos_fallidos >= self.max_intentos_lectura:
                    self._error = (
                        f"La camara '{self.device}' dejo de responder "
                        f"({intentos_fallidos} lecturas fallidas seguidas)."
                    )
                    self._frame_listo.set()  # despierta a open() si seguia esperando el primer frame
                    return
                time.sleep(0.05)
                continue
            intentos_fallidos = 0
            with self._lock:
                self._ultimo_frame = frame
            self._frame_listo.set()

    def read(self, timeout: float = 1.0) -> Tuple[bool, Optional[np.ndarray]]:
        """A diferencia de FileVideoSource.read(), esta version espera (con
        timeout) a que el hilo de captura guarde un frame NUEVO desde la
        ultima vez que se leyo -- evita que el loop principal reprocese el
        mismo frame en bucle apretado si la inferencia es mas rapida que la
        camara. Si se cumple el timeout sin frame nuevo, igual devuelve el
        ultimo disponible (o (False, None) si todavia no llego ninguno)."""
        frame_es_nuevo = self._frame_listo.wait(timeout=timeout)
        with self._lock:
            frame = self._ultimo_frame
            if frame_es_nuevo:
                self._frame_listo.clear()
        if frame is None:
            return False, None
        return True, frame

    def error(self) -> Optional[str]:
        """Motivo por el que la camara dejo de entregar frames, o None si
        sigue funcionando bien. El loop principal en main.py lo consulta en
        cada iteracion para distinguir un corte real de la camara de la
        operacion normal."""
        return self._error

    def release(self) -> None:
        self._detener.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None

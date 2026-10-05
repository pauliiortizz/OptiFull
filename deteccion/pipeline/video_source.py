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
        etiqueta: Optional[str] = None,
        reconectar_hasta_seg: float = 0.0,
        descartar_repetidos: bool = False,
        timeout_lectura_ms: Optional[int] = None,
    ) -> None:
        # reconectar_hasta_seg > 0: si el stream deja de entregar frames se reabre la conexion (con
        #   espera creciente entre intentos) y recien se da por muerta la camara pasado ese tiempo;
        #   0 = comportamiento original (un corte termina la lectura). Pensado para RTSP.
        # descartar_repetidos: si no hay un frame NUEVO, read() devuelve (True, None) en vez de
        #   repetir el ultimo -- sin esto, un stream trabado haria reprocesar la misma imagen.
        # timeout_lectura_ms: tiempo maximo de espera de red al abrir/leer una URL (por defecto
        #   OpenCV espera 30 s antes de rendirse).
        self.reconectar_hasta_seg = reconectar_hasta_seg
        self.descartar_repetidos = descartar_repetidos
        self.timeout_lectura_ms = timeout_lectura_ms
        self._reconectando = False
        self.device = device
        # Nombre para mensajes/logs: una URL RTSP lleva usuario:clave, asi que
        # nunca se imprime 'device' crudo si hay una etiqueta.
        self.etiqueta = etiqueta or str(device)
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

    def _abrir_cap(self) -> "cv2.VideoCapture":
        """Abre la captura; con timeout_lectura_ms (solo URLs) limita la espera de red."""
        if self.timeout_lectura_ms and isinstance(self.device, str):
            try:
                return cv2.VideoCapture(self.device, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(self.timeout_lectura_ms),
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(self.timeout_lectura_ms),
                ])
            except Exception:
                pass  # OpenCV sin soporte de esos parametros: se abre sin timeout propio
        return cv2.VideoCapture(self.device)

    def reconectando(self) -> bool:
        """True mientras el hilo de captura intenta reabrir un stream cortado."""
        return self._reconectando

    def _reconectar(self) -> bool:
        """Reabre el stream con espera creciente (2 s, 4 s ... hasta 15 s) hasta reconectar o hasta
        agotar reconectar_hasta_seg. True si volvio a entregar frames."""
        self._reconectando = True
        inicio = time.monotonic()
        espera, intento = 2.0, 0
        print(f"[RTSP] '{self.etiqueta}' sin imagen -- reconectando (hasta {self.reconectar_hasta_seg:.0f} s)...")
        try:
            while not self._detener.is_set() and time.monotonic() - inicio < self.reconectar_hasta_seg:
                intento += 1
                try:
                    if self.cap is not None:
                        self.cap.release()
                except Exception:
                    pass
                self.cap = self._abrir_cap()
                if self.cap.isOpened():
                    ok, frame = self.cap.read()
                    if ok:
                        with self._lock:
                            self._ultimo_frame = frame
                        self._frame_listo.set()
                        print(f"[RTSP] '{self.etiqueta}' reconectada tras {time.monotonic() - inicio:.0f} s "
                              f"({intento} intento{'s' if intento != 1 else ''}).")
                        return True
                if self._detener.wait(espera):
                    return False
                espera = min(espera * 2, 15.0)
            return False
        finally:
            self._reconectando = False

    def open(self) -> None:
        self.cap = self._abrir_cap()
        if not self.cap.isOpened():
            raise RuntimeError(
                f"No se pudo abrir la camara '{self.etiqueta}'. Verifica que "
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
                f"La camara '{self.etiqueta}' no entrego ningun frame en "
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
                    if self.reconectar_hasta_seg > 0 and self._reconectar():
                        intentos_fallidos = 0
                        continue
                    self._error = (
                        f"La camara '{self.etiqueta}' dejo de responder "
                        f"({intentos_fallidos} lecturas fallidas seguidas"
                        + (f" y no volvio en {self.reconectar_hasta_seg:.0f} s" if self.reconectar_hasta_seg > 0 else "")
                        + ")."
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
        if self.descartar_repetidos and not frame_es_nuevo:
            return True, None   # sin frame nuevo: no hay nada que procesar (no se repite el ultimo)
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


class ScreenVideoSource(VideoSource):
    """Captura de pantalla en vivo (para analizar, ej., una videollamada de
    Google Meet abierta en el navegador: hay que dejar la pestana/ventana de
    Meet visible en el monitor elegido ANTES de correr esto -- esta fuente no
    sabe nada de Meet, solo copia lo que haya en pantalla en esa region).

    Misma estructura de hilo de captura que WebcamVideoSource (slot unico
    sobreescrito, nunca una cola) porque mss tampoco bloquea esperando un
    frame 'nuevo': sin esto, leer en el loop principal a la velocidad de la
    inferencia (mas lenta que el refresco de pantalla) repetiria el mismo
    frame en vez de descartar los viejos."""

    is_live = True
    total_frames = None

    def __init__(
        self,
        monitor: int = 1,
        region: Optional[Tuple[int, int, int, int]] = None,
        target_fps: Optional[float] = None,
        scale: float = 1.0,
        timeout_primer_frame_seg: float = 5.0,
    ) -> None:
        # 'monitor' sigue la numeracion de mss.monitors: 0 = todos los
        # monitores combinados, 1 = el primero, 2 = el segundo, etc.
        # 'region', si se pasa, es (x, y, ancho, alto) en pixeles absolutos y
        # tiene prioridad sobre 'monitor' -- sirve para recortar solo la
        # ventana/pestana de Meet en vez de capturar el monitor entero.
        # 'scale' achica el frame capturado ANTES de entregarlo (ej. 0.5 =
        # mitad de ancho/alto) -- baja el costo de la inferencia de YOLO
        # ademas de la CPU que ya ahorra 'target_fps', sin tocar la region
        # capturada en si.
        self.monitor = monitor
        self.region = region
        self.target_fps = target_fps
        self.scale = scale
        self.timeout_primer_frame_seg = timeout_primer_frame_seg

        self._sct = None
        self._captura_area = None
        self.fps = target_fps or 15.0
        self.frame_w = 0
        self.frame_h = 0

        self._thread: Optional[threading.Thread] = None
        self._detener = threading.Event()
        self._frame_listo = threading.Event()
        self._lock = threading.Lock()
        self._ultimo_frame: Optional[np.ndarray] = None
        self._error: Optional[str] = None

    def open(self) -> None:
        import mss  # import perezoso: solo hace falta en modo --screen

        self._sct = mss.mss()
        if self.region is not None:
            x, y, w, h = self.region
            self._captura_area = {"left": x, "top": y, "width": w, "height": h}
        else:
            try:
                monitor_info = self._sct.monitors[self.monitor]
            except IndexError:
                raise RuntimeError(
                    f"No existe el monitor {self.monitor} (hay "
                    f"{len(self._sct.monitors) - 1} monitor(es) detectado(s))."
                )
            self._captura_area = monitor_info

        self.frame_w = round(self._captura_area["width"] * self.scale)
        self.frame_h = round(self._captura_area["height"] * self.scale)

        self._detener.clear()
        self._frame_listo.clear()
        self._error = None
        self._thread = threading.Thread(target=self._loop_captura, daemon=True)
        self._thread.start()

        if not self._frame_listo.wait(timeout=self.timeout_primer_frame_seg):
            self.release()
            raise RuntimeError(
                f"La captura de pantalla no entrego ningun frame en "
                f"{self.timeout_primer_frame_seg:.0f}s."
            )
        if self._error:
            error, self._error = self._error, None
            self.release()
            raise RuntimeError(error)

    def _loop_captura(self) -> None:
        import mss

        # Cada hilo necesita su propia instancia de mss.mss() -- la libreria
        # usa recursos nativos por hilo (ver docs de mss), la de open() es
        # solo para calcular self._captura_area antes de arrancar el hilo.
        with mss.mss() as sct:
            intervalo = (1.0 / self.target_fps) if self.target_fps else 0.0
            while not self._detener.is_set():
                try:
                    shot = sct.grab(self._captura_area)
                except Exception as e:
                    self._error = f"La captura de pantalla fallo: {e}"
                    self._frame_listo.set()
                    return
                # mss entrega BGRA; el pipeline (YOLO/cv2) espera BGR de 3 canales.
                frame = cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)
                if self.scale != 1.0:
                    frame = cv2.resize(frame, (self.frame_w, self.frame_h), interpolation=cv2.INTER_AREA)
                with self._lock:
                    self._ultimo_frame = frame
                self._frame_listo.set()
                if intervalo:
                    time.sleep(intervalo)

    def read(self, timeout: float = 1.0) -> Tuple[bool, Optional[np.ndarray]]:
        frame_es_nuevo = self._frame_listo.wait(timeout=timeout)
        with self._lock:
            frame = self._ultimo_frame
            if frame_es_nuevo:
                self._frame_listo.clear()
        if frame is None:
            return False, None
        return True, frame

    def error(self) -> Optional[str]:
        return self._error

    def release(self) -> None:
        self._detener.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._sct is not None:
            self._sct.close()
            self._sct = None

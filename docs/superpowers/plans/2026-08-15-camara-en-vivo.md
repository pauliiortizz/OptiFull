# Cámara en vivo (webcam) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir correr `deteccion/main.py` contra la webcam de la PC en tiempo real (`--webcam`), reutilizando el pipeline de detección/tracking/heatmap/zonas/overlay existente, sin persistir nada en la base de datos ni en Supabase Storage, y sin romper el modo archivo actual.

**Architecture:** Nueva abstracción `VideoSource` (`FileVideoSource` / `WebcamVideoSource`) que expone `open()/read()/release()` con la misma interfaz para archivo y cámara. `WebcamVideoSource` captura en un hilo de background que sobreescribe un único slot con el frame más reciente (nunca una cola). `deteccion/main.py` se refactoriza para leer de un `VideoSource` en vez de `cv2.VideoCapture` directo, con un flag `--webcam` que activa el modo en vivo; en ese modo, `camara_id`/`sesion_id` quedan en `None` y toda la sección de guardado (BD + Storage) se saltea explícitamente.

**Tech Stack:** Python, OpenCV (`cv2`, ya instalado — sin dependencias nuevas), `threading` (stdlib), `pytest` + `unittest.mock` (ya usados en el proyecto).

**Spec:** `docs/superpowers/specs/2026-08-15-camara-en-vivo-design.md`

## Global Constraints

- No se agregan dependencias nuevas — solo `opencv-python` (ya instalado) y stdlib (`threading`, `time`, `argparse`, `collections.deque`).
- El modo cámara en vivo NUNCA escribe en Postgres/Supabase ni sube nada a Supabase Storage — ver spec, sección "Modo cámara = sin persistencia". Esto se garantiza con un `if modo_camara:`/`else:` explícito en la cola de guardado de `main.py`, no solo confiando en que `Persistencia.*` sea no-op sin conexión (esa garantía NO cubre `SupabaseStorage.subir_png`).
- El modo archivo (`python deteccion/main.py` sin flags) debe quedar con comportamiento idéntico al actual — mismo `FRAME_SKIP`, misma persistencia, mismo overlay, mismos resultados.
- `WebcamVideoSource` nunca acumula una cola de frames: siempre expone el más reciente, descartando los atrasados si el consumidor es más lento que la cámara.
- Estilo del proyecto: docstrings y nombres en español, siguiendo el estilo ya presente en `deteccion/`.

---

## Task 1: `VideoSource` base + `FileVideoSource`

**Files:**
- Create: `deteccion/pipeline/video_source.py`
- Test: `test/unitarios/test_video_source.py`

**Interfaces:**
- Produces: `VideoSource` (ABC) con atributos `fps: float`, `frame_w: int`, `frame_h: int`, `total_frames: Optional[int]`, `is_live: bool`, y métodos `open() -> None`, `read() -> Tuple[bool, Optional[np.ndarray]]`, `release() -> None`.
- Produces: `FileVideoSource(path: str)` — implementación concreta, `is_live = False`.

- [ ] **Step 1: Escribir el test de `FileVideoSource` (falla porque el módulo no existe todavía)**

Crear `test/unitarios/test_video_source.py`:

```python
"""Tests unitarios de VideoSource: FileVideoSource envuelve un archivo real
(se genera uno sintetico de unos pocos frames por test, sin depender de
ningun video del repo); WebcamVideoSource se prueba con cv2.VideoCapture
mockeado (ver mas abajo) porque no hay camara real en CI."""
import os
import tempfile
import threading
import time

import cv2
import numpy as np
import pytest

from deteccion.pipeline.video_source import FileVideoSource, WebcamVideoSource


def _crear_video_sintetico(path: str, n_frames: int = 5, w: int = 64, h: int = 48, fps: float = 10.0) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (w, h))
    for i in range(n_frames):
        frame = np.full((h, w, 3), i * 10, dtype=np.uint8)
        writer.write(frame)
    writer.release()


# ── FileVideoSource ──────────────────────────────────────────────────────────

def test_file_video_source_expone_metadata_correcta(tmp_path):
    path = str(tmp_path / "sintetico.mp4")
    _crear_video_sintetico(path, n_frames=5, w=64, h=48, fps=10.0)

    source = FileVideoSource(path)
    source.open()

    assert source.is_live is False
    assert source.frame_w == 64
    assert source.frame_h == 48
    assert source.fps == pytest.approx(10.0)
    assert source.total_frames == 5

    source.release()


def test_file_video_source_lee_todos_los_frames_y_despues_corta(tmp_path):
    path = str(tmp_path / "sintetico.mp4")
    _crear_video_sintetico(path, n_frames=5)

    source = FileVideoSource(path)
    source.open()

    leidos = 0
    while True:
        ok, frame = source.read()
        if not ok:
            break
        assert frame is not None
        leidos += 1

    assert leidos == 5
    source.release()


def test_file_video_source_archivo_inexistente_lanza_error_claro():
    source = FileVideoSource("no_existe_este_archivo_12345.mp4")
    with pytest.raises(RuntimeError, match="No se pudo abrir"):
        source.open()


def test_file_video_source_release_es_seguro_llamarlo_dos_veces(tmp_path):
    path = str(tmp_path / "sintetico.mp4")
    _crear_video_sintetico(path, n_frames=2)

    source = FileVideoSource(path)
    source.open()
    source.release()
    source.release()  # no debe lanzar
```

- [ ] **Step 2: Correr el test para confirmar que falla (el módulo no existe)**

Run: `python -m pytest test/unitarios/test_video_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'deteccion.pipeline.video_source'`

- [ ] **Step 3: Implementar `VideoSource` y `FileVideoSource`**

Crear `deteccion/pipeline/video_source.py` con el siguiente contenido (el resto de las clases de este archivo, `WebcamVideoSource`, se agregan en la Tarea 2 — este paso deja solo la base y `FileVideoSource` para que el test de arriba pase):

```python
"""Fuentes de video intercambiables para el pipeline de deteccion. El resto
del pipeline (deteccion/main.py) solo conoce esta interfaz -- no le importa
si el frame vino de un archivo (analisis offline, fin conocido) o de una
camara en vivo (webcam local hoy; a futuro cualquier URL de streaming que
cv2.VideoCapture sepa abrir, ej. un iPhone corriendo una app de IP-camera --
ver WebcamVideoSource, pensada para que una futura IphoneVideoSource
reutilice el mismo hilo de captura sin duplicar nada)."""
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
```

Nota: el test de arriba importa también `WebcamVideoSource`, que todavía no existe en este paso — por eso el Step 2 de la Tarea 2 (no este) es el que hace pasar el archivo de test completo. Para validar SOLO lo de esta tarea, correr los tests de `FileVideoSource` con `-k`:

Run: `python -m pytest test/unitarios/test_video_source.py -v -k file_video_source`
Expected: FAIL igual (import error por `WebcamVideoSource` inexistente) — esto es esperado, se resuelve en la Tarea 2. Continuar directo a la Tarea 2 sin commitear todavía (el archivo de test necesita las dos clases para poder importarse).

---

## Task 2: `WebcamVideoSource` (captura en hilo, último frame siempre)

**Files:**
- Modify: `deteccion/pipeline/video_source.py`
- Modify: `test/unitarios/test_video_source.py`

**Interfaces:**
- Consumes: `VideoSource` (Task 1).
- Produces: `WebcamVideoSource(device=0, resolution=None, target_fps=None, max_intentos_lectura=30, timeout_primer_frame_seg=5.0)`, `is_live = True`, `total_frames = None`, método extra `read(timeout: float = 1.0)` y `error() -> Optional[str]`.

- [ ] **Step 1: Agregar los tests de `WebcamVideoSource` (mockeando `cv2.VideoCapture`)**

Agregar al final de `test/unitarios/test_video_source.py`:

```python
from unittest.mock import MagicMock, patch


# ── WebcamVideoSource ────────────────────────────────────────────────────────

def test_webcam_open_lanza_error_claro_si_no_se_puede_abrir():
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False

    with patch("deteccion.pipeline.video_source.cv2.VideoCapture", return_value=mock_cap):
        source = WebcamVideoSource(device=5)
        with pytest.raises(RuntimeError, match="No se pudo abrir la camara"):
            source.open()


def test_webcam_reporta_error_si_nunca_entrega_frames():
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 30.0
    mock_cap.read.return_value = (False, None)  # nunca entrega nada

    with patch("deteccion.pipeline.video_source.cv2.VideoCapture", return_value=mock_cap):
        source = WebcamVideoSource(device=0, max_intentos_lectura=3, timeout_primer_frame_seg=2.0)
        with pytest.raises(RuntimeError, match="dejo de responder"):
            source.open()


def test_webcam_read_devuelve_el_ultimo_frame_no_el_primero():
    """Prueba el requisito central: nunca se acumula una cola -- read() debe
    devolver el frame MAS RECIENTE producido, no el mas viejo. Se generan 20
    frames numerados y se verifica que, al leer una sola vez despues de que
    los 20 ya se produjeron, se obtiene el #20 (no el #1)."""
    frames_producidos = [np.full((2, 2, 3), i, dtype=np.uint8) for i in range(1, 21)]
    idx = {"i": 0}
    todos_producidos = threading.Event()

    def fake_read():
        i = idx["i"]
        if i >= len(frames_producidos):
            return False, None
        idx["i"] += 1
        if i == len(frames_producidos) - 1:
            todos_producidos.set()
        return True, frames_producidos[i]

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 30.0
    mock_cap.read.side_effect = fake_read

    with patch("deteccion.pipeline.video_source.cv2.VideoCapture", return_value=mock_cap):
        source = WebcamVideoSource(device=0, timeout_primer_frame_seg=2.0)
        source.open()
        assert todos_producidos.wait(timeout=2.0)
        time.sleep(0.05)  # deja que el hilo termine de guardar el ultimo antes de leer
        ok, frame = source.read(timeout=0.2)
        source.release()

    assert ok is True
    assert int(frame[0, 0, 0]) == 20


def test_webcam_is_live_y_total_frames_none():
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 30.0
    mock_cap.read.return_value = (True, np.zeros((2, 2, 3), dtype=np.uint8))

    with patch("deteccion.pipeline.video_source.cv2.VideoCapture", return_value=mock_cap):
        source = WebcamVideoSource(device=0, timeout_primer_frame_seg=2.0)
        source.open()
        assert source.is_live is True
        assert source.total_frames is None
        assert source.error() is None
        source.release()


def test_webcam_release_detiene_el_hilo_y_es_seguro_llamarlo_dos_veces():
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 30.0
    mock_cap.read.return_value = (True, np.zeros((2, 2, 3), dtype=np.uint8))

    with patch("deteccion.pipeline.video_source.cv2.VideoCapture", return_value=mock_cap):
        source = WebcamVideoSource(device=0, timeout_primer_frame_seg=2.0)
        source.open()
        source.release()
        source.release()  # no debe lanzar
        assert source._thread is None
```

- [ ] **Step 2: Correr los tests nuevos para confirmar que fallan**

Run: `python -m pytest test/unitarios/test_video_source.py -v`
Expected: FAIL — `ImportError: cannot import name 'WebcamVideoSource'`

- [ ] **Step 3: Implementar `WebcamVideoSource`**

Agregar a `deteccion/pipeline/video_source.py` (después de `FileVideoSource`; también agregar `import threading` e `import time` a los imports del módulo):

```python
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
```

- [ ] **Step 4: Correr todos los tests del archivo y confirmar que pasan**

Run: `python -m pytest test/unitarios/test_video_source.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Correr toda la suite de tests unitarios para confirmar que no se rompió nada**

Run: `python -m pytest test/unitarios -v`
Expected: PASS (todos, incluidos los preexistentes)

- [ ] **Step 6: Commit**

```bash
git add deteccion/pipeline/video_source.py test/unitarios/test_video_source.py
git commit -m "Agregar VideoSource/FileVideoSource/WebcamVideoSource para camara en vivo"
```

---

## Task 3: Integrar `VideoSource` en `deteccion/main.py` + flag `--webcam`

**Files:**
- Modify: `deteccion/main.py`
- Modify: `deteccion/config.py`

**Interfaces:**
- Consumes: `FileVideoSource`, `WebcamVideoSource` (Task 1 y 2) — `source.open()/read()/release()`, `source.fps/frame_w/frame_h/total_frames/is_live`, `WebcamVideoSource.error()`.

- [ ] **Step 1: Agregar la configuración de cámara en vivo a `deteccion/config.py`**

Agregar al final de `deteccion/config.py`:

```python

# ── Camara en vivo (webcam) ─────────────────────────────────────────────────
# Ver deteccion/pipeline/video_source.py:WebcamVideoSource y el flag --webcam
# de main.py. La camara en vivo usa el mismo pipeline de deteccion/tracking/
# heatmap que un video, pero NUNCA persiste en la BD ni sube nada a Supabase
# Storage (main.py corta esa seccion entera cuando modo_camara=True) -- es
# solo para validar el pipeline en vivo antes de decidir si se persiste.
WEBCAM_DEVICE_INDEX    = 0     # indice de camara por default para --webcam sin argumento
WEBCAM_RESOLUTION      = None  # (ancho, alto) o None = la resolucion default de la camara
WEBCAM_TARGET_FPS      = None  # fps pedido a la camara, o None = el que de por default
WEBCAM_USAR_REID_NUBE  = False  # False = tracking local + heatmap sin gastar cupo de Gemini/Groq/Claude
WEBCAM_CAMARA_ID_ZONAS = None  # id de camara (ver CAMARA_NOMBRES) para cargar SUS zonas en modo
                                # solo lectura -- nunca escribe (mismo patron que SOLO_LEER_ZONAS).
                                # None = corre sin zonas (heatmap/tracking igual funcionan).
```

- [ ] **Step 2: Verificar que `config.py` sigue siendo válido**

Run: `python -c "from deteccion import config; print(config.WEBCAM_DEVICE_INDEX, config.WEBCAM_USAR_REID_NUBE)"`
Expected: `0 False`

- [ ] **Step 3: Agregar imports y el parser de argumentos en `deteccion/main.py`**

Modificar el bloque de imports al principio del archivo — reemplazar:

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from datetime import datetime

import cv2
from ultralytics import YOLO
```

por:

```python
import argparse
import sys
import os
import time
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from datetime import datetime

import cv2
from ultralytics import YOLO
```

Y en el bloque de imports de `deteccion.*` — reemplazar:

```python
from deteccion.pipeline.tracking import PersonTracker
from deteccion.pipeline.heatmap import (
    HeatmapBuilder, combinar_grids, calcular_stats_grid, codificar_combinado,
)
```

por:

```python
from deteccion.pipeline.tracking import PersonTracker
from deteccion.pipeline.video_source import FileVideoSource, WebcamVideoSource
from deteccion.pipeline.heatmap import (
    HeatmapBuilder, combinar_grids, calcular_stats_grid, codificar_combinado,
)
```

Agregar, justo antes de `def _subir_o_guardar_local(...)`, dos funciones nuevas:

```python
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline de deteccion: YOLO+ByteTrack -> PersonTracker -> Heatmap.",
    )
    parser.add_argument(
        "--webcam", nargs="?", const=None, default=False, metavar="DEVICE",
        help="Usa la camara en vivo de la PC en vez de config.VIDEO_PATH. Sin "
             "valor usa config.WEBCAM_DEVICE_INDEX; opcionalmente se puede "
             "pasar un indice de dispositivo, ej. --webcam 1. El modo camara "
             "NUNCA persiste en la base de datos ni en Supabase Storage.",
    )
    return parser.parse_args()


def _fps_actual(muestras: deque) -> float:
    """FPS de procesamiento real (no el nominal de la camara), calculado
    sobre las marcas de tiempo de los ultimos frames PROCESADOS (ver
    fps_muestras en main()). Con menos de 2 muestras no hay intervalo que
    medir todavia."""
    if len(muestras) < 2:
        return 0.0
    return (len(muestras) - 1) / (muestras[-1] - muestras[0])
```

- [ ] **Step 4: Determinar modo cámara vs. archivo al principio de `main()`**

Reemplazar:

```python
def main() -> None:
    # ── Determinar camara e inicio de grabacion ────────────────────────────────
    try:
        camara_id = config.CAMARA_ID_OVERRIDE or utils.parse_camara_id(config.VIDEO_PATH)
        inicio_dt = utils.parse_inicio(config.VIDEO_PATH)
        print(f"Camara detectada : {camara_id}  (desde '{Path(config.VIDEO_PATH).name}')")
        print(f"Inicio grabacion : {inicio_dt}")
    except ValueError as e:
        print(f"[AVISO] {e}")
        camara_id = None
        inicio_dt = datetime.now()
```

por:

```python
def main() -> None:
    args = _parse_args()
    modo_camara = args.webcam is not False
    webcam_device = config.WEBCAM_DEVICE_INDEX if args.webcam is None else int(args.webcam)
    # SHOW_PREVIEW puede estar en False en config.py (uso normal con video de
    # archivo, sin ventana) -- en modo camara la ventana es obligatoria: ver
    # todo en vivo es el objetivo del modo, no algo opcional.
    mostrar_preview = True if modo_camara else config.SHOW_PREVIEW

    # ── Determinar camara e inicio de grabacion ────────────────────────────────
    if modo_camara:
        camara_id = None
        inicio_dt = datetime.now()
        print(f"[INFO] Modo camara en vivo (device={webcam_device}) -- NO se va "
              f"a persistir nada en la base de datos ni en Supabase Storage. Es "
              f"solo una vista previa local del pipeline.")
    else:
        try:
            camara_id = config.CAMARA_ID_OVERRIDE or utils.parse_camara_id(config.VIDEO_PATH)
            inicio_dt = utils.parse_inicio(config.VIDEO_PATH)
            print(f"Camara detectada : {camara_id}  (desde '{Path(config.VIDEO_PATH).name}')")
            print(f"Inicio grabacion : {inicio_dt}")
        except ValueError as e:
            print(f"[AVISO] {e}")
            camara_id = None
            inicio_dt = datetime.now()
```

- [ ] **Step 5: Carga de zonas — soportar lectura opcional en modo cámara**

Reemplazar:

```python
    zonas = persistencia.cargar_zonas(camara_id) if conectado else []

    if zonas:
        print(f"[DB] {len(zonas)} zonas cargadas para camara {camara_id}: {[z['nombre'] for z in zonas]}")
    else:
        print(f"[DB] Sin zonas definidas para camara {camara_id}.")
```

por:

```python
    if modo_camara and config.WEBCAM_CAMARA_ID_ZONAS is not None:
        # Carga de zonas en modo SOLO LECTURA para que el overlay las pueda
        # dibujar -- mismo patron que SOLO_LEER_ZONAS: conecta, lee, corta.
        # Nunca crea sesion ni escribe nada (coherente con modo_camara).
        zonas = persistencia.cargar_zonas(config.WEBCAM_CAMARA_ID_ZONAS) if persistencia.conectar() else []
        if persistencia.conn:
            persistencia.conn.close()
            persistencia.conn = None
    else:
        zonas = persistencia.cargar_zonas(camara_id) if conectado else []

    if zonas:
        zonas_de = config.WEBCAM_CAMARA_ID_ZONAS if modo_camara else camara_id
        print(f"[DB] {len(zonas)} zonas cargadas para camara {zonas_de}: {[z['nombre'] for z in zonas]}")
    else:
        print(f"[DB] Sin zonas definidas para esta corrida.")
```

- [ ] **Step 6: Reemplazar la apertura de `cv2.VideoCapture` por `VideoSource`**

Reemplazar:

```python
        model        = YOLO("yolov8n.pt")
        # Modelo APARTE para detectar productos (clases COCO de config.PRODUCTO_CLASES_COCO)
        # -- nunca se llama con .track()/persist=True, asi que no pisa el estado de
        # tracking de 'model' (ver utils.detectar_productos). Se usa perezosamente, solo
        # cuando alguna persona esta parada en una zona tipo='gondola' este frame.
        model_productos = YOLO("yolov8n.pt")
        cap          = cv2.VideoCapture(config.VIDEO_PATH)
        fps          = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        persistencia.actualizar_resolucion_sesion(sesion_id, frame_w, frame_h)

        max_dist            = frame_w * config.MAX_DIST_RATIO
        caja_distancia_px   = frame_w * config.CAJA_APROXIMACION_RATIO
        # Frames PROCESADOS (no crudos) por segundo real de video, para
        # convertir CAJA_PERMANENCIA_MINIMA_SEG a un contador de frames
        # consecutivos -- mismo criterio que INTERACCION_FRAMES_MINIMOS pero
        # partiendo de segundos en vez de un numero de frames fijo.
        caja_frames_minimos = max(1, round(config.CAJA_PERMANENCIA_MINIMA_SEG * fps / config.FRAME_SKIP))
        quick_expiry_frames = int(config.QUICK_EXPIRY_SEC * fps)
        long_expiry_frames  = int(config.LONG_EXPIRY_SEC * fps)
        frames_a_procesar   = total_frames // config.FRAME_SKIP

        print(f"\nVideo           : {config.VIDEO_PATH}")
        print(f"Resolucion      : {frame_w}x{frame_h}  |  {fps:.0f}fps  |  {total_frames:,} frames")
        print(f"Frames a leer   : {frames_a_procesar:,}  (frame_skip={config.FRAME_SKIP})")
        print()
```

por:

```python
        model        = YOLO("yolov8n.pt")
        # Modelo APARTE para detectar productos (clases COCO de config.PRODUCTO_CLASES_COCO)
        # -- nunca se llama con .track()/persist=True, asi que no pisa el estado de
        # tracking de 'model' (ver utils.detectar_productos). Se usa perezosamente, solo
        # cuando alguna persona esta parada en una zona tipo='gondola' este frame.
        model_productos = YOLO("yolov8n.pt")

        if modo_camara:
            source = WebcamVideoSource(
                device=webcam_device,
                resolution=config.WEBCAM_RESOLUTION,
                target_fps=config.WEBCAM_TARGET_FPS,
            )
        else:
            source = FileVideoSource(config.VIDEO_PATH)
        source.open()

        fps          = source.fps
        frame_w      = source.frame_w
        frame_h      = source.frame_h
        total_frames = source.total_frames  # None en modo camara
        # En modo camara no hay FRAME_SKIP: WebcamVideoSource ya descarta los
        # frames atrasados solo (siempre entrega el mas reciente), asi que no
        # hace falta el muestreo por FRAME_SKIP que si necesita un archivo (ahi
        # cada frame de un video ya grabado hay que decidir si se procesa).
        # frame_skip_efectivo=1 mantiene correctas las conversiones seg->frames
        # de mas abajo (caja_frames_minimos, tracker.frame_skip, etc.).
        frame_skip_efectivo = 1 if modo_camara else config.FRAME_SKIP
        persistencia.actualizar_resolucion_sesion(sesion_id, frame_w, frame_h)

        max_dist            = frame_w * config.MAX_DIST_RATIO
        caja_distancia_px   = frame_w * config.CAJA_APROXIMACION_RATIO
        # Frames PROCESADOS (no crudos) por segundo real de video, para
        # convertir CAJA_PERMANENCIA_MINIMA_SEG a un contador de frames
        # consecutivos -- mismo criterio que INTERACCION_FRAMES_MINIMOS pero
        # partiendo de segundos en vez de un numero de frames fijo.
        caja_frames_minimos = max(1, round(config.CAJA_PERMANENCIA_MINIMA_SEG * fps / frame_skip_efectivo))
        quick_expiry_frames = int(config.QUICK_EXPIRY_SEC * fps)
        long_expiry_frames  = int(config.LONG_EXPIRY_SEC * fps)
        frames_a_procesar   = (total_frames // frame_skip_efectivo) if total_frames is not None else None

        if modo_camara:
            print(f"\nCamara en vivo  : device={webcam_device}")
            print(f"Resolucion      : {frame_w}x{frame_h}  |  {fps:.0f}fps (nominal)")
        else:
            print(f"\nVideo           : {config.VIDEO_PATH}")
            print(f"Resolucion      : {frame_w}x{frame_h}  |  {fps:.0f}fps  |  {total_frames:,} frames")
            print(f"Frames a leer   : {frames_a_procesar:,}  (frame_skip={frame_skip_efectivo})")
        print()
```

- [ ] **Step 7: Desactivar Re-ID en la nube por default en modo cámara**

Reemplazar (justo antes del `if config.REID_PROVIDER == "groq":`):

```python
        # ── Construccion de los componentes del pipeline ────────────────────────────
        heatmap = HeatmapBuilder(frame_w, frame_h, config.GAUSSIAN_RADIUS)

        # Proveedor de Re-ID en la nube: Gemini o Groq (config.REID_PROVIDER), ambos
        # con la misma interfaz (.activo, .generar_descripcion(), .clasificar()) asi
        # que PersonTracker no necesita saber cual esta usando.
        if config.REID_PROVIDER == "groq":
            gemini = GroqReID(
                usar_groq_reid=config.USAR_GROQ_REID,
```

por:

```python
        # ── Construccion de los componentes del pipeline ────────────────────────────
        heatmap = HeatmapBuilder(frame_w, frame_h, config.GAUSSIAN_RADIUS)

        # En modo camara, Re-ID en la nube esta apagado por default (config.
        # WEBCAM_USAR_REID_NUBE=False) para no gastar cupo de API en pruebas
        # locales -- el tracking local (ByteTrack + apariencia) sigue andando
        # igual. Se puede prender en config.py si se quiere probar tambien.
        permitir_reid_nube = (not modo_camara) or config.WEBCAM_USAR_REID_NUBE
        if not permitir_reid_nube:
            print("[ReID] Modo camara en vivo: Re-ID en la nube desactivado por "
                  "default (config.WEBCAM_USAR_REID_NUBE=False) -- tracking local "
                  "+ heatmap sin gastar cupo de API.")

        # Proveedor de Re-ID en la nube: Gemini o Groq (config.REID_PROVIDER), ambos
        # con la misma interfaz (.activo, .generar_descripcion(), .clasificar()) asi
        # que PersonTracker no necesita saber cual esta usando.
        if config.REID_PROVIDER == "groq":
            gemini = GroqReID(
                usar_groq_reid=config.USAR_GROQ_REID and permitir_reid_nube,
```

Y, en las otras dos ramas del mismo `if/elif/else` (Claude y Gemini), aplicar el mismo cambio — reemplazar:

```python
        elif config.REID_PROVIDER == "claude":
            gemini = ClaudeReID(
                usar_claude_reid=config.USAR_CLAUDE_REID,
```

por:

```python
        elif config.REID_PROVIDER == "claude":
            gemini = ClaudeReID(
                usar_claude_reid=config.USAR_CLAUDE_REID and permitir_reid_nube,
```

y reemplazar:

```python
        else:
            gemini = GeminiReID(
                usar_gemini_reid=config.USAR_GEMINI_REID,
```

por:

```python
        else:
            gemini = GeminiReID(
                usar_gemini_reid=config.USAR_GEMINI_REID and permitir_reid_nube,
```

- [ ] **Step 8: Usar `frame_skip_efectivo` en la construcción del `PersonTracker`**

Reemplazar:

```python
        tracker = PersonTracker(
            frame_skip=config.FRAME_SKIP,
```

por:

```python
        tracker = PersonTracker(
            frame_skip=frame_skip_efectivo,
```

- [ ] **Step 9: Reemplazar el loop principal para leer de `source` (con pausa/reanudación y detección de error de cámara)**

Reemplazar:

```python
        traj_buffer            = []
        ultimo_muestreo_traj    = {}   # sid -> frame_count del ultimo punto de trayectoria guardado
        muestreo_traj_frames    = max(1, int(fps * config.TRAYECTORIA_INTERVALO_SEG))
        last_frame      = None
        frame_count     = 0
        preview_counter = 0

        pbar = tqdm(total=frames_a_procesar, unit="fr", desc="Analizando") if tqdm else None

        # ── Loop principal ──────────────────────────────────────────────────────────
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            if frame_count % config.FRAME_SKIP != 0:
                continue

            last_frame = frame

            if pbar:
                pbar.update(1)
            elif frame_count % (config.FRAME_SKIP * 500) == 0:
                pct = frame_count / total_frames * 100
                print(f"  {pct:.1f}%  [{utils.to_timestamp(frame_count, fps)}]", end="\r")
```

por:

```python
        traj_buffer            = []
        ultimo_muestreo_traj    = {}   # sid -> frame_count del ultimo punto de trayectoria guardado
        muestreo_traj_frames    = max(1, int(fps * config.TRAYECTORIA_INTERVALO_SEG))
        last_frame      = None
        frame_count     = 0
        preview_counter = 0
        fps_muestras    = deque(maxlen=30)  # timestamps de los ultimos frames PROCESADOS (FPS en vivo)
        pausado         = False

        pbar = tqdm(total=frames_a_procesar, unit="fr", desc="Analizando") if tqdm else None

        # ── Loop principal ──────────────────────────────────────────────────────────
        while True:
            if modo_camara and pausado:
                # Pausa: no se lee ni procesa. La camara sigue viva en su hilo
                # de background (WebcamVideoSource sigue capturando), asi que
                # al reanudar se retoma con el frame mas reciente disponible,
                # no con uno atrasado. La ventana queda congelada en el ultimo
                # frame ya dibujado hasta que se reanuda.
                tecla = cv2.waitKey(50) & 0xFF
                if tecla == ord('q'):
                    break
                if tecla == ord('p'):
                    pausado = False
                    print("[INFO] Reanudado.")
                continue

            ret, frame = source.read()

            if modo_camara:
                error = source.error()
                if error:
                    print(f"[ERROR] {error}")
                    break

            if not ret:
                break

            frame_count += 1
            if not modo_camara and frame_count % frame_skip_efectivo != 0:
                continue

            last_frame = frame
            fps_muestras.append(time.perf_counter())

            if pbar:
                pbar.update(1)
            elif not modo_camara and frame_count % (frame_skip_efectivo * 500) == 0:
                pct = frame_count / total_frames * 100
                print(f"  {pct:.1f}%  [{utils.to_timestamp(frame_count, fps)}]", end="\r")
```

- [ ] **Step 10: Actualizar las referencias a `config.SHOW_PREVIEW` dentro del loop por `mostrar_preview`, y dibujar FPS/estado en vivo**

Reemplazar:

```python
            # Preview del heatmap en tiempo real
            if config.SHOW_PREVIEW:
                preview_counter += 1
                if preview_counter % config.PREVIEW_CADA_N == 0:
```

por:

```python
            # Preview del heatmap en tiempo real
            if mostrar_preview:
                preview_counter += 1
                if preview_counter % config.PREVIEW_CADA_N == 0:
```

Reemplazar:

```python
                    pct = frame_count / total_frames * 100 if total_frames else 0
                    cv2.putText(overlay, f"Frame {frame_count}/{total_frames} ({pct:.0f}%)",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    cv2.imshow("OptiFull - Deteccion + Heatmap", utils.resize_for_display(overlay))
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
```

por:

```python
                    if modo_camara:
                        cv2.putText(overlay, f"LIVE | Frame {frame_count} | FPS: {_fps_actual(fps_muestras):.1f}",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    else:
                        pct = frame_count / total_frames * 100 if total_frames else 0
                        cv2.putText(overlay, f"Frame {frame_count}/{total_frames} ({pct:.0f}%)",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    cv2.imshow("OptiFull - Deteccion + Heatmap", utils.resize_for_display(overlay))
                    tecla = cv2.waitKey(1) & 0xFF
                    if tecla == ord('q'):
                        break
                    if modo_camara and tecla == ord('p'):
                        pausado = True
                        print("[INFO] Pausado -- 'p' para reanudar, 'q' para detener.")
```

- [ ] **Step 11: Liberar `source` en vez de `cap`, y usar `mostrar_preview`**

Reemplazar:

```python
        if pbar:
            pbar.close()
        if config.SHOW_PREVIEW:
            cv2.destroyAllWindows()
        cap.release()
```

por:

```python
        if pbar:
            pbar.close()
        if mostrar_preview:
            cv2.destroyAllWindows()
        source.release()
```

- [ ] **Step 12: `frames_procesados` con `frame_skip_efectivo`**

Reemplazar:

```python
        frames_procesados = frame_count // config.FRAME_SKIP
```

por:

```python
        frames_procesados = frame_count // frame_skip_efectivo
```

- [ ] **Step 13: Saltear toda la sección de guardado en BD/Storage en modo cámara**

Reemplazar (todo el bloque, desde el comentario de "Construir resultados de permanencia" hasta el `metricas.imprimir_resumen` final):

```python
        # ── Construir resultados de permanencia y guardar en BD ─────────────────────
        rows = metricas.construir_rows(tracker.resumen_por_persona(), fps)
        persistencia.guardar_personas(sesion_id, rows, traj_buffer, fps, inicio_dt, camara_id)

        # ── Auditoria post-analisis (ANTES de cerrar la sesion) ─────────────────────
        # Red de seguridad para lo que el matching en vivo puede haber dejado
        # pasar: recalcula zona_id, saca de Zona Caja a quien no matchee a un
        # empleado ya conocido, y fusiona personas de camaras del mismo grupo
        # detectadas casi al mismo instante. Va DESPUES de guardar_personas
        # (necesita las trayectorias ya volcadas por completo) pero ANTES de
        # cerrar_sesion, tal como se pidio.
        persistencia.auditar_sesion(
            sesion_id, camara_id, config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS
        )

        # Decide empleado vs cliente por la MAYORIA de puntos de trayectoria
        # de cada persona de ESTA sesion (no por presencia puntual en Zona
        # Caja -- eso fusionaba clientes que solo pasaron a pagar) y borra
        # los puntos minoritarios que contradicen esa mayoria. Ver
        # Persistencia.reclasificar_por_mayoria_zona(). Acotado a 'sesion_id'
        # para no re-escanear toda la BD en cada video.
        persistencia.reclasificar_por_mayoria_zona(sesion_id=sesion_id)

        # Recien ACA se sabe quien es empleado en esta sesion -- durante el
        # analisis en vivo (_on_visita_cerrada) todavia no se sabia, asi que
        # los eventos/alertas de un sid que termino siendo empleado quedan
        # mal clasificados (un empleado no "compra" ni puede "robar"). Se
        # descartan antes de que lleguen al frontend.
        persistencia.limpiar_eventos_de_empleados(sesion_id=sesion_id)
        persistencia.sincronizar_es_empleado_trayectorias(sesion_id=sesion_id)

        # ── Cerrar sesion ────────────────────────────────────────────────────────────
        fin_dt = utils.frame_to_dt(total_frames, fps, inicio_dt)
        persistencia.cerrar_sesion(sesion_id, fin_dt)

        # Fusion retroactiva automatica de continuidad entre videos consecutivos
        # de esta camara (corte de archivo del DVR) + cross-camara del dia --
        # antes habia que correr deteccion/mantenimiento/fusionar_dia.py a mano
        # despues de cada corrida. Se corre para 'inicio_dt' (fecha del corte
        # con la sesion ANTERIOR de esta camara, el caso comun) y tambien para
        # 'fin_dt' si cae en otro dia calendario (sesion que cruza medianoche).
        if conectado:
            fechas_fusion = {inicio_dt.date(), fin_dt.date()}
            for fecha_fusion in fechas_fusion:
                persistencia.fusionar_dia_hasta_converger(
                    fecha_fusion, config.CONTINUIDAD_VENTANA_SEG, config.CONTINUIDAD_ALTA_CONFIANZA_SEG,
                    config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS,
                )

        # ── Guardar heatmap en BD (solo el "puro", sin overlay) ─────────────────────
        if not heatmap.esta_vacio():
            stats      = heatmap.calcular_stats(zonas, config.HEATMAP_UMBRAL, config.HEATMAP_GRID)
            ts_str     = inicio_dt.strftime("%Y%m%d_%H%M%S")
            puro_bytes = heatmap.codificar_puro(stats["hm_norm"])
            imagen_url = _subir_o_guardar_local(storage, f"camara_{camara_id}/{ts_str}.png", puro_bytes)

            persistencia.guardar_heatmap(
                camara_id, sesion_id, inicio_dt, fin_dt, stats,
                imagen_url, heatmap.total_detecciones, frames_procesados,
            )

            # ── Combinar con las sesiones previas de esta camara ────────────────────
            sesiones_previas = persistencia.obtener_matrices_camara(camara_id)
            if sesiones_previas:
                grid_size = sesiones_previas[0]["resolucion_x"] or config.HEATMAP_GRID
                combinado = combinar_grids(sesiones_previas, grid_size)
                stats_cam = calcular_stats_grid(combinado, zonas, config.HEATMAP_UMBRAL, frame_w, frame_h)
                cam_bytes = codificar_combinado(stats_cam["hm_norm"], frame_w, frame_h)
                cam_url   = _subir_o_guardar_local(storage, f"camara_{camara_id}/combinado.png", cam_bytes)
                persistencia.guardar_heatmap_camara(
                    camara_id, stats_cam, cam_url,
                    sum(s["total_detecciones"] for s in sesiones_previas),
                    sum(s["frames_procesados"] for s in sesiones_previas),
                    len(sesiones_previas),
                )
        else:
            print("[Heatmap] Acumulador vacio, no se guarda en BD.")

        persistencia.cerrar()

        # ── Resumen ──────────────────────────────────────────────────────────────────
        metricas.imprimir_resumen(
            rows, camara_id, sesion_id, tracker.max_personas,
            tracker.conteo_metodo_reid, heatmap.total_detecciones, frames_procesados,
            len(traj_buffer),
        )
```

por:

```python
        # ── Construir resultados de permanencia ──────────────────────────────────────
        rows = metricas.construir_rows(tracker.resumen_por_persona(), fps)

        if modo_camara:
            # Modo camara en vivo: NUNCA se persiste -- ni BD (Persistencia.*
            # ya es no-op sin conexion, pero eso no cubre Supabase Storage) ni
            # imagenes de heatmap. Se corta explicitamente ACA, antes de
            # cualquier llamada de guardado, en vez de confiar solo en que
            # sesion_id/camara_id sean None. Ver spec: "Modo camara = sin
            # persistencia".
            print("[INFO] Modo camara en vivo: no se persistio nada en la base "
                  "de datos ni en Supabase Storage (por diseno).")
        else:
            persistencia.guardar_personas(sesion_id, rows, traj_buffer, fps, inicio_dt, camara_id)

            # ── Auditoria post-analisis (ANTES de cerrar la sesion) ─────────────────
            # Red de seguridad para lo que el matching en vivo puede haber dejado
            # pasar: recalcula zona_id, saca de Zona Caja a quien no matchee a un
            # empleado ya conocido, y fusiona personas de camaras del mismo grupo
            # detectadas casi al mismo instante. Va DESPUES de guardar_personas
            # (necesita las trayectorias ya volcadas por completo) pero ANTES de
            # cerrar_sesion, tal como se pidio.
            persistencia.auditar_sesion(
                sesion_id, camara_id, config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS
            )

            # Decide empleado vs cliente por la MAYORIA de puntos de trayectoria
            # de cada persona de ESTA sesion (no por presencia puntual en Zona
            # Caja -- eso fusionaba clientes que solo pasaron a pagar) y borra
            # los puntos minoritarios que contradicen esa mayoria. Ver
            # Persistencia.reclasificar_por_mayoria_zona(). Acotado a 'sesion_id'
            # para no re-escanear toda la BD en cada video.
            persistencia.reclasificar_por_mayoria_zona(sesion_id=sesion_id)

            # Recien ACA se sabe quien es empleado en esta sesion -- durante el
            # analisis en vivo (_on_visita_cerrada) todavia no se sabia, asi que
            # los eventos/alertas de un sid que termino siendo empleado quedan
            # mal clasificados (un empleado no "compra" ni puede "robar"). Se
            # descartan antes de que lleguen al frontend.
            persistencia.limpiar_eventos_de_empleados(sesion_id=sesion_id)
            persistencia.sincronizar_es_empleado_trayectorias(sesion_id=sesion_id)

            # ── Cerrar sesion ──────────────────────────────────────────────────────
            fin_dt = utils.frame_to_dt(total_frames, fps, inicio_dt)
            persistencia.cerrar_sesion(sesion_id, fin_dt)

            # Fusion retroactiva automatica de continuidad entre videos consecutivos
            # de esta camara (corte de archivo del DVR) + cross-camara del dia --
            # antes habia que correr deteccion/mantenimiento/fusionar_dia.py a mano
            # despues de cada corrida. Se corre para 'inicio_dt' (fecha del corte
            # con la sesion ANTERIOR de esta camara, el caso comun) y tambien para
            # 'fin_dt' si cae en otro dia calendario (sesion que cruza medianoche).
            if conectado:
                fechas_fusion = {inicio_dt.date(), fin_dt.date()}
                for fecha_fusion in fechas_fusion:
                    persistencia.fusionar_dia_hasta_converger(
                        fecha_fusion, config.CONTINUIDAD_VENTANA_SEG, config.CONTINUIDAD_ALTA_CONFIANZA_SEG,
                        config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS,
                    )

            # ── Guardar heatmap en BD (solo el "puro", sin overlay) ──────────────────
            if not heatmap.esta_vacio():
                stats      = heatmap.calcular_stats(zonas, config.HEATMAP_UMBRAL, config.HEATMAP_GRID)
                ts_str     = inicio_dt.strftime("%Y%m%d_%H%M%S")
                puro_bytes = heatmap.codificar_puro(stats["hm_norm"])
                imagen_url = _subir_o_guardar_local(storage, f"camara_{camara_id}/{ts_str}.png", puro_bytes)

                persistencia.guardar_heatmap(
                    camara_id, sesion_id, inicio_dt, fin_dt, stats,
                    imagen_url, heatmap.total_detecciones, frames_procesados,
                )

                # ── Combinar con las sesiones previas de esta camara ────────────────
                sesiones_previas = persistencia.obtener_matrices_camara(camara_id)
                if sesiones_previas:
                    grid_size = sesiones_previas[0]["resolucion_x"] or config.HEATMAP_GRID
                    combinado = combinar_grids(sesiones_previas, grid_size)
                    stats_cam = calcular_stats_grid(combinado, zonas, config.HEATMAP_UMBRAL, frame_w, frame_h)
                    cam_bytes = codificar_combinado(stats_cam["hm_norm"], frame_w, frame_h)
                    cam_url   = _subir_o_guardar_local(storage, f"camara_{camara_id}/combinado.png", cam_bytes)
                    persistencia.guardar_heatmap_camara(
                        camara_id, stats_cam, cam_url,
                        sum(s["total_detecciones"] for s in sesiones_previas),
                        sum(s["frames_procesados"] for s in sesiones_previas),
                        len(sesiones_previas),
                    )
            else:
                print("[Heatmap] Acumulador vacio, no se guarda en BD.")

        persistencia.cerrar()

        # ── Resumen ──────────────────────────────────────────────────────────────────
        metricas.imprimir_resumen(
            rows, camara_id, sesion_id, tracker.max_personas,
            tracker.conteo_metodo_reid, heatmap.total_detecciones, frames_procesados,
            len(traj_buffer),
        )
```

- [ ] **Step 14: Mensaje de interrupción claro en modo cámara**

Reemplazar:

```python
    except (KeyboardInterrupt, Exception):
        # Analisis interrumpido a mitad de camino (Ctrl+C, cupo de API
        # agotado, excepcion no manejada, etc.): no dejar la sesion a medio
        # procesar en la BD -- se borra entera (personas/trayectorias/visitas
        # via CASCADE) para no contaminar el Re-ID entre camaras ni los
        # reportes con datos incompletos.
        print(f"\n[AVISO] Analisis interrumpido -- borrando la sesion incompleta "
              f"(id={sesion_id}) de la BD...")
        if conectado and sesion_id:
            persistencia.borrar_sesion(sesion_id)
        persistencia.cerrar()
        raise
```

por:

```python
    except (KeyboardInterrupt, Exception):
        if modo_camara:
            # No hay sesion en BD que limpiar (nunca se creo una) -- solo
            # confirmar que la camara se corto.
            print("\n[INFO] Camara en vivo detenida.")
        else:
            # Analisis interrumpido a mitad de camino (Ctrl+C, cupo de API
            # agotado, excepcion no manejada, etc.): no dejar la sesion a medio
            # procesar en la BD -- se borra entera (personas/trayectorias/visitas
            # via CASCADE) para no contaminar el Re-ID entre camaras ni los
            # reportes con datos incompletos.
            print(f"\n[AVISO] Analisis interrumpido -- borrando la sesion incompleta "
                  f"(id={sesion_id}) de la BD...")
            if conectado and sesion_id:
                persistencia.borrar_sesion(sesion_id)
        persistencia.cerrar()
        raise
```

- [ ] **Step 15: Verificar que el archivo sigue siendo Python válido y que el CLI responde**

Run: `python -c "import ast; ast.parse(open('deteccion/main.py', encoding='utf-8').read())"`
Expected: sin salida (parseo exitoso, sin `SyntaxError`)

Run: `python deteccion/main.py --help`
Expected: imprime el `usage:` de argparse con la opción `--webcam`, sale con código 0 (sin intentar abrir cámara ni video)

- [ ] **Step 16: Correr toda la suite de tests unitarios para confirmar que nada se rompió**

Run: `python -m pytest test/unitarios -v`
Expected: PASS (todos)

- [ ] **Step 17: Commit**

```bash
git add deteccion/main.py deteccion/config.py
git commit -m "Agregar modo camara en vivo (--webcam) a deteccion/main.py, sin persistencia"
```

---

## Task 4: Verificación manual con cámara real

No es automatizable (requiere una webcam física y una ventana visible) — lo corre el usuario en su máquina. Este paso queda documentado como checklist, no como test.

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Correr el modo cámara**

Run: `python deteccion/main.py --webcam`

Verificar en consola:
- `[INFO] Modo camara en vivo (device=0) -- NO se va a persistir...`
- `[ReID] Modo camara en vivo: Re-ID en la nube desactivado...`
- `[DB] Sin zonas definidas para esta corrida.` (a menos que se haya configurado `WEBCAM_CAMARA_ID_ZONAS`)

- [ ] **Step 2: Verificar la ventana**

Se abre "OptiFull - Deteccion + Heatmap" mostrando la cámara en vivo con:
- Boxes verdes + `#sid` sobre las personas detectadas.
- Heatmap superpuesto que se va acumulando.
- Texto `LIVE | Frame N | FPS: X.X` en la esquina superior izquierda, con un FPS > 0 después de un par de segundos.

- [ ] **Step 3: Probar pausa/reanudación**

Presionar `p` → la ventana se congela en el último frame, consola imprime `[INFO] Pausado...`.
Presionar `p` de nuevo → se reanuda con un frame fresco (no uno viejo), consola imprime `[INFO] Reanudado.`.

- [ ] **Step 4: Detener con 'q' y verificar liberación**

Presionar `q` → la ventana se cierra, el proceso termina limpio, imprime el resumen final (`metricas.imprimir_resumen`) y `[INFO] Modo camara en vivo: no se persistio nada...`.

Verificar que la cámara quedó liberada: abrir cualquier otra app que use la webcam (ej. la app Cámara de Windows) y confirmar que puede abrirla sin error de "dispositivo en uso".

- [ ] **Step 5: Confirmar que no se escribió nada en la BD**

Si `DATABASE_URL` está configurado en `.env`, correr una consulta rápida antes y después de la corrida en vivo:

```sql
SELECT COUNT(*) FROM sesiones_video;
```

El conteo debe ser idéntico antes y después de correr `--webcam`.

- [ ] **Step 6: Confirmar que el modo archivo sigue funcionando igual que antes**

Run: `python deteccion/main.py`

Debe comportarse exactamente igual que antes de este cambio: mismo log de inicio (`Camara detectada`, `Video`, `Resolucion`, `Frames a leer`), mismo comportamiento de persistencia si hay BD configurada, mismo `Ctrl+C` -> borra sesión incompleta.

- [ ] **Step 7 (opcional): Probar el manejo de error de cámara**

Run: `python deteccion/main.py --webcam 99` (índice de dispositivo que no existe)

Expected: falla rápido con un mensaje claro tipo `[ERROR] ...` o una excepción con `RuntimeError: No se pudo abrir la camara '99'. Verifica que este conectada...` — no un traceback críptico de OpenCV.

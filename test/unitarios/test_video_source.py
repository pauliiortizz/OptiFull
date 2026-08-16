"""Tests unitarios de VideoSource: FileVideoSource envuelve un archivo real
(se genera uno sintetico de unos pocos frames por test, sin depender de
ningun video del repo); WebcamVideoSource se prueba con cv2.VideoCapture
mockeado (ver mas abajo) porque no hay camara real en CI."""
import threading
import time
from unittest.mock import MagicMock, patch

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

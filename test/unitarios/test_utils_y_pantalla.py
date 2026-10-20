"""Tests complementarios de deteccion/utils.py (fechas desde el nombre del video, reloj en vivo, escalado de
zonas, zona mas cercana) y de ScreenVideoSource (captura de pantalla, con un doble de la libreria mss)."""
import os
import sys
import types
from datetime import datetime

import cv2
import numpy as np
import pytest

from deteccion import utils
from deteccion.pipeline import video_source as vs


# ── utils: nombre del video, reloj y zonas ────────────────────────────────────

def test_camara_sin_prefijo_d_lanza_error_claro():
    with pytest.raises(ValueError, match="CAMARA_ID_OVERRIDE"):
        utils.parse_camara_id("video_caja.mp4")


@pytest.mark.parametrize("nombre, esperado", [
    ("D04_20260705143000.mp4", datetime(2026, 7, 5, 14, 30)),
    ("D01_20260705_090510.mp4", datetime(2026, 7, 5, 9, 5, 10)),
])
def test_inicio_desde_el_nombre_del_video(nombre, esperado):
    assert utils.parse_inicio(nombre) == esperado


@pytest.mark.parametrize("nombre", ["D04_sin_fecha.mp4", "D04_20261399_250000.mp4"])   # sin fecha o fecha invalida
def test_sin_fecha_valida_usa_la_fecha_del_archivo(tmp_path, nombre):
    archivo = tmp_path / nombre
    archivo.write_bytes(b"")
    os.utime(archivo, (1_760_000_000, 1_760_000_000))
    assert utils.parse_inicio(str(archivo)) == datetime.fromtimestamp(1_760_000_000)


def test_reloj_en_vivo_usa_la_hora_real_de_cada_frame():
    inicio = datetime(2026, 10, 7, 10)
    reloj = [datetime(2026, 10, 7, 10, 0, 5), datetime(2026, 10, 7, 10, 0, 9)]
    try:
        utils.set_reloj_vivo(reloj)
        assert utils.frame_to_dt(1, 30, inicio) == reloj[1]
        assert utils.frame_to_dt(5, 1, inicio) == datetime(2026, 10, 7, 10, 0, 5)   # fuera del reloj: frame/fps
    finally:
        utils.set_reloj_vivo(None)
    assert utils.frame_to_dt(60, 30, inicio) == datetime(2026, 10, 7, 10, 0, 2)


def test_escalar_zonas_a_otra_resolucion():
    zonas = [{"id": 1, "poligono": [[0, 0], [1920, 1080]]}, {"id": 2, "poligono": "[[960, 540], [0, 1080]]"}]
    assert utils.escalar_zonas(zonas, 1920, 1080, 1920, 1080) is zonas        # mismo tamano: sin cambios
    assert utils.escalar_zonas([], 640, 360, 1920, 1080) == []
    escaladas = utils.escalar_zonas(zonas, 640, 360, 1920, 1080)
    assert escaladas[0]["poligono"] == [[0, 0], [640, 360]]
    assert escaladas[1]["poligono"] == [[320, 180], [0, 360]]                 # el poligono puede venir como JSON


ZONA = [{"id": 7, "poligono": [[0, 0], [100, 0], [100, 100], [0, 100]]}]


@pytest.mark.parametrize("punto, esperado", [
    ((50, 50), 7),       # adentro
    ((50, 115), 7),      # afuera, a 15 px del borde: se asigna a la zona mas cercana
    ((50, 125), None),   # a 25 px: fuera de cobertura
])
def test_zona_por_cercania_al_borde(punto, esperado):
    assert utils.get_zona_id(*punto, ZONA, max_dist_borde=20) == esperado


def test_distancia_a_un_lado_degenerado():
    assert utils._dist_punto_segmento(3, 4, 0, 0, 0, 0) == pytest.approx(5.0)


@pytest.mark.parametrize("tamano, esperado", [((1920, 1080), (1280, 720)), ((640, 480), (640, 480))])
def test_achicar_para_mostrar_en_pantalla(tamano, esperado):
    w, h = tamano
    assert utils.resize_for_display(np.zeros((h, w, 3), np.uint8)).shape[:2] == (esperado[1], esperado[0])


# ── ScreenVideoSource con un doble de mss ─────────────────────────────────────

class CapturaFalsa:
    monitores = [{"left": 0, "top": 0, "width": 200, "height": 100},   # 0 = todos juntos
                 {"left": 0, "top": 0, "width": 200, "height": 100}]
    falla = False

    def __init__(self):
        self.monitors = self.monitores
        self.cerrada = False

    def grab(self, area):
        if CapturaFalsa.falla:
            raise OSError("pantalla bloqueada")
        return np.full((area["height"], area["width"], 4), 90, np.uint8)   # mss entrega BGRA

    def close(self):
        self.cerrada = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture
def mss_falso(monkeypatch):
    CapturaFalsa.falla = False
    monkeypatch.setitem(sys.modules, "mss", types.SimpleNamespace(mss=CapturaFalsa))


def test_captura_de_un_monitor_entrega_frames_bgr(mss_falso):
    fuente = vs.ScreenVideoSource(monitor=1, target_fps=100)
    fuente.open()
    try:
        ok, frame = fuente.read()
        assert ok and frame.shape == (100, 200, 3)
        assert (fuente.frame_w, fuente.frame_h, fuente.fps) == (200, 100, 100)
        assert fuente.is_live and fuente.total_frames is None and fuente.error() is None
    finally:
        fuente.release()
    fuente.release()   # liberar dos veces no rompe


def test_captura_de_una_region_achicada(mss_falso):
    fuente = vs.ScreenVideoSource(region=(10, 10, 80, 40), scale=0.5)
    fuente.open()
    try:
        assert fuente.read()[1].shape == (20, 40, 3)
    finally:
        fuente.release()


def test_monitor_inexistente_lanza_error_claro(mss_falso):
    with pytest.raises(RuntimeError, match="No existe el monitor 5"):
        vs.ScreenVideoSource(monitor=5).open()


def test_si_la_captura_falla_open_lanza_el_error(mss_falso):
    CapturaFalsa.falla = True
    with pytest.raises(RuntimeError, match="pantalla bloqueada"):
        vs.ScreenVideoSource(monitor=1).open()


def test_sin_frames_en_el_tiempo_limite_open_falla(monkeypatch, mss_falso):
    monkeypatch.setattr(vs.ScreenVideoSource, "_loop_captura", lambda self: None)   # el hilo nunca entrega
    with pytest.raises(RuntimeError, match="no entrego ningun frame"):
        vs.ScreenVideoSource(monitor=1, timeout_primer_frame_seg=0.05).open()


def test_read_antes_del_primer_frame_devuelve_false():
    assert vs.ScreenVideoSource().read(timeout=0.01) == (False, None)


def test_cvtcolor_de_bgra_a_bgr_conserva_los_valores():
    # El pipeline (YOLO/cv2) espera BGR de 3 canales: la conversion no debe alterar el color
    bgra = np.full((2, 2, 4), (10, 20, 30, 255), np.uint8)
    assert cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)[0, 0].tolist() == [10, 20, 30]

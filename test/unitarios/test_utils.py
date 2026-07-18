"""Tests unitarios de deteccion/utils.py -- helpers puros de parsing y
geometria, sin BD, red ni video real."""
from datetime import datetime

import numpy as np
import pytest

from deteccion.utils import (
    frame_to_dt,
    get_zona_id,
    parse_camara_id,
    point_in_polygon,
    safe_crop,
    to_timestamp,
)


# ── parse_camara_id ─────────────────────────────────────────────────────────

def test_parse_camara_id_extrae_numero_de_camara():
    assert parse_camara_id("D04_20260520_061524.mp4") == 4


def test_parse_camara_id_es_case_insensitive():
    assert parse_camara_id("d01_20260101_120000.mp4") == 1


def test_parse_camara_id_ignora_directorio_en_el_path():
    assert parse_camara_id("videos/entrada/D03_20260101_120000.mp4") == 3


def test_parse_camara_id_formato_invalido_lanza_valueerror():
    with pytest.raises(ValueError):
        parse_camara_id("grabacion_sin_formato.mp4")


# ── frame_to_dt / to_timestamp ──────────────────────────────────────────────

def test_frame_to_dt_frame_cero_es_el_inicio():
    inicio = datetime(2026, 5, 20, 10, 0, 0)
    assert frame_to_dt(0, 30.0, inicio) == inicio


def test_frame_to_dt_suma_segundos_segun_fps():
    inicio = datetime(2026, 5, 20, 10, 0, 0)
    # 300 frames a 30 fps = 10 segundos
    assert frame_to_dt(300, 30.0, inicio) == datetime(2026, 5, 20, 10, 0, 10)


def test_to_timestamp_formatea_hh_mm_ss():
    # 3600 frames a 30fps = 120 segundos = 0:02:00
    assert to_timestamp(3600, 30.0) == "0:02:00"


# ── point_in_polygon ─────────────────────────────────────────────────────────

CUADRADO = [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_point_in_polygon_punto_adentro():
    assert point_in_polygon(5, 5, CUADRADO) is True


def test_point_in_polygon_punto_afuera():
    assert point_in_polygon(50, 50, CUADRADO) is False


def test_point_in_polygon_punto_lejos_en_negativo():
    assert point_in_polygon(-5, -5, CUADRADO) is False


# ── get_zona_id ──────────────────────────────────────────────────────────────

ZONAS = [
    {"id": 1, "poligono": [(0, 0), (10, 0), (10, 10), (0, 10)]},
    {"id": 2, "poligono": [(20, 20), (30, 20), (30, 30), (20, 30)]},
]


def test_get_zona_id_devuelve_la_zona_que_contiene_el_punto():
    assert get_zona_id(5, 5, ZONAS) == 1
    assert get_zona_id(25, 25, ZONAS) == 2


def test_get_zona_id_devuelve_none_si_no_esta_en_ninguna_zona():
    assert get_zona_id(100, 100, ZONAS) is None


# ── safe_crop ────────────────────────────────────────────────────────────────

def test_safe_crop_recorta_bbox_normal():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    crop = safe_crop(frame, [10, 20, 50, 80])
    assert crop.shape == (60, 40, 3)


def test_safe_crop_clampea_bbox_que_se_pasa_de_los_bordes():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    # Box que excede el frame (200x100) en ambos ejes
    crop = safe_crop(frame, [-50, -50, 500, 500])
    assert crop.shape == (100, 200, 3)


def test_safe_crop_bbox_totalmente_fuera_de_frame_devuelve_vacio():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    crop = safe_crop(frame, [300, 300, 400, 400])
    assert crop.size == 0

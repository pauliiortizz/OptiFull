"""Tests unitarios de deteccion/utils.py -- helpers puros de parsing y
geometria, sin BD, red ni video real."""
from datetime import datetime

import numpy as np
import pytest

from deteccion.utils import (
    cerca_de_zona_tipo,
    detectar_productos,
    frame_to_dt,
    get_zona_id,
    parse_camara_id,
    point_in_polygon,
    producto_cerca_de_persona,
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


# ── cerca_de_zona_tipo ───────────────────────────────────────────────────────

ZONAS_CON_TIPO = [
    {"id": 1, "tipo": "caja",    "poligono": [(0, 0), (10, 0), (10, 10), (0, 10)]},
    {"id": 2, "tipo": "gondola", "poligono": [(50, 50), (60, 50), (60, 60), (50, 60)]},
]


def test_cerca_de_zona_tipo_true_si_esta_dentro_del_poligono():
    # Zona Caja es el lado del EMPLEADO, pero si el punto SI cae adentro
    # (proyeccion del pie pegado al mostrador) tambien debe contar.
    assert cerca_de_zona_tipo(5, 5, ZONAS_CON_TIPO, "caja", max_dist=0) is True


def test_cerca_de_zona_tipo_true_si_esta_cerca_del_borde_sin_entrar():
    # El cliente se ACERCA desde el lado de enfrente sin pisar el poligono.
    assert cerca_de_zona_tipo(15, 5, ZONAS_CON_TIPO, "caja", max_dist=10) is True


def test_cerca_de_zona_tipo_false_si_esta_lejos():
    assert cerca_de_zona_tipo(15, 5, ZONAS_CON_TIPO, "caja", max_dist=2) is False


def test_cerca_de_zona_tipo_ignora_zonas_de_otro_tipo():
    # (55, 55) esta DENTRO de la zona gondola, no de ninguna zona 'caja'.
    assert cerca_de_zona_tipo(55, 55, ZONAS_CON_TIPO, "caja", max_dist=5) is False


def test_cerca_de_zona_tipo_sin_zonas_de_ese_tipo_es_false():
    assert cerca_de_zona_tipo(5, 5, ZONAS_CON_TIPO, "deposito", max_dist=100) is False


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


# ── producto_cerca_de_persona ────────────────────────────────────────────────

def test_producto_cerca_de_persona_centro_dentro_del_box():
    box_persona = [100, 100, 150, 250]
    productos = [[110, 120, 130, 140]]  # centro (120, 130) cae adentro
    assert producto_cerca_de_persona(box_persona, productos) is True


def test_producto_cerca_de_persona_centro_lejos_no_cuenta():
    box_persona = [100, 100, 150, 250]
    productos = [[500, 500, 520, 520]]
    assert producto_cerca_de_persona(box_persona, productos) is False


def test_producto_cerca_de_persona_usa_el_margen_configurado():
    box_persona = [100, 100, 150, 250]
    # Centro del producto en (160, 150): 10px afuera del borde derecho (x2=150)
    producto = [[155, 140, 165, 160]]
    assert producto_cerca_de_persona(box_persona, producto, margen_px=15) is True
    assert producto_cerca_de_persona(box_persona, producto, margen_px=5) is False


def test_producto_cerca_de_persona_sin_productos_es_false():
    assert producto_cerca_de_persona([0, 0, 10, 10], []) is False


def test_producto_cerca_de_persona_alguno_de_varios_alcanza():
    box_persona = [100, 100, 150, 250]
    productos = [[500, 500, 520, 520], [110, 120, 130, 140]]
    assert producto_cerca_de_persona(box_persona, productos) is True


# ── detectar_productos ───────────────────────────────────────────────────────

class _BoxesFake:
    """Duplica solo lo que detectar_productos() toca de 'results[0].boxes'
    (un objeto ultralytics.Boxes real), sin cargar pesos de YOLO."""

    def __init__(self, boxes):
        self._boxes = boxes

    @property
    def xyxy(self):
        boxes = self._boxes

        class _Tensor:
            def tolist(self):
                return boxes

        return _Tensor()


class _ResultadoFake:
    def __init__(self, boxes):
        self.boxes = _BoxesFake(boxes) if boxes is not None else None


class _ModeloFake:
    """Duplica la interfaz minima de un modelo YOLO (ultralytics) que
    detectar_productos() necesita: llamable, devuelve una lista de
    resultados con .boxes.xyxy.tolist()."""

    def __init__(self, boxes):
        self._boxes = boxes
        self.llamadas = []

    def __call__(self, frame, classes, conf, verbose):
        self.llamadas.append({"frame": frame, "classes": classes, "conf": conf, "verbose": verbose})
        return [_ResultadoFake(self._boxes)]


def test_detectar_productos_devuelve_los_boxes_del_resultado():
    modelo = _ModeloFake([[10, 10, 20, 20]])
    boxes = detectar_productos(modelo, frame=None, clases=[39, 41], conf=0.4)
    assert boxes == [[10, 10, 20, 20]]
    assert modelo.llamadas[0]["classes"] == [39, 41]
    assert modelo.llamadas[0]["conf"] == 0.4


def test_detectar_productos_sin_clases_configuradas_no_llama_al_modelo():
    modelo = _ModeloFake([[10, 10, 20, 20]])
    boxes = detectar_productos(modelo, frame=None, clases=[], conf=0.4)
    assert boxes == []
    assert modelo.llamadas == []


def test_detectar_productos_sin_boxes_en_el_resultado_devuelve_lista_vacia():
    modelo = _ModeloFake(None)
    boxes = detectar_productos(modelo, frame=None, clases=[39], conf=0.4)
    assert boxes == []

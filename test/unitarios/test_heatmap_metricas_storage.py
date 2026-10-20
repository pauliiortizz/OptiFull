"""Tests de deteccion/pipeline: mapa de calor (heatmap.py), metricas de permanencia (metricas.py) y
subida a Supabase Storage (storage.py, con requests simulado: no sale a internet)."""
import json

import cv2
import numpy as np
import pytest

from deteccion.pipeline import metricas, storage
from deteccion.pipeline.heatmap import (HeatmapBuilder, _make_gaussian, calcular_stats_grid, codificar_combinado,
                                        combinar_grids)

PNG = b"\x89PNG"


def decodificar(png):
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)


# ── HeatmapBuilder ────────────────────────────────────────────────────────────

def test_kernel_gaussiano_simetrico_con_maximo_1_en_el_centro():
    k = _make_gaussian(5)
    assert k.shape == (11, 11)
    assert k[5, 5] == pytest.approx(1.0) and k.max() == pytest.approx(1.0)
    assert np.allclose(k, k.T) and np.allclose(k, k[::-1, ::-1])


def test_heatmap_nuevo_esta_vacio_y_al_agregar_un_punto_ya_no():
    hm = HeatmapBuilder(100, 80, gaussian_radius=6)
    assert hm.esta_vacio()
    hm.agregar_punto(50, 40)
    assert not hm.esta_vacio() and hm.total_detecciones == 1
    assert hm.accumulator[40, 50] == pytest.approx(1.0)   # el centro recibe el maximo del kernel


@pytest.mark.parametrize("cx, cy", [(0, 0), (99, 79), (-3, 40), (102, 85)])
def test_puntos_en_el_borde_o_afuera_no_rompen(cx, cy):
    # Valores limite: el kernel se recorta contra los bordes del frame
    hm = HeatmapBuilder(100, 80, gaussian_radius=6)
    hm.agregar_punto(cx, cy)
    assert hm.accumulator.shape == (80, 100)


def test_render_con_y_sin_fondo():
    hm = HeatmapBuilder(40, 30, gaussian_radius=4)
    assert hm.render().shape == (30, 40, 3)                     # vacio: no divide por cero
    hm.agregar_punto(20, 15)
    fondo = np.full((30, 40, 3), 200, np.uint8)
    assert hm.render(fondo, alpha_bg=1.0).tolist() == fondo.tolist()   # alpha 1: solo el fondo


ZONAS = [{"id": 1, "poligono": [[0, 0], [49, 0], [49, 79], [0, 79]]},       # mitad izquierda
         {"id": 2, "poligono": [[50, 0], [99, 0], [99, 79], [50, 79]]}]     # mitad derecha


def test_estadisticas_del_heatmap():
    hm = HeatmapBuilder(100, 80, gaussian_radius=5)
    for _ in range(3):
        hm.agregar_punto(80, 40)   # punto caliente a la derecha
    hm.agregar_punto(20, 40)
    st = hm.calcular_stats(ZONAS, umbral_pct=0.5, grid_size=8)
    assert (st["punto_max_x"], st["punto_max_y"]) == (80, 40)
    assert st["valor_maximo"] == pytest.approx(3.0)
    assert st["zona_id_mas_caliente"] == 2
    assert 0 < st["area_activa_pct"] < 10 and 0 < st["concentracion"] <= 1
    matriz = json.loads(st["matriz_json"])
    assert len(matriz) == 8 and len(matriz[0]) == 8 and max(map(max, matriz)) <= 1.0


def test_estadisticas_sin_zonas():
    hm = HeatmapBuilder(50, 50, gaussian_radius=3)
    hm.agregar_punto(10, 10)
    assert hm.calcular_stats([], umbral_pct=0.5, grid_size=4)["zona_id_mas_caliente"] is None


def test_codificar_puro_genera_png_con_transparencia_donde_no_hubo_calor():
    hm = HeatmapBuilder(60, 40, gaussian_radius=4)
    hm.agregar_punto(30, 20)
    img = decodificar(hm.codificar_puro(hm.calcular_stats([], 0.5, 8)["hm_norm"]))
    assert img.shape == (40, 60, 4)
    assert img[0, 0, 3] == 0 and img[20, 30, 3] == 255   # alfa = intensidad


# ── Heatmap combinado entre sesiones ──────────────────────────────────────────

def test_combinar_grids_recupera_la_escala_de_cada_sesion():
    sesiones = [{"matriz": [[1.0, 0.0], [0.0, 0.5]], "valor_maximo": 4},
                {"matriz": json.dumps([[0.0, 1.0], [0.0, 1.0]]), "valor_maximo": 2},   # puede venir como JSON
                {"matriz": [[1.0, 1.0], [1.0, 1.0]], "valor_maximo": None}]            # sin maximo: no suma
    assert combinar_grids(sesiones, 2).tolist() == [[4.0, 2.0], [0.0, 4.0]]


def test_stats_de_la_grilla_combinada_en_coordenadas_del_frame():
    grid = np.zeros((4, 4))
    grid[1, 3] = 8.0   # celda fila 1, columna 3
    st = calcular_stats_grid(grid, ZONAS, umbral_pct=0.5, frame_w=100, frame_h=80)
    assert (st["punto_max_x"], st["punto_max_y"]) == (75, 20)
    assert st["zona_id_mas_caliente"] == 2
    assert st["area_activa_pct"] == pytest.approx(6.25)   # 1 de 16 celdas
    assert st["concentracion"] == pytest.approx(1.0)


def test_stats_de_una_grilla_vacia_no_divide_por_cero():
    st = calcular_stats_grid(np.zeros((4, 4)), [], umbral_pct=0.5, frame_w=100, frame_h=80)
    assert st["valor_maximo"] == 0 and st["concentracion"] == 0.0


@pytest.mark.parametrize("tamano, esperado", [((None, None), (4, 4)), ((64, 48), (48, 64))])
def test_codificar_combinado_reescala_a_la_resolucion_de_la_camara(tamano, esperado):
    img = decodificar(codificar_combinado(np.eye(4), *tamano))
    assert img.shape[:2] == esperado and img.shape[2] == 4


# ── Metricas de permanencia ───────────────────────────────────────────────────

@pytest.mark.parametrize("seg, bucket", [
    (0, "< 1 min"), (59.9, "< 1 min"), (60, "1-5 min"), (299, "1-5 min"), (300, "5-15 min"),
    (899, "5-15 min"), (900, "15-60 min"), (3599, "15-60 min"), (3600, "> 1 hora"),
])
def test_bucket_de_permanencia_valores_limite(seg, bucket):
    assert metricas._dist_bucket(seg) == bucket


def test_construir_rows_calcula_entrada_salida_y_duracion():
    resumen = [{"sid": 3, "first_frame": 0, "last_frame": 299, "metodo_reid": "nuevo", "descripcion": None},
               {"sid": 4, "first_frame": 30, "last_frame": 30, "metodo_reid": "gemini", "descripcion": {"a": 1},
                "cliente_id_hint": 9}]
    r1, r2 = metricas.construir_rows(resumen, fps=30)
    assert (r1["entrada"], r1["salida"], r1["duracion_seg"], r1["duracion_min"]) == ("0:00:00", "0:00:09", 10.0, 0.17)
    assert r1["cliente_id_hint"] is None
    assert (r2["duracion_seg"], r2["cliente_id_hint"]) == (0.0, 9)   # 1 frame a 30 fps = 0.03 s


def test_imprimir_resumen_con_personas_y_reid_en_la_nube(capsys):
    rows = metricas.construir_rows([
        {"sid": 1, "first_frame": 0, "last_frame": 59, "metodo_reid": "nuevo", "descripcion": None},
        {"sid": 2, "first_frame": 0, "last_frame": 3599, "metodo_reid": "gemini", "descripcion": None}], fps=1)
    metricas.imprimir_resumen(rows, camara_id=2, sesion_id=7, max_personas=2,
                              conteo_metodo_reid={"nuevo": 2, "posicion": 1, "gemini": 1},
                              total_detecciones=1234, frames_procesados=5000, num_trayectorias=40)
    salida = capsys.readouterr().out
    assert "Personas unicas detectadas  : 2" in salida
    assert "Permanencia maxima          : 60.0 min  (ID 2)" in salida
    assert "gemini      :    1  (25.0%)" in salida
    assert "50.0% local, 50.0% Gemini" in salida
    assert "sesion=7, 2 personas, 40 trayectorias" in salida


def test_imprimir_resumen_sin_personas_ni_sesion(capsys):
    metricas.imprimir_resumen([], None, None, 0, {}, 0, 0, 0)
    salida = capsys.readouterr().out
    assert "Camara                      : desconocida" in salida and "no guardada" in salida
    assert "Permanencia maxima" not in salida
    assert "BD              :" not in salida


# ── Supabase Storage ──────────────────────────────────────────────────────────

class RespuestaFalsa:
    def __init__(self, status=200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Http:
    """Doble de requests.put/delete: guarda los pedidos y responde con 'status' (None = sin red)."""

    def __init__(self):
        self.pedidos, self.status = [], 200


@pytest.fixture
def http(monkeypatch):
    estado = Http()
    pedidos = estado.pedidos

    def put(url, headers, data, timeout):
        pedidos.append(("PUT", url, headers, data))
        return RespuestaFalsa(estado.status)

    def delete(url, headers, timeout):
        pedidos.append(("DELETE", url, headers, None))
        if estado.status is None:
            raise ConnectionError("sin red")
        return RespuestaFalsa(estado.status)

    monkeypatch.setattr(storage.requests, "put", put)
    monkeypatch.setattr(storage.requests, "delete", delete)
    return estado


@pytest.mark.parametrize("url, clave, habilitado, esperado", [
    ("https://x.supabase.co/", "k", True, True),
    ("", "k", True, False),            # sin URL
    ("https://x.supabase.co", None, True, False),   # sin clave
    ("https://x.supabase.co", "k", False, False),   # deshabilitado a proposito
])
def test_storage_solo_se_habilita_con_url_y_clave(url, clave, habilitado, esperado):
    assert storage.SupabaseStorage(url, clave, "heatmaps", habilitado).enabled is esperado


def test_subir_png_usa_upsert_y_devuelve_la_url_publica(http):
    s = storage.SupabaseStorage("https://x.supabase.co/", "clave", "heatmaps", True)
    url = s.subir_png("camara_2/combinado.png", PNG)
    assert url == "https://x.supabase.co/storage/v1/object/public/heatmaps/camara_2/combinado.png"
    metodo, endpoint, headers, data = http.pedidos[0]
    assert endpoint == "https://x.supabase.co/storage/v1/object/heatmaps/camara_2/combinado.png"
    assert headers["x-upsert"] == "true" and headers["Content-Type"] == "image/png" and data == PNG


def test_subida_fallida_o_deshabilitada_devuelve_none(http, capsys):
    http.status = 500
    assert storage.SupabaseStorage("https://x", "k", "b", True).subir("a.png", PNG, "image/png") is None
    assert "Error subiendo 'a.png'" in capsys.readouterr().out
    assert storage.SupabaseStorage("", "k", "b", True).subir("a.png", PNG, "image/png") is None


@pytest.mark.parametrize("status, esperado", [(200, True), (204, True), (404, True), (403, False), (None, False)])
def test_borrar_considera_borrado_si_ya_no_existia(http, status, esperado):
    http.status = status
    assert storage.SupabaseStorage("https://x", "k", "b", True).borrar("a.png") is esperado


def test_borrar_sin_storage_no_hace_nada(http):
    assert storage.SupabaseStorage("", None, "b", True).borrar("a.png") is False
    assert http.pedidos == []

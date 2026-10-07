"""Tests unitarios de deteccion/pipeline/fotos.py (foto de cada persona para decidir si es empleado) y de las
alertas 'Persona posiblemente empleada' de frontend/api/alertas.py. Sin camara ni BD."""
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import numpy as np

from deteccion.pipeline.fotos import CapturadorFotos, a_jpg, recortar_persona, tocando_borde


def _frame() -> np.ndarray:
    return np.full((360, 640, 3), 120, dtype=np.uint8)


def test_recortar_persona_incluye_margen_y_no_sale_del_cuadro():
    r = recortar_persona(_frame(), (100, 100, 200, 300))
    assert r is not None
    assert r.shape[0] > 200 and r.shape[1] > 100          # caja de 100x200 + margen
    borde = recortar_persona(_frame(), (-50, -20, 60, 80))
    assert borde is not None and borde.shape[0] <= 360 and borde.shape[1] <= 640


def test_recortar_persona_con_caja_vacia_devuelve_none():
    assert recortar_persona(_frame(), (10, 10, 12, 12)) is None


def test_tocando_borde():
    assert tocando_borde((0, 50, 80, 200), 640, 360)
    assert tocando_borde((300, 50, 400, 359), 640, 360)
    assert not tocando_borde((100, 50, 200, 250), 640, 360)


def test_a_jpg_limita_el_alto():
    import cv2
    jpg = a_jpg(np.zeros((1000, 400, 3), dtype=np.uint8))
    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[0] == 420


def test_se_queda_con_el_recorte_mas_grande_y_sin_tocar_el_borde():
    c = CapturadorFotos(storage=None, database_url="x", fps=2.0, min_seg=10)
    c.registrar(1, 1, _frame(), (100, 100, 140, 200))      # chica
    c.registrar(1, 2, _frame(), (100, 100, 180, 260))      # mas grande: gana
    c.registrar(1, 3, _frame(), (0, 0, 300, 350))          # la mas grande, pero toca el borde: se ignora
    c.registrar(1, 4, _frame(), (100, 100, 150, 220))      # mas chica que la mejor: se ignora
    area, _ = c._mejor[1]
    assert area == 80 * 160


def test_publica_solo_a_quien_llevo_el_tiempo_minimo_y_ya_tiene_persona_en_la_bd():
    c = CapturadorFotos(storage="st", database_url="db", fps=2.0, min_seg=10)   # 20 frames
    for n in range(1, 30):
        c.registrar(1, n, _frame(), (100, 100, 180, 260))            # lleva 28 frames: alcanza
    for n in range(1, 6):
        c.registrar(2, n, _frame(), (300, 100, 380, 260))            # solo 4 frames: no alcanza
    lanzados = []
    with patch("deteccion.pipeline.fotos.threading.Thread") as hilo:
        hilo.side_effect = lambda target, args, daemon: lanzados.append(args) or MagicMock()
        n = c.publicar_pendientes({1: 77, 2: 88}, frame_num=30)
    assert n == 1
    assert lanzados[0][2] == 77                                      # persona_db_id de la persona 1
    assert 1 in c._publicadas and 2 not in c._publicadas


def test_no_publica_si_la_persona_todavia_no_tiene_id_en_la_bd():
    c = CapturadorFotos(storage=None, database_url="db", fps=2.0, min_seg=10)
    for n in range(1, 30):
        c.registrar(1, n, _frame(), (100, 100, 180, 260))
    with patch("deteccion.pipeline.fotos.threading.Thread") as hilo:
        assert c.publicar_pendientes({}, frame_num=30) == 0
        hilo.assert_not_called()


def test_olvida_a_quien_se_fue_sin_llegar_al_minimo():
    c = CapturadorFotos(storage=None, database_url="db", fps=2.0, min_seg=10)
    for n in range(1, 4):
        c.registrar(5, n, _frame(), (100, 100, 180, 260))
    c.publicar_pendientes({5: 1}, frame_num=100)                    # paso mucho tiempo desde que se lo vio
    assert 5 not in c._mejor and 5 not in c._ultimo


# ── alertas "Persona posiblemente empleada" ──────────────────────────────────────────────────────────────

def _fila(**kw):
    base = {
        "cliente_id": 12, "fecha": date(2026, 10, 7), "minutos": 215,
        "primera_hora": datetime(2026, 10, 7, 8, 5), "ultima_hora": datetime(2026, 10, 7, 13, 40),
        "camara_id": 4, "foto_url": "https://x.supabase.co/storage/v1/object/public/b/evidencias/personas/persona_12.jpg",
        "revisado": False, "es_empleado": False,
    }
    base.update(kw)
    return base


def test_alerta_de_posible_empleado_abierta_con_foto_y_descripcion():
    from frontend.api.alertas import _alertas_posible_empleado
    cur = MagicMock()
    cur.fetchall.return_value = [_fila()]
    [a] = _alertas_posible_empleado(cur)
    assert a["tipo"] == "posible_empleado" and a["title"] == "Persona posiblemente empleada"
    assert a["status"] == "open" and a["persona_id"] == 12 and a["cam"] == 4
    assert a["foto"].endswith("persona_12.jpg")
    assert "3 h 35 min" in a["desc"] and "08:05" in a["desc"] and "13:40" in a["desc"]


def test_alerta_resuelta_segun_la_decision():
    from frontend.api.alertas import _alertas_posible_empleado
    cur = MagicMock()
    cur.fetchall.return_value = [_fila(revisado=True, es_empleado=True), _fila(cliente_id=13, revisado=True, es_empleado=False)]
    emp, cli = _alertas_posible_empleado(cur)
    assert emp["status"] == "resolved" and "excluida" in emp["desc"] and emp["es_empleado"] is True
    assert cli["status"] == "resolved" and "sigue contando" in cli["desc"]


def test_alerta_sin_foto_y_sin_columnas_nuevas():
    from frontend.api.alertas import _alertas_posible_empleado
    cur = MagicMock()
    cur.fetchall.return_value = [_fila(foto_url=None)]
    assert _alertas_posible_empleado(cur)[0]["foto"] is None
    # BD sin la migracion (columnas inexistentes): no rompe el resto de las alertas
    cur2 = MagicMock()
    cur2.execute.side_effect = Exception("column foto_url does not exist")
    assert _alertas_posible_empleado(cur2) == []
    cur2.connection.rollback.assert_called_once()

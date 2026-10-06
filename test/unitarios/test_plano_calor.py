"""Tests unitarios de frontend/api/plano_calor.py -- funciones puras (sin BD) que recortan el
calor de la camara fuente dentro de cada zona, para pintar el croquis de la tienda."""
import numpy as np
import pytest

from api.plano_calor import calor_en_zona, calor_por_zona, mascara_zona

# Zonas en espacio 1920x1080: mitad izquierda y mitad derecha del cuadro.
IZQ = [[0, 0], [960, 0], [960, 1080], [0, 1080]]
DER = [[960, 0], [1920, 0], [1920, 1080], [960, 1080]]


def _grilla(celdas: dict, n: int = 64) -> list:
    g = np.zeros((n, n))
    for (fila, col), v in celdas.items():
        g[fila, col] = v
    return g.tolist()


def test_mascara_cubre_la_fraccion_correcta_del_cuadro():
    mask = mascara_zona(IZQ, 64)
    assert mask.mean() == pytest.approx(0.5, abs=0.05)
    assert mask[:, :10].all() and not mask[:, -10:].any()


def test_recorte_conserva_posicion_dentro_de_la_zona():
    # Dos puntos calientes en la mitad derecha: el mas fuerte abajo, el flojo arriba.
    grilla = _grilla({(10, 50): 0.4, (50, 50): 1.0, (10, 5): 0.9})
    r = calor_en_zona(grilla, 100, DER)
    assert r["pico"] == pytest.approx(1.0)
    c0, f0 = r["origen"]
    assert r["grid"][50 - f0][50 - c0] == pytest.approx(1.0)
    assert r["grid"][10 - f0][50 - c0] == pytest.approx(0.4)
    assert r["bbox"] == {"x0": 960, "y0": 0, "x1": 1920, "y1": 1080}


def test_celdas_fuera_de_la_zona_quedan_en_cero():
    # El calor 0.9 de la mitad izquierda NO debe aparecer en el recorte de la derecha.
    r = calor_en_zona(_grilla({(10, 5): 0.9, (10, 50): 0.3}), 10, DER)
    assert r["pico"] == pytest.approx(0.3)
    assert max(max(fila) for fila in r["grid"]) == pytest.approx(0.3)


def test_share_es_el_porcentaje_de_detecciones_dentro_de_la_zona():
    r = calor_en_zona(_grilla({(10, 5): 1.0, (10, 50): 0.5}), 100, DER)
    assert r["share_pct"] == pytest.approx(100 * 50 / 150, abs=0.1)


def test_zona_fuera_del_cuadro_devuelve_none():
    assert calor_en_zona(_grilla({}), 1, [[3000, 3000], [3100, 3000], [3100, 3100]]) is None


def test_usa_solo_la_camara_fuente_de_cada_tipo():
    cam2 = {"matriz": _grilla({(5, 50): 0.5}), "valor_maximo": 1, "zonas": [{"tipo": "otro", "poligono": DER}]}
    cam4 = {"matriz": _grilla({(5, 50): 1.0}), "valor_maximo": 1,
            "zonas": [{"tipo": "otro", "poligono": DER}, {"tipo": "gondola", "poligono": DER}]}
    r = calor_por_zona({2: cam2, 4: cam4}, {"otro": 2, "gondola": 4})
    assert r["otro"]["camara_id"] == 2 and r["otro"]["pico"] == pytest.approx(0.5)   # no se mezcla con la 4
    assert r["gondola"]["camara_id"] == 4 and r["gondola"]["pico"] == pytest.approx(1.0)


def test_tipo_sin_camara_fuente_o_sin_esa_zona_no_aparece():
    cam4 = {"matriz": _grilla({(5, 50): 1.0}), "valor_maximo": 1, "zonas": [{"tipo": "gondola", "poligono": DER}]}
    assert calor_por_zona({4: cam4}, {"otro": 2, "caja": 4, "gondola": 4}).keys() == {"gondola"}
    assert calor_por_zona({}, {"gondola": 4}) == {}


# ── calor por hora del dia (promedio de todos los dias) ─────────────────────

from api.plano_calor import celdas_por_zona, rango_horario


def _fila(cam, dia, seg, xn, yn):
    return {"camara_id": cam, "dia": dia, "seg": seg, "xn": xn, "yn": yn}


def test_celdas_juntan_todos_los_dias_y_solo_la_camara_fuente():
    zonas = {4: [{"tipo": "gondola", "poligono": DER}], 2: [{"tipo": "otro", "poligono": DER}]}
    filas = [
        _fila(4, "2026-05-20", 3600, 0.75, 0.5),
        _fila(4, "2026-05-20", 3610, 0.75, 0.5),    # misma celda y mismo bloque: se suma
        _fila(4, "2026-05-21", 3650, 0.75, 0.5),    # OTRO dia, misma hora: se junta con los anteriores
        _fila(4, "2026-05-21", 3700, 0.25, 0.5),    # fuera de la zona (mitad izquierda)
        _fila(2, "2026-10-05", 3800, 0.75, 0.5),    # camara 2: no es la fuente de 'gondola'
    ]
    r = celdas_por_zona(filas, zonas, {"gondola": 4})
    assert list(r) == ["gondola"]
    g = r["gondola"]
    assert g["camara_id"] == 4 and g["dias"] == 2
    assert g["celdas"] == [[3600 // 300, 48, 32, 3]]           # [bloque de 5 min, columna, fila, cantidad]
    assert g["bbox"] == {"x0": 960, "y0": 0, "x1": 1920, "y1": 1080}


def test_celdas_combina_zonas_de_camaras_distintas_con_sus_propios_dias():
    zonas = {4: [{"tipo": "gondola", "poligono": DER}], 2: [{"tipo": "otro", "poligono": IZQ}]}
    filas = [_fila(4, "a", 100, 0.8, 0.2), _fila(4, "b", 100, 0.8, 0.2), _fila(2, "c", 200, 0.2, 0.2)]
    r = celdas_por_zona(filas, zonas, {"gondola": 4, "otro": 2})
    assert r["gondola"]["dias"] == 2 and r["otro"]["dias"] == 1     # cada camara cuenta SUS dias
    assert set(r) == {"gondola", "otro"}


def test_celdas_sin_datos_de_la_camara_no_devuelve_ese_tipo():
    zonas = {4: [{"tipo": "caja", "poligono": IZQ}]}
    assert celdas_por_zona([_fila(2, "a", 100, 0.5, 0.5)], zonas, {"caja": 4}) == {}
    assert celdas_por_zona([], zonas, {"caja": 4}) == {}


def test_rango_horario_redondea_a_la_hora_y_tiene_un_minimo():
    bloque = lambda h, m: (h * 3600 + m * 60) // 300
    z = {"caja": {"celdas": [[bloque(15, 30), 1, 1, 1], [bloque(18, 8), 1, 1, 1]]}}
    assert rango_horario(z) == {"desde": 15 * 60, "hasta": 19 * 60}
    assert rango_horario({"caja": {"celdas": [[bloque(9, 5), 1, 1, 1]]}}) == {"desde": 9 * 60, "hasta": 10 * 60}
    assert rango_horario({}) == {"desde": 8 * 60, "hasta": 22 * 60}


def test_dias_ignora_dias_casi_vacios_para_no_achicar_el_promedio():
    zonas = {4: [{"tipo": "caja", "poligono": IZQ}]}
    filas = [_fila(4, "lunes", 100 + i, 0.2, 0.2) for i in range(50)]          # dia con actividad
    filas += [_fila(4, "martes", 100 + i, 0.2, 0.2) for i in range(40)]        # otro dia con actividad
    filas += [_fila(4, "grabacion_cortada", 100, 0.2, 0.2)]                    # 1 posicion: no es un dia real
    assert celdas_por_zona(filas, zonas, {"caja": 4})["caja"]["dias"] == 2


# ── recorridos de clientes (flechas de trayectoria promedio) ────────────────

from api.plano_calor import tramos_por_zona


def _pos(cam, persona, dia, seg, xn, yn):
    return {"camara_id": cam, "persona_id": persona, "dia": dia, "seg": seg, "xn": xn, "yn": yn}


def test_tramo_de_una_persona_que_cruza_la_zona():
    zonas = {4: [{"tipo": "gondola", "poligono": DER}]}
    filas = [_pos(4, 1, "d1", 3600 + 10 * i, 0.55 + 0.05 * i, 0.5) for i in range(8)]   # camina de izq a der en la zona
    r = tramos_por_zona(filas, zonas, {"gondola": 4})["gondola"]
    assert r["camara_id"] == 4 and r["dias"] == 1
    assert len(r["tramos"]) == 1
    minuto, pts = r["tramos"][0]
    assert minuto == 60 and len(pts) == 12                      # 6 puntos x (x, y)
    assert pts[0] < pts[-2]                                     # avanza hacia la derecha
    assert pts[0] == 550 and pts[-2] == 900


def test_gente_parada_no_genera_tramo():
    zonas = {4: [{"tipo": "gondola", "poligono": DER}]}
    filas = [_pos(4, 1, "d1", 100 + 10 * i, 0.75 + 0.001 * (i % 2), 0.5) for i in range(10)]
    assert tramos_por_zona(filas, zonas, {"gondola": 4}) == {}


def test_un_hueco_largo_parte_el_recorrido_en_dos_tramos():
    zonas = {4: [{"tipo": "gondola", "poligono": DER}]}
    a = [_pos(4, 1, "d1", 100 + 10 * i, 0.55 + 0.06 * i, 0.5) for i in range(6)]
    b = [_pos(4, 1, "d1", 1000 + 10 * i, 0.55 + 0.06 * i, 0.5) for i in range(6)]       # 15 min despues
    assert len(tramos_por_zona(a + b, zonas, {"gondola": 4})["gondola"]["tramos"]) == 2


def test_solo_cuentan_las_posiciones_dentro_de_la_zona_de_la_camara_fuente():
    zonas = {4: [{"tipo": "gondola", "poligono": DER}], 2: [{"tipo": "otro", "poligono": DER}]}
    fuera = [_pos(4, 1, "d1", 100 + 10 * i, 0.1 + 0.06 * i, 0.5) for i in range(6)]     # mitad izquierda: fuera de la zona
    otra_camara = [_pos(2, 2, "d1", 100 + 10 * i, 0.55 + 0.06 * i, 0.5) for i in range(6)]
    r = tramos_por_zona(fuera + otra_camara, zonas, {"gondola": 4, "otro": 2})
    assert "gondola" not in r                                   # camino fuera de la zona
    assert r["otro"]["camara_id"] == 2                          # cada tipo usa solo su camara fuente


def test_dos_zonas_de_la_misma_camara_se_reparten_los_tramos():
    zonas = {4: [{"tipo": "gondola", "poligono": DER}, {"tipo": "caja", "poligono": IZQ}]}
    der = [_pos(4, 1, "d1", 100 + 10 * i, 0.55 + 0.06 * i, 0.5) for i in range(6)]
    izq = [_pos(4, 2, "d1", 100 + 10 * i, 0.05 + 0.06 * i, 0.5) for i in range(6)]
    r = tramos_por_zona(der + izq, zonas, {"gondola": 4, "caja": 4})
    assert len(r["gondola"]["tramos"]) == 1 and len(r["caja"]["tramos"]) == 1

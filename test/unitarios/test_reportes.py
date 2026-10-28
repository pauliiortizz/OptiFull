"""Tests de los endpoints /api/reportes/* del dashboard (frontend/api/reportes.py) y de detectar_picos().
La base de datos se simula con BDFalsa (conftest.py)."""
from datetime import date, datetime

import pytest

from api import app
from api import reportes as m

ENDPOINTS = ["tendencia-semanal", "permanencia-semanal", "congestion-horaria", "promedio-diario",
             "posibles-empleados", "conversion-compra", "permanencia-por-zona"]


@pytest.fixture
def cliente():
    return app.test_client()


@pytest.fixture
def con_bd(monkeypatch, bd):
    monkeypatch.setattr(m, "_get_conn", lambda: bd)
    return bd


def get(cliente, endpoint, **params):
    r = cliente.get(f"/api/reportes/{endpoint}", query_string=params)
    return r.status_code, r.get_json()


# ── Comportamiento comun a todos los endpoints ────────────────────────────────

@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_sin_base_de_datos_responde_vacio_marcado_sin_bd(cliente, monkeypatch, endpoint):
    monkeypatch.setattr(m, "_get_conn", lambda: None)
    status, datos = get(cliente, endpoint)
    assert status == 200
    assert datos["fuente"] == "sin_bd"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_error_de_la_base_de_datos_responde_500(cliente, con_bd, endpoint):
    con_bd.error = RuntimeError("se cortó la conexión")
    status, datos = get(cliente, endpoint)
    assert status == 500
    assert datos["error"] == "se cortó la conexión"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_sin_filas_responde_ceros_o_vacio(cliente, con_bd, endpoint):
    status, datos = get(cliente, endpoint)
    assert status == 200 and datos["fuente"] == "db"


# ── Tendencia y permanencia semanal ───────────────────────────────────────────

@pytest.mark.parametrize("endpoint", ["tendencia-semanal", "promedio-diario"])
def test_el_dia_de_las_personas_es_el_de_la_deteccion_y_no_el_de_grabacion_del_video(cliente, con_bd, endpoint):
    """Un analisis que arranca el sabado y sigue el domingo: las personas vistas el domingo deben contarse el domingo,
    aunque 'sesiones_video.inicio' (la fecha de grabacion del video) sea del sabado. Antes la tendencia agrupaba por
    s.inicio y el domingo aparecia 'sin datos' mientras la congestion (por timestamp de la trayectoria) si tenia."""
    con_bd.responder("WITH por_dia", [{"fecha": date(2026, 10, 25), "valor": 5, "cantidad": 5,
                                       "promedio": 5, "dias_con_datos": 1}])
    get(cliente, endpoint)
    sql, _ = con_bd.consultas[0]
    assert "FROM trayectorias t" in sql and "ts::date" in sql
    assert "s.inicio" not in sql


@pytest.mark.parametrize("endpoint, fragmento", [
    ("tendencia-semanal", "WITH por_dia"),
    ("permanencia-semanal", "WITH permanencia_por_cliente_dia"),
])
def test_semanal_serie_diaria_y_promedio_por_dia_de_semana_en_el_rango(cliente, con_bd, endpoint, fragmento):
    con_bd.responder(fragmento, [
        {"fecha": date(2026, 10, 11), "valor": 6},   # domingo
        {"fecha": date(2026, 10, 12), "valor": 3},   # lunes
        {"fecha": date(2026, 10, 18), "valor": 8},   # domingo
    ])
    _, datos = get(cliente, endpoint, desde="2026-10-11", hasta="2026-10-18")
    assert datos["labels"][0] == "Lun" and datos["labels"][6] == "Dom"
    assert datos["promedio"] == [3, 0, 0, 0, 0, 0, 7]            # domingos: (6 + 8) / 2
    assert datos["dias_con_datos"] == [1, 0, 0, 0, 0, 0, 2]
    assert datos["por_fecha"] == [{"fecha": "2026-10-11", "valor": 6}, {"fecha": "2026-10-12", "valor": 3},
                                  {"fecha": "2026-10-18", "valor": 8}]
    _, params = con_bd.consultas[0]
    assert (params["desde"], params["hasta"]) == (date(2026, 10, 11), date(2026, 10, 18))


@pytest.mark.parametrize("endpoint, fragmento", [("promedio-diario", "WITH por_dia"), ("conversion-compra", "WITH por_persona_dia")])
def test_promedio_diario_y_conversion_pasan_el_rango_del_filtro(cliente, con_bd, endpoint, fragmento):
    get(cliente, endpoint, desde="2026-10-23", hasta="2026-10-23")
    _, params = con_bd.consultas[0]
    assert (params["desde"], params["hasta"]) == (date(2026, 10, 23), date(2026, 10, 23))


# ── Congestion horaria ────────────────────────────────────────────────────────

def test_congestion_arma_la_matriz_y_el_pico_y_pasa_el_rango_de_fechas(cliente, con_bd):
    con_bd.responder("WITH ocupacion", [
        {"fecha": date(2026, 10, 2), "hora": 20, "cantidad": 10},   # viernes 20 hs
        {"fecha": date(2026, 10, 9), "hora": 20, "cantidad": 13},   # otro viernes 20 hs
        {"fecha": date(2026, 10, 6), "hora": 9, "cantidad": 2},     # martes 9 hs
    ])
    _, datos = get(cliente, "congestion-horaria", desde="2026-10-01", hasta="2026-10-09")
    assert datos["matriz"][4][20] == 12 and datos["dias_con_datos"][4][20] == 2   # promedio de los viernes (11,5 -> 12)
    assert datos["pico"] == {"dia": "Vie", "hora_inicio": 20, "hora_fin": 20, "promedio": 12}
    assert len(datos["picos"]) == 2
    # Grilla de cada fecha (la usa el dashboard con Hoy / 7 dias) y sus picos, con la fecha como 'dia'
    assert [f["fecha"] for f in datos["por_fecha"]] == ["2026-10-02", "2026-10-06", "2026-10-09"]
    assert datos["por_fecha"][2]["horas"][20] == 13
    assert datos["picos_por_fecha"][0] == {"dia": "2026-10-09", "hora_inicio": 20, "hora_fin": 20, "promedio": 13}
    _, params = con_bd.consultas[0]
    assert (params["desde"], params["hasta"]) == (date(2026, 10, 1), date(2026, 10, 9))


def test_congestion_sin_datos_no_tiene_pico(cliente, con_bd):
    _, datos = get(cliente, "congestion-horaria")
    assert datos["pico"] is None and datos["picos"] == []


# ── Promedio diario y conversion ──────────────────────────────────────────────

@pytest.mark.parametrize("fila, promedio, dias", [
    ({"promedio": 18, "dias_con_datos": 4}, 18, 4),
    ({"promedio": None, "dias_con_datos": 0}, None, 0),   # sin dias con datos no hay promedio
])
def test_promedio_diario(cliente, con_bd, fila, promedio, dias):
    con_bd.responder("WITH por_dia", [fila])
    _, datos = get(cliente, "promedio-diario")
    assert (datos["promedio"], datos["dias_con_datos"]) == (promedio, dias)


@pytest.mark.parametrize("fila, pct", [
    ({"promedio_compraron": 3, "promedio_no_compraron": 1, "dias_con_datos": 2}, 75.0),
    ({"promedio_compraron": None, "promedio_no_compraron": 5, "dias_con_datos": 1}, 0.0),
    ({"promedio_compraron": 0, "promedio_no_compraron": 0, "dias_con_datos": 1}, None),   # sin clientes: sin %
    ({"promedio_compraron": None, "promedio_no_compraron": None, "dias_con_datos": 0}, None),
])
def test_conversion_de_compra(cliente, con_bd, fila, pct):
    con_bd.responder("WITH por_persona_dia", [fila])
    _, datos = get(cliente, "conversion-compra")
    assert datos["pct_conversion"] == pct


# ── Posibles empleados ────────────────────────────────────────────────────────

def test_posibles_empleados_usa_el_umbral_en_segundos_y_formatea_horas(cliente, con_bd):
    con_bd.responder("HAVING SUM(segundos) >= %(umbral)s", [{
        "cliente_id": 7, "fecha": date(2026, 10, 3), "apariciones": 4, "minutos_totales": 245,
        "primera_hora": datetime(2026, 10, 3, 8, 5), "ultima_hora": datetime(2026, 10, 3, 12, 40, 9),
    }])
    _, datos = get(cliente, "posibles-empleados")
    assert datos["umbral_horas"] == m.UMBRAL_HORAS_POSIBLE_EMPLEADO
    assert datos["candidatos"][0] == {
        "cliente_id": 7, "fecha": "2026-10-03", "apariciones": 4, "minutos_totales": 245,
        "primera_hora": "08:05:00", "ultima_hora": "12:40:09"}
    _, params = con_bd.consultas[0]
    assert params["umbral"] == m.UMBRAL_HORAS_POSIBLE_EMPLEADO * 3600


# ── Permanencia por zona ──────────────────────────────────────────────────────

def test_permanencia_por_zona_ordena_por_minutos_por_visitante(cliente, con_bd):
    con_bd.responder("FROM trayectorias t", [
        # 'segundos' = tiempo visto ya sumado en SQL (huecos cortos cubiertos, ver cargar_permanencias_db)
        {"tipo": "caja", "cliente_id": 1, "segundos": 60},       # 1 min
        {"tipo": "gondola", "cliente_id": 1, "segundos": 300},   # 5 min
        {"tipo": "gondola", "cliente_id": 2, "segundos": 180},   # 3 min
        {"tipo": "deposito", "cliente_id": 3, "segundos": 60},   # tipo sin nombre: se muestra tal cual
    ])
    _, datos = get(cliente, "permanencia-por-zona")
    zonas = datos["zonas"]
    assert [z["nombre"] for z in zonas] == ["Góndolas", "Caja", "deposito"]
    gondolas = zonas[0]
    assert (gondolas["permanencia_promedio_min"], gondolas["permanencia_maxima_min"]) == (4.0, 5.0)
    assert (gondolas["visitantes"], gondolas["minutos_totales"], gondolas["pct"]) == (2, 8.0, 80)


# ── detectar_picos ────────────────────────────────────────────────────────────

DIAS = ["Lun", "Mar"]


def _fila(valores):
    fila = [0] * 24
    for h, v in valores.items():
        fila[h] = v
    return fila


def test_un_dia_puede_tener_dos_picos_separados_por_un_valle():
    fila = _fila({9: 5, 10: 8, 11: 3, 18: 6, 19: 7})
    picos = m.detectar_picos([fila, [0] * 24], [[1] * 24, [0] * 24], DIAS)
    assert [(p["hora_inicio"], p["hora_fin"], p["promedio"]) for p in picos] == [(10, 10, 8), (19, 19, 7)]


def test_horas_consecutivas_iguales_se_agrupan_en_un_rango():
    fila = _fila({14: 9, 15: 9})
    picos = m.detectar_picos([fila], [[1] * 24], DIAS)
    assert picos == [{"dia": "Lun", "hora_inicio": 14, "hora_fin": 15, "promedio": 9}]


@pytest.mark.parametrize("valor, es_pico", [(6, True), (5, False)])   # umbral 60 % de 10 = 6
def test_umbral_del_pico_valor_limite(valor, es_pico):
    fila = _fila({8: 10, 15: valor})
    picos = m.detectar_picos([fila], [[1] * 24], DIAS)
    assert any(p["hora_inicio"] == 15 for p in picos) is es_pico


def test_horas_sin_datos_no_cuentan_como_vecinas():
    fila = _fila({0: 4, 23: 4, 12: 1})
    con_datos = [[1 if h in (0, 12, 23) else 0 for h in range(24)]]
    picos = m.detectar_picos([fila], con_datos, DIAS)
    assert {p["hora_inicio"] for p in picos} == {0, 23}   # bordes del dia: sin vecino de un lado


def test_dia_sin_datos_no_tiene_picos():
    assert m.detectar_picos([[0] * 24], [[0] * 24], DIAS) == []

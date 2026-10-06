"""Tests unitarios del filtro por rango de fechas del dashboard (frontend/api/db.py): parse_rango()
y el fragmento SQL que lo aplica. Funciones puras, sin BD."""
from datetime import date

from api.db import parse_rango, sql_rango


def test_parse_rango_valido():
    assert parse_rango("2026-10-01", "2026-10-05") == (date(2026, 10, 1), date(2026, 10, 5))


def test_parse_rango_un_dia():
    assert parse_rango("2026-10-05", "2026-10-05") == (date(2026, 10, 5), date(2026, 10, 5))


def test_parse_rango_vacio_o_ausente_es_sin_limite():
    assert parse_rango(None, None) == (None, None)
    assert parse_rango("", "") == (None, None)


def test_parse_rango_invalido_se_ignora_ese_lado():
    assert parse_rango("no-es-fecha", "2026-10-05") == (None, date(2026, 10, 5))
    assert parse_rango("2026-13-45", None) == (None, None)
    assert parse_rango("2026-10-01", "ayer") == (date(2026, 10, 1), None)


def test_parse_rango_al_reves_se_intercambia():
    assert parse_rango("2026-10-05", "2026-10-01") == (date(2026, 10, 1), date(2026, 10, 5))


def test_sql_rango_usa_la_columna_y_acepta_limites_nulos():
    sql = sql_rango("p.primera_deteccion")
    assert "p.primera_deteccion::date >= %(desde)s::date" in sql
    assert "p.primera_deteccion::date <= %(hasta)s::date" in sql
    assert sql.count("IS NULL") == 2     # cada lado puede faltar

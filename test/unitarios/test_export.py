"""Tests de la exportacion del reporte de permanencia (frontend/api/export.py): /export/csv y /export/pdf,
con la base de datos o con el CSV local como respaldo."""
import csv
import io

import pytest

from api import app
from api import export as m

FILAS = [{"id": 1, "cliente_id": 1, "entrada": "10:00:00", "salida": "10:05:00", "duracion_seg": 300, "duracion_min": 5.0},
         {"id": 2, "cliente_id": 1, "entrada": "11:00:00", "salida": "11:01:00", "duracion_seg": 60, "duracion_min": 1.0}]
PERMANENCIAS = [{"cliente_id": 1, "entrada": "10:00:00", "salida": "11:01:00", "duracion_seg": 360, "duracion_min": 6.0}]


@pytest.fixture
def cliente():
    return app.test_client()


@pytest.fixture
def desde_bd(monkeypatch):
    monkeypatch.setattr(m, "cargar_db", lambda: FILAS)
    monkeypatch.setattr(m, "cargar_permanencias_db", lambda: PERMANENCIAS)


@pytest.fixture
def desde_csv(monkeypatch):
    monkeypatch.setattr(m, "cargar_db", lambda: None)
    monkeypatch.setattr(m, "cargar_csv", lambda: FILAS)


def leer_csv(r):
    return list(csv.reader(io.StringIO(r.data.decode("utf-8-sig"))))


def test_csv_desde_la_bd_detalla_un_cliente_por_fila(cliente, desde_bd):
    r = cliente.get("/api/export/csv")
    assert r.mimetype == "text/csv" and r.headers["Content-Disposition"].endswith('.csv"')
    filas = leer_csv(r)
    assert ["# Fuente: Base de datos"] in filas
    assert ["Personas totales", "2"] in filas and ["Personas unicas", "1"] in filas
    detalle = filas[filas.index(["ID", "Entrada", "Salida", "Duracion (seg)", "Duracion (min)"]) + 1:]
    assert detalle == [["1", "10:00:00", "11:01:00", "360", "6.0"]]   # permanencia ya sumada entre visitas


def test_csv_desde_el_csv_local_detalla_cada_registro(cliente, desde_csv):
    filas = leer_csv(cliente.get("/api/export/csv"))
    assert ["# Fuente: CSV local"] in filas
    detalle = filas[filas.index(["ID", "Entrada", "Salida", "Duracion (seg)", "Duracion (min)"]) + 1:]
    assert len(detalle) == 2


@pytest.mark.parametrize("formato", ["csv", "pdf"])
def test_sin_bd_ni_csv_responde_500(cliente, monkeypatch, formato):
    def sin_csv():
        raise FileNotFoundError("permanencia.csv")

    monkeypatch.setattr(m, "cargar_db", lambda: None)
    monkeypatch.setattr(m, "cargar_csv", sin_csv)
    r = cliente.get(f"/api/export/{formato}")
    assert r.status_code == 500 and "permanencia.csv" in r.get_json()["error"]


@pytest.mark.parametrize("fuente", ["desde_bd", "desde_csv"])
def test_pdf(cliente, request, fuente):
    request.getfixturevalue(fuente)
    r = cliente.get("/api/export/pdf")
    assert r.mimetype == "application/pdf" and r.data.startswith(b"%PDF")
    assert r.headers["Content-Disposition"].endswith('.pdf"')

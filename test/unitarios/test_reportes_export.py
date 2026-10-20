"""Tests de los endpoints GET /api/reportes/opciones y POST /api/reportes/exportar
(frontend/api/reportes_export.py). Clases de equivalencia del body: metricas, formato, fechas y camaras.
La base de datos se simula con BDFalsa (conftest.py)."""
from datetime import date

import pytest

from api import app
from api import reportes_export as re_


@pytest.fixture
def cliente():
    return app.test_client()


@pytest.fixture
def con_bd(monkeypatch, bd):
    bd.responder("FROM camaras", [(1, "Caja"), (2, "Salón")])
    bd.responder("FROM sesiones_video", [(date(2026, 9, 1), date(2026, 10, 7))])
    monkeypatch.setattr(re_, "_get_conn", lambda: bd)
    return bd


@pytest.fixture
def sin_bd(monkeypatch):
    monkeypatch.setattr(re_, "_get_conn", lambda: None)


def exportar(cliente, **body):
    return cliente.post("/api/reportes/exportar", json={"metricas": ["stock_faltantes"], "formato": "pdf", **body})


# ── /reportes/opciones ────────────────────────────────────────────────────────

def test_opciones_devuelve_catalogo_camaras_y_rango_de_fechas(cliente, con_bd):
    r = cliente.get("/api/reportes/opciones")
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["camaras"] == [{"id": 1, "nombre": "Caja"}, {"id": 2, "nombre": "Salón"}]
    assert (datos["fecha_min"], datos["fecha_max"]) == ("2026-09-01", "2026-10-07")
    assert {f["id"] for f in datos["formatos"]} == {"pdf", "xlsx", "csv", "png"}
    assert con_bd.cerrada


def test_opciones_sin_sesiones_devuelve_fechas_nulas(cliente, monkeypatch, bd):
    bd.responder("FROM sesiones_video", [(None, None)])
    monkeypatch.setattr(re_, "_get_conn", lambda: bd)
    datos = cliente.get("/api/reportes/opciones").get_json()
    assert datos["fecha_min"] is None and datos["camaras"] == []


def test_opciones_sin_base_de_datos_responde_503(cliente, sin_bd):
    assert cliente.get("/api/reportes/opciones").status_code == 503


def test_opciones_error_en_la_consulta_responde_500(cliente, monkeypatch, bd):
    bd.error = RuntimeError("timeout")
    monkeypatch.setattr(re_, "_get_conn", lambda: bd)
    r = cliente.get("/api/reportes/opciones")
    assert r.status_code == 500 and bd.cerrada


# ── /reportes/exportar: validacion del body (clases invalidas -> 400) ─────────

@pytest.mark.parametrize("body, mensaje", [
    ({"metricas": None}, "al menos una métrica"),
    ({"metricas": []}, "al menos una métrica"),
    ({"metricas": "stock_faltantes"}, "al menos una métrica"),          # no es lista
    ({"metricas": ["stock_faltantes", "inventada"]}, "Métricas desconocidas: inventada"),
    ({"formato": "docx"}, "Formato inválido"),
    ({"formato": None}, "Formato inválido"),
    ({"desde": "07/10/2026"}, "'desde' debe tener formato YYYY-MM-DD"),
    ({"hasta": "2026-13-01"}, "'hasta' debe tener formato YYYY-MM-DD"),
    ({"camaras": ["dos"]}, "'camaras' debe ser una lista de ids numéricos"),
    ({"camaras": [[1]]}, "'camaras' debe ser una lista de ids numéricos"),
    ({"desde": "2026-10-08", "hasta": "2026-10-07"}, "'desde' no puede ser posterior"),   # limite: 1 dia despues
], ids=["sin-metricas", "lista-vacia", "no-es-lista", "desconocida", "formato-invalido", "sin-formato",
        "desde-formato", "hasta-mes-13", "camara-texto", "camara-lista", "desde-mayor"])
def test_exportar_body_invalido_responde_400(cliente, con_bd, body, mensaje):
    r = exportar(cliente, **body)
    assert r.status_code == 400
    assert mensaje in r.get_json()["error"]
    assert con_bd.consultas == []   # se valida antes de tocar la base de datos


def test_exportar_sin_body_json_responde_400(cliente):
    r = cliente.post("/api/reportes/exportar", data="no es json", content_type="text/plain")
    assert r.status_code == 400


# ── /reportes/exportar: casos validos ─────────────────────────────────────────

@pytest.mark.parametrize("formato, mime", [
    ("pdf", "application/pdf"),
    ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
])
def test_exportar_genera_el_archivo_como_descarga(cliente, con_bd, formato, mime):
    con_bd.responder("FROM productos ORDER BY nombre", [{"sku": "A", "nombre": "Agua", "categoria": "-", "cantidad": 0}])
    r = exportar(cliente, formato=formato, desde="2026-10-07", hasta="2026-10-07", camaras=["2"])   # desde == hasta: valido
    assert r.status_code == 200
    assert r.mimetype == mime
    disposicion = r.headers["Content-Disposition"]
    assert disposicion.startswith('attachment; filename="optifull_reporte_') and disposicion.endswith(f'.{formato}"')
    assert r.headers["Cache-Control"] == "no-store"
    assert con_bd.cerrada


def test_exportar_usa_nombre_generico_para_camaras_desconocidas(cliente, con_bd, monkeypatch):
    recibido = {}

    def generador(metricas, filtros, camaras_txt):
        recibido["camaras"] = camaras_txt
        return b"ok", "text/plain", "txt"

    monkeypatch.setitem(re_.GENERADORES, "pdf", generador)
    exportar(cliente, camaras=[2, 9])
    assert recibido["camaras"] == "Salón, Cámara 9"


@pytest.mark.parametrize("formato, mensaje", [
    ("csv", "no tienen tablas de datos para el CSV"),
    ("png", "No hay gráficos para exportar"),
])
def test_exportar_sin_contenido_para_el_formato_responde_422(cliente, con_bd, formato, mensaje):
    r = exportar(cliente, formato=formato, metricas=["personas_flujo"])   # sin datos: ni tablas ni graficos
    assert r.status_code == 422
    assert mensaje in r.get_json()["error"]


# ── /reportes/exportar: fallas de infraestructura ─────────────────────────────

def test_exportar_sin_base_de_datos_responde_503(cliente, sin_bd):
    assert exportar(cliente).status_code == 503


def test_exportar_error_al_consultar_responde_500(cliente, monkeypatch, bd):
    bd.error = RuntimeError("se cayó la conexión")
    monkeypatch.setattr(re_, "_get_conn", lambda: bd)
    r = exportar(cliente)
    assert r.status_code == 500
    assert "No se pudieron consultar los datos" in r.get_json()["error"]


def test_exportar_error_al_generar_el_archivo_responde_500(cliente, con_bd, monkeypatch):
    def roto(*_):
        raise ValueError("fuente rota")

    monkeypatch.setitem(re_.GENERADORES, "pdf", roto)
    r = exportar(cliente)
    assert r.status_code == 500
    assert r.get_json()["error"] == "No se pudo generar el archivo PDF: fuente rota"

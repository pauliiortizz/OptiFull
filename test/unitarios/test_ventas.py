"""Tests del endpoint GET /api/ventas (frontend/api/ventas.py): tickets vendidos en caja con sus productos,
total y fecha. La base de datos se simula con BDFalsa."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from api import app
from api import ventas as m


@pytest.fixture
def cliente():
    return app.test_client()


@pytest.fixture
def con_bd(monkeypatch, bd):
    monkeypatch.setattr(m, "_get_conn", lambda: bd)
    return bd


def fila(ticket, venta_id, total, fecha, linea, sku, nombre, cantidad, precio):
    return {"ticket": ticket, "venta_id": venta_id, "total": total, "fecha": fecha, "linea": linea,
            "sku": sku, "nombre": nombre, "cantidad": cantidad, "precio_unitario": precio}


HOY = datetime(2026, 10, 21, 15, 30, tzinfo=timezone.utc)
AYER = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)

FILAS = [
    # ticket 2: dos productos
    fila(2, 2, Decimal("1250.00"), HOY, 10, "A", "Agua", 2, Decimal("500.00")),
    fila(2, 2, Decimal("1250.00"), HOY, 11, "B", "Barra", 1, Decimal("250.00")),
    # transaccion vieja sin ticket (venta_id NULL): ticket = -id, total con el precio actual
    fila(-7, None, None, AYER, 7, "C", "Chicle", 3, Decimal("100.00")),
]


def test_agrupa_los_productos_de_cada_ticket(cliente, con_bd):
    con_bd.responder("FROM transacciones", FILAS)
    datos = cliente.get("/api/ventas").get_json()
    assert [v["id"] for v in datos["ventas"]] == [2, None]
    t2 = datos["ventas"][0]
    assert t2["total"] == 1250.0 and t2["fecha"] == HOY.isoformat()
    assert t2["items"] == [
        {"sku": "A", "nombre": "Agua", "cantidad": 2, "precio_unitario": 500.0, "subtotal": 1000.0},
        {"sku": "B", "nombre": "Barra", "cantidad": 1, "precio_unitario": 250.0, "subtotal": 250.0},
    ]


def test_venta_sin_ticket_calcula_el_total_con_el_precio_actual(cliente, con_bd):
    con_bd.responder("FROM transacciones", FILAS)
    vieja = cliente.get("/api/ventas").get_json()["ventas"][1]
    assert vieja["total"] == 300.0 and len(vieja["items"]) == 1


def test_resumen(cliente, con_bd):
    con_bd.responder("FROM transacciones", FILAS)
    assert cliente.get("/api/ventas").get_json()["resumen"] == {
        "tickets": 2, "total": 1550.0, "unidades": 6, "ticket_promedio": 775.0}


def test_sin_ventas(cliente, con_bd):
    assert cliente.get("/api/ventas").get_json() == {
        "ventas": [], "resumen": {"tickets": 0, "total": 0, "unidades": 0, "ticket_promedio": 0}}


def test_producto_sin_precio_ni_nombre(cliente, con_bd):
    con_bd.responder("FROM transacciones", [fila(3, 3, Decimal("0"), HOY, 1, "X", None, 1, None)])
    item = cliente.get("/api/ventas").get_json()["ventas"][0]["items"][0]
    assert item == {"sku": "X", "nombre": "X", "cantidad": 1, "precio_unitario": None, "subtotal": None}


def test_limite_corta_en_tickets_completos(cliente, con_bd):
    con_bd.responder("FROM transacciones", FILAS)
    ventas = cliente.get("/api/ventas?limite=1").get_json()["ventas"]
    assert len(ventas) == 1 and len(ventas[0]["items"]) == 2


def test_filtro_de_fechas_se_pasa_a_la_consulta(cliente, con_bd):
    cliente.get("/api/ventas?desde=2026-10-01&hasta=2026-10-21")
    _, params = con_bd.consultas[0]
    assert (str(params["desde"]), str(params["hasta"])) == ("2026-10-01", "2026-10-21")
    assert params["zona"] == "America/Argentina/Cordoba"


@pytest.mark.parametrize("query", ["desde=ayer", "hasta=2026-13-01", "limite=muchos"])
def test_parametros_invalidos_responden_400(cliente, con_bd, query):
    assert cliente.get(f"/api/ventas?{query}").status_code == 400
    assert con_bd.consultas == []


def test_sin_base_de_datos_responde_503(cliente, monkeypatch):
    monkeypatch.setattr(m, "_get_conn", lambda: None)
    assert cliente.get("/api/ventas").status_code == 503


def test_error_de_la_base_de_datos_responde_500(cliente, con_bd):
    con_bd.error = RuntimeError("timeout")
    r = cliente.get("/api/ventas")
    assert r.status_code == 500 and r.get_json() == {"error": "timeout"}

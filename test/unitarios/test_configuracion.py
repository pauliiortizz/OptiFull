"""Tests de frontend/api/configuracion.py (/api/configuracion) y de las alertas de espera en caja que usan
su umbral (alertas._alertas_caja). La base de datos se simula con BDFalsa (conftest.py)."""
from datetime import datetime, timedelta

import pytest

import api
from api import alertas, configuracion

CAJA = [[100, 100], [200, 100], [200, 200], [100, 200]]   # poligono de la zona de caja (px)
GUARDADO = {"umbrales": {"wait": 2.5},
            "sucursal": {"nombre": "Local", "direccion": "Calle 1", "horario": "8 a 20"}, "push": False}


@pytest.fixture
def cliente():
    return api.app.test_client()


# ── /api/configuracion ───────────────────────────────────────────────────────

def test_get_sin_base_devuelve_los_valores_por_defecto(cliente, monkeypatch):
    monkeypatch.setattr(configuracion, "_get_conn", lambda: None)
    assert cliente.get("/api/configuracion").get_json() == configuracion.POR_DEFECTO


def test_get_con_la_tabla_inexistente_devuelve_los_valores_por_defecto(cliente, monkeypatch, bd):
    bd.error = RuntimeError('relation "configuracion" does not exist')
    monkeypatch.setattr(configuracion, "_get_conn", lambda: bd)
    assert cliente.get("/api/configuracion").get_json() == configuracion.POR_DEFECTO
    assert bd.rollbacks == 1 and bd.cerrada


def test_get_devuelve_lo_guardado_completando_lo_que_falte(cliente, monkeypatch, bd):
    bd.responder("FROM configuracion", [({"umbrales": {"queue": 3, "wait": 7}},)])   # queue: umbral que ya no se usa
    monkeypatch.setattr(configuracion, "_get_conn", lambda: bd)
    d = cliente.get("/api/configuracion").get_json()
    assert d["umbrales"] == {"wait": 7}
    assert d["sucursal"] == configuracion.POR_DEFECTO["sucursal"] and d["push"] is True


def test_put_guarda_y_devuelve_la_configuracion(cliente, monkeypatch, bd):
    monkeypatch.setattr(configuracion, "_get_conn", lambda: bd)
    r = cliente.put("/api/configuracion", json={**GUARDADO, "sucursal": {**GUARDADO["sucursal"], "nombre": "  Local  "}})
    assert r.status_code == 200
    assert r.get_json() == GUARDADO   # el nombre se guarda sin espacios de mas
    insert = next(p for sql, p in bd.consultas if "INSERT INTO configuracion" in sql)
    assert '"wait": 2.5' in insert[0] and bd.commits == 1


@pytest.mark.parametrize("cambio", [
    {"umbrales": {"wait": 0.5}},
    {"umbrales": {"wait": 15.5}},
    {"umbrales": {"wait": 4.2}},
    {"umbrales": {"wait": "4"}},
    {"umbrales": {"wait": True}},
    {"sucursal": {"nombre": " "}},
    {"push": "si"},
])
def test_put_rechaza_valores_invalidos_sin_tocar_la_base(cliente, monkeypatch, bd, cambio):
    monkeypatch.setattr(configuracion, "_get_conn", lambda: bd)
    r = cliente.put("/api/configuracion", json={**GUARDADO, **cambio})
    assert r.status_code == 400 and "error" in r.get_json()
    assert bd.consultas == []


def test_put_sin_base_responde_503(cliente, monkeypatch):
    monkeypatch.setattr(configuracion, "_get_conn", lambda: None)
    assert cliente.put("/api/configuracion", json=GUARDADO).status_code == 503


# ── Alertas de espera y de cola en caja ──────────────────────────────────────

def _puntos(persona, inicio, n, x=150, y=150, sesion=11):
    return [{"persona_id": persona, "ts": inicio + timedelta(seconds=i * 10), "x": x, "y": y, "sesion_id": sesion}
            for i in range(n)]


def _bd_caja(bd, puntos, umbrales, resueltas=()):
    bd.responder("FROM configuracion", [{"datos": {"umbrales": umbrales}}])
    bd.responder("z.tipo = 'caja'", [{"camara_id": 2, "poligono": CAJA}])
    bd.responder("SELECT frame_w", [])
    bd.responder("t.centroide_x", puntos)
    bd.responder("SELECT id FROM alertas_caja_resueltas", [{"id": i} for i in resueltas])
    bd.responder("SELECT id, inicio FROM sesiones_video", [{"id": 11, "inicio": datetime(2026, 10, 28, 9, 59)}])
    return bd.cursor()


def test_espera_que_llega_al_umbral_levanta_una_alerta(bd):
    t0 = datetime(2026, 10, 28, 10)
    puntos = _puntos(1, t0, 12) + _puntos(2, t0, 3)   # 120 s y 30 s de espera
    lista = alertas._alertas_caja(_bd_caja(bd, puntos, {"wait": 2}))
    assert len(lista) == 1
    a = lista[0]
    assert (a["tipo"], a["sev"], a["title"], a["zone"], a["status"], a["persona_id"]) == (
        "espera_excesiva", "warn", "Espera larga en caja", "Caja", "open", 1)
    assert "esperó 2 min" in a["desc"] and "umbral configurado es 2 min" in a["desc"]
    assert a["offset_seg"] == 52   # 60 s desde el inicio de la sesion - 8 s de margen del clip


def test_subir_el_umbral_de_espera_saca_la_alerta(bd):
    puntos = _puntos(1, datetime(2026, 10, 28, 10), 12)
    assert alertas._alertas_caja(_bd_caja(bd, puntos, {"wait": 2.5})) == []


def test_una_alerta_de_caja_resuelta_sale_como_resuelta(bd):
    t0 = datetime(2026, 10, 28, 10)
    id_ = f"espera-2-1-{int(t0.timestamp())}"
    lista = alertas._alertas_caja(_bd_caja(bd, _puntos(1, t0, 12), {"wait": 2}, resueltas=[id_]))
    assert lista[0]["id"] == id_ and lista[0]["status"] == "resolved"


def test_alertas_de_caja_con_error_de_base_no_rompen_nada(bd):
    bd.error = RuntimeError("caida")
    assert alertas._alertas_caja(bd.cursor()) == []


@pytest.mark.parametrize("body, resuelta, sql", [({}, True, "INSERT"), ({"resuelta": False}, False, "DELETE")])
def test_resolver_alerta_de_caja(cliente, monkeypatch, bd, body, resuelta, sql):
    monkeypatch.setattr(alertas, "_get_conn", lambda: bd)
    r = cliente.post("/api/alertas/espera-2-1-1761656400/resolver", json=body)
    assert r.get_json() == {"id": "espera-2-1-1761656400", "resuelta": resuelta}
    assert any(s.strip().startswith(sql) for s, _ in bd.consultas) and bd.commits == 1


def test_resolver_alerta_con_id_desconocido_responde_404(cliente, monkeypatch, bd):
    monkeypatch.setattr(alertas, "_get_conn", lambda: bd)
    assert cliente.post("/api/alertas/cola-2-1761656400/resolver", json={}).status_code == 404
    assert bd.consultas == []

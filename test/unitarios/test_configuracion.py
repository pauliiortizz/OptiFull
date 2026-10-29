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


def test_put_que_cambia_el_umbral_lo_anota_desde_ahora(cliente, monkeypatch, bd):
    bd.responder("FROM configuracion", [({"umbrales": {"wait": 6}},)])
    monkeypatch.setattr(configuracion, "_get_conn", lambda: bd)
    monkeypatch.setattr(configuracion, "ahora_local", lambda: datetime(2026, 10, 28, 22, 22))
    assert cliente.put("/api/configuracion", json=GUARDADO).status_code == 200
    anotados = [p for s, p in bd.consultas if s.strip().startswith("INSERT INTO umbrales_espera_historial")]
    # primera vez: el umbral que regia hasta ahora (6) y el nuevo (2,5) desde ahora
    assert anotados == [(configuracion.DESDE_SIEMPRE, 6), (datetime(2026, 10, 28, 22, 22), 2.5)]
    assert bd.commits == 1


def test_put_que_no_cambia_el_umbral_no_anota_nada(cliente, monkeypatch, bd):
    bd.responder("FROM configuracion", [({"umbrales": {"wait": 2.5}},)])
    monkeypatch.setattr(configuracion, "_get_conn", lambda: bd)
    assert cliente.put("/api/configuracion", json={**GUARDADO, "push": True}).status_code == 200
    assert not any("umbrales_espera_historial" in s for s, _ in bd.consultas)


def test_put_con_historial_ya_empezado_solo_anota_el_nuevo(cliente, monkeypatch, bd):
    bd.responder("FROM configuracion", [({"umbrales": {"wait": 6}},)])
    bd.responder("SELECT 1 FROM umbrales_espera_historial", [(1,)])
    monkeypatch.setattr(configuracion, "_get_conn", lambda: bd)
    cliente.put("/api/configuracion", json=GUARDADO)
    anotados = [p for s, p in bd.consultas if s.strip().startswith("INSERT INTO umbrales_espera_historial")]
    assert len(anotados) == 1 and anotados[0][1] == 2.5


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
    return bd.cursor()


def test_espera_que_llega_al_umbral_levanta_una_alerta(bd):
    t0 = datetime(2026, 10, 28, 10)
    puntos = _puntos(1, t0, 12) + _puntos(2, t0, 3)   # 120 s y 30 s de espera
    lista = alertas._alertas_caja(_bd_caja(bd, puntos, {"wait": 2}))
    assert len(lista) == 1
    a = lista[0]
    assert (a["tipo"], a["sev"], a["title"], a["zone"], a["persona_id"]) == (
        "espera_excesiva", "warn", "Espera larga en caja", "Caja", 1)
    assert "esperó 2 min" in a["desc"] and "umbral vigente en ese momento era 2 min" in a["desc"]
    # sin resolver no tiene estado; sin video ni evidencia
    assert a["status"] is None and a["evidencia"] is None and a["sesion_id"] is None


# ── El umbral rige desde que se cambia ────────────────────────────────────────

D = datetime(2026, 10, 28)
CAMBIO = D.replace(hour=22, minute=22)   # 6 min hasta las 22:22, 2,5 min desde ahi
HISTORIAL = [(configuracion.DESDE_SIEMPRE, 6.0), (CAMBIO, 2.5)]


def _espera(inicio, minutos):
    return {"inicio": inicio, "segundos": minutos * 60}


@pytest.mark.parametrize("inicio, minutos, umbral", [
    (D.replace(hour=14), 3, None),               # 3 min a las 14 h: con el umbral de ese momento (6) no era alerta
    (D.replace(hour=14), 7, 6.0),                # 7 min a las 14 h: si, con el de 6
    (CAMBIO + timedelta(minutes=5), 3, 2.5),     # despues del cambio rige 2,5
    (CAMBIO - timedelta(minutes=1), 4, 2.5),     # empezo antes del cambio y a las 22:23:30 ya llevaba 2,5 con el nuevo
    (CAMBIO - timedelta(minutes=10), 5, None),   # termino antes del cambio sin llegar a 6
])
def test_cada_espera_usa_el_umbral_vigente_en_su_momento(inicio, minutos, umbral):
    assert alertas.umbral_que_dispara(_espera(inicio, minutos), HISTORIAL) == umbral


def test_subir_el_umbral_no_borra_las_alertas_que_ya_habia():
    historial = [(configuracion.DESDE_SIEMPRE, 2.5), (CAMBIO, 8.0)]
    assert alertas.umbral_que_dispara(_espera(D.replace(hour=14), 3), historial) == 2.5
    assert alertas.umbral_que_dispara(_espera(CAMBIO + timedelta(minutes=1), 3), historial) is None


def test_bajar_el_umbral_no_trae_alertas_viejas(bd):
    bd.responder("to_regclass", [{"t": "umbrales_espera_historial"}])
    bd.responder("FROM umbrales_espera_historial ORDER BY", [
        {"vigente_desde": configuracion.DESDE_SIEMPRE, "wait": 6.0},
        {"vigente_desde": datetime(2026, 10, 28, 12), "wait": 2.0},
    ])
    antes = _puntos(1, datetime(2026, 10, 28, 10), 18)         # 3 min a las 10, con el umbral de 6
    despues = _puntos(2, datetime(2026, 10, 28, 13), 18)       # 3 min a las 13, con el de 2
    lista = alertas._alertas_caja(_bd_caja(bd, antes + despues, {"wait": 2}))
    assert [a["persona_id"] for a in lista] == [2]


def test_subir_el_umbral_de_espera_saca_la_alerta(bd):
    puntos = _puntos(1, datetime(2026, 10, 28, 10), 12)
    assert alertas._alertas_caja(_bd_caja(bd, puntos, {"wait": 2.5})) == []


def test_alertas_de_caja_con_error_de_base_no_rompen_nada(bd):
    bd.error = RuntimeError("caida")
    assert alertas._alertas_caja(bd.cursor()) == []


def test_una_alerta_de_caja_resuelta_sale_como_resuelta(bd):
    t0 = datetime(2026, 10, 28, 10)
    id_ = f"espera-2-1-{int(t0.timestamp())}"
    lista = alertas._alertas_caja(_bd_caja(bd, _puntos(1, t0, 12), {"wait": 2}, resueltas=[id_]))
    assert lista[0]["id"] == id_ and lista[0]["status"] == "resolved"


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

"""Tests de frontend/api/push.py (/api/push/*): suscripciones de los navegadores y envio de las alertas como
notificacion push. La base se simula con BDFalsa (conftest.py) y el envio real (pywebpush) se reemplaza por uno
falso que anota a quien se le mando cada mensaje."""
import json

import pytest

import api
from api import push

SUSCRIPCION = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": "BPclave", "auth": "secreto"}}
FILA = ("https://fcm.googleapis.com/fcm/send/abc", "BPclave", "secreto")
OTRA = ("https://updates.push.services.mozilla.com/wpush/v2/xyz", "BPotra", "otro")


@pytest.fixture
def cliente():
    return api.app.test_client()


@pytest.fixture
def con_bd(monkeypatch, bd):
    monkeypatch.setattr(push, "_get_conn", lambda: bd)
    return bd


@pytest.fixture
def con_claves(monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BPublica")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "privada")
    monkeypatch.setenv("PUSH_TOKEN", "token-del-detector")


@pytest.fixture
def envios(monkeypatch):
    """Reemplaza el envio real: guarda (endpoint, mensaje) y responde lo que diga 'resultado' para cada endpoint."""
    registro = {"enviados": [], "resultado": {}}

    def enviar(suscripcion, mensaje):
        registro["enviados"].append((suscripcion["endpoint"], mensaje))
        return registro["resultado"].get(suscripcion["endpoint"], "ok")
    monkeypatch.setattr(push, "_enviar", enviar)
    return registro


def sql_con(bd, fragmento):
    return [(sql, p) for sql, p in bd.consultas if fragmento in sql]


# ── Clave publica y suscripciones ────────────────────────────────────────────

def test_sin_claves_vapid_el_push_queda_apagado(cliente, monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    r = cliente.get("/api/push/clave")
    assert r.status_code == 503 and "no están configuradas" in r.get_json()["error"]


def test_devuelve_la_clave_publica(cliente, con_claves):
    assert cliente.get("/api/push/clave").get_json() == {"clave": "BPublica"}


def test_guarda_la_suscripcion_del_navegador_con_el_usuario(cliente, con_bd):
    r = cliente.post("/api/push/suscripcion", json=SUSCRIPCION)
    assert r.status_code == 201
    assert sql_con(con_bd, "CREATE TABLE IF NOT EXISTS push_suscripciones")
    (_, params), = sql_con(con_bd, "INSERT INTO push_suscripciones")
    assert params == (*FILA, "admin_test") and con_bd.commits == 1


@pytest.mark.parametrize("cuerpo", [
    None, {}, {"endpoint": "https://x"}, {**SUSCRIPCION, "endpoint": "http://inseguro/abc"},
    {**SUSCRIPCION, "keys": {"p256dh": "", "auth": "a"}}, {**SUSCRIPCION, "endpoint": "https://" + "x" * 2000},
])
def test_rechaza_suscripciones_invalidas_sin_tocar_la_base(cliente, con_bd, cuerpo):
    assert cliente.post("/api/push/suscripcion", json=cuerpo).status_code == 400
    assert con_bd.consultas == []


def test_borra_la_suscripcion(cliente, con_bd):
    assert cliente.delete("/api/push/suscripcion", json={"endpoint": FILA[0]}).status_code == 200
    (_, params), = sql_con(con_bd, "DELETE FROM push_suscripciones WHERE endpoint = %s")
    assert params == (FILA[0],)


def test_sin_base_responde_503(cliente, monkeypatch):
    monkeypatch.setattr(push, "_get_conn", lambda: None)
    assert cliente.post("/api/push/suscripcion", json=SUSCRIPCION).status_code == 503


# ── Notificacion de prueba ───────────────────────────────────────────────────

def test_la_prueba_va_solo_al_navegador_que_la_pide(cliente, con_bd, con_claves, envios):
    con_bd.responder("WHERE endpoint = %s", [FILA])
    assert cliente.post("/api/push/prueba", json={"endpoint": FILA[0]}).status_code == 200
    assert [e for e, _ in envios["enviados"]] == [FILA[0]]
    assert envios["enviados"][0][1]["titulo"] == "Notificaciones de OptiFull activadas"


def test_la_prueba_de_un_navegador_no_suscripto_da_404(cliente, con_bd, con_claves, envios):
    assert cliente.post("/api/push/prueba", json={"endpoint": FILA[0]}).status_code == 404
    assert envios["enviados"] == []


def test_si_el_servicio_de_push_rechaza_la_prueba_avisa_el_error(cliente, con_bd, con_claves, envios):
    con_bd.responder("WHERE endpoint = %s", [FILA])
    envios["resultado"][FILA[0]] = "error"
    assert cliente.post("/api/push/prueba", json={"endpoint": FILA[0]}).status_code == 502


# ── Aviso del detector: POST /api/push/alerta ────────────────────────────────

def avisar(cliente, alerta_id=7, token="token-del-detector"):
    return cliente.post("/api/push/alerta", json={"alerta_id": alerta_id}, headers={"X-Push-Token": token})


def test_la_alerta_llega_a_todos_los_navegadores_con_el_texto_de_la_base(cliente, con_bd, con_claves, envios):
    con_bd.responder("FROM alertas WHERE id", [("posible_hurto", "Tomó un producto y salió sin pasar por caja")])
    con_bd.responder("FROM push_suscripciones", [FILA, OTRA])
    r = avisar(cliente)
    assert r.get_json() == {"enviadas": 2}
    assert [e for e, _ in envios["enviados"]] == [FILA[0], OTRA[0]]
    mensaje = envios["enviados"][0][1]
    assert mensaje == {"titulo": "Posible hurto detectado", "cuerpo": "Tomó un producto y salió sin pasar por caja",
                       "url": "/alertas", "tag": "optifull-alerta-7"}


def test_las_suscripciones_vencidas_se_borran(cliente, con_bd, con_claves, envios):
    con_bd.responder("FROM alertas WHERE id", [("posible_hurto", "x")])
    con_bd.responder("FROM push_suscripciones", [FILA, OTRA])
    envios["resultado"][OTRA[0]] = "vencida"
    assert avisar(cliente).get_json() == {"enviadas": 1}
    (_, params), = sql_con(con_bd, "DELETE FROM push_suscripciones WHERE endpoint = ANY")
    assert params == ([OTRA[0]],)


@pytest.mark.sin_sesion
@pytest.mark.parametrize("token", ["", "otro-token"])
def test_sin_el_token_del_detector_no_se_manda_nada(cliente, con_bd, con_claves, envios, token):
    r = avisar(cliente, token=token)
    assert r.status_code == 403 and envios["enviados"] == [] and con_bd.consultas == []


@pytest.mark.sin_sesion
def test_el_aviso_del_detector_no_pide_sesion(cliente, con_bd, con_claves, envios):
    con_bd.responder("FROM alertas WHERE id", [("posible_hurto", "x")])
    assert avisar(cliente).status_code == 200


def test_sin_push_token_configurado_el_endpoint_queda_cerrado(cliente, con_bd, con_claves, envios, monkeypatch):
    monkeypatch.delenv("PUSH_TOKEN")
    assert avisar(cliente, token="").status_code == 403


def test_con_el_push_apagado_en_configuracion_no_se_manda(cliente, con_bd, con_claves, envios):
    con_bd.responder("FROM configuracion", [({"push": False},)])
    con_bd.responder("FROM alertas WHERE id", [("posible_hurto", "x")])
    con_bd.responder("FROM push_suscripciones", [FILA])
    assert avisar(cliente).get_json()["enviadas"] == 0 and envios["enviados"] == []


def test_alerta_inexistente_da_404(cliente, con_bd, con_claves, envios):
    assert avisar(cliente).status_code == 404 and envios["enviados"] == []


@pytest.mark.parametrize("alerta_id", ["7", None, True, 1.5])
def test_alerta_id_invalido_da_400(cliente, con_bd, con_claves, alerta_id):
    assert avisar(cliente, alerta_id=alerta_id).status_code == 400


# ── Envio real (pywebpush) ───────────────────────────────────────────────────

class RespuestaFalsa:
    def __init__(self, status_code):
        self.status_code = status_code


@pytest.mark.parametrize("excepcion, esperado", [(None, "ok"), (404, "vencida"), (410, "vencida"), (500, "error"),
                                                  (RuntimeError("sin red"), "error")])
def test_enviar_clasifica_la_respuesta_del_servicio_de_push(monkeypatch, con_claves, excepcion, esperado):
    import pywebpush
    llamadas = []

    def webpush_falso(**kw):
        llamadas.append(kw)
        if isinstance(excepcion, int):
            raise pywebpush.WebPushException("rechazado", response=RespuestaFalsa(excepcion))
        if excepcion:
            raise excepcion
    monkeypatch.setattr(pywebpush, "webpush", webpush_falso)
    fila = {"endpoint": FILA[0], "p256dh": FILA[1], "auth": FILA[2]}
    assert push._enviar(fila, {"titulo": "Hola"}) == esperado
    kw = llamadas[0]
    assert kw["subscription_info"] == SUSCRIPCION and json.loads(kw["data"]) == {"titulo": "Hola"}
    assert kw["vapid_private_key"] == "privada" and kw["vapid_claims"]["sub"].startswith(("https://", "mailto:"))

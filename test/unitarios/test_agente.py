"""Tests del agente local (frontend/api/agente.py): lo que el panel de produccion le pide a la compu de la caja
(video del celular, prender/apagar el detector, videos de prueba) y sus controles, que reemplazan a la sesion:
solo en la compu (no en la nube), solo pedidos de la propia compu y con Host local, y las ordenes solo desde las
paginas de produccion y QA."""
import pytest
from flask import jsonify

from api import app
from api import agente as m

PROD = "https://optifull.onrender.com"
QA = "https://optifull-qa.onrender.com"


@pytest.fixture
def cliente():
    return app.test_client()


@pytest.fixture
def delegados(monkeypatch):
    """Reemplaza las funciones de productos y video que el agente reusa; registra con que se las llamo."""
    llamadas = []

    def falso(nombre):
        def f(*args):
            llamadas.append((nombre, args))
            return jsonify({"de": nombre})
        return f

    monkeypatch.setattr(m.productos, "iniciar", falso("iniciar"))
    monkeypatch.setattr(m.productos, "detener", falso("detener"))
    monkeypatch.setattr(m.productos, "camara", falso("camara"))
    monkeypatch.setattr(m.video, "list_videos", falso("videos"))
    monkeypatch.setattr(m.video, "serve_video", falso("video"))
    return llamadas


class ProcesoFalso:
    def __init__(self, vivo):
        self.vivo = vivo

    def poll(self):
        return None if self.vivo else 0


# ── Lo que ofrece ─────────────────────────────────────────────────────────────

@pytest.mark.sin_sesion
def test_no_pide_sesion_y_dice_que_esta(cliente, monkeypatch):
    monkeypatch.setattr(m.productos, "_proceso_caja", None)
    r = cliente.get("/agente/estado")
    assert r.status_code == 200 and r.get_json() == {"agente": True, "corriendo": False}


@pytest.mark.parametrize("proceso, corriendo", [(None, False), (ProcesoFalso(vivo=True), True),
                                                (ProcesoFalso(vivo=False), False)])
def test_estado_dice_si_el_detector_esta_corriendo(cliente, monkeypatch, proceso, corriendo):
    monkeypatch.setattr(m.productos, "_proceso_caja", proceso)
    assert cliente.get("/agente/estado").get_json()["corriendo"] is corriendo


@pytest.mark.parametrize("metodo, ruta, delegado", [
    ("post", "/agente/iniciar", "iniciar"),
    ("post", "/agente/detener", "detener"),
    ("get", "/agente/camara?url=http://192.168.0.10:8081/video", "camara"),
    ("get", "/agente/videos", "videos"),
    ("get", "/agente/video/caja.mp4", "video"),
])
def test_reusa_las_funciones_de_la_caja_y_de_video(cliente, delegados, metodo, ruta, delegado):
    r = getattr(cliente, metodo)(ruta, headers={"Origin": PROD})
    assert r.status_code == 200 and r.get_json() == {"de": delegado}
    assert delegados[0][0] == delegado


def test_el_video_pasa_el_nombre_del_archivo(cliente, delegados):
    cliente.get("/agente/video/caja%202.mp4")
    assert delegados == [("video", ("caja 2.mp4",))]


# ── Controles ─────────────────────────────────────────────────────────────────

def test_en_la_nube_no_existe(cliente, monkeypatch, delegados):
    monkeypatch.setenv("APP_ENV", "production")
    for metodo, ruta in [("get", "/agente/estado"), ("post", "/agente/iniciar"), ("get", "/agente/camara")]:
        assert getattr(cliente, metodo)(ruta, headers={"Origin": PROD}).status_code == 404
    assert delegados == []


def test_rechaza_pedidos_de_otros_equipos_de_la_red(cliente, delegados):
    # serve_dashboard escucha en 0.0.0.0: el celular del hotspot u otra compu llegarian sin este control
    r = cliente.get("/agente/camara?url=x", environ_base={"REMOTE_ADDR": "192.168.137.141"})
    assert r.status_code == 403 and delegados == []


@pytest.mark.parametrize("host", ["malo.com", "malo.com:8080", "192.168.0.195:8080"])
def test_rechaza_un_host_que_no_es_local(cliente, delegados, host):
    # DNS rebinding: un sitio apunta su dominio a 127.0.0.1 y el navegador le pega al agente con ese Host
    assert cliente.get("/agente/estado", headers={"Host": host}).status_code == 403


@pytest.mark.parametrize("host", ["127.0.0.1:8080", "localhost:8080", "[::1]:8080"])
def test_acepta_los_host_locales(cliente, host):
    assert cliente.get("/agente/estado", headers={"Host": host}).status_code == 200


def test_acepta_pedidos_por_ipv6_local(cliente):
    assert cliente.get("/agente/estado", environ_base={"REMOTE_ADDR": "::1"}).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://sitio-malo.com"}, {"Origin": "http://localhost:5173"}])
def test_las_ordenes_solo_vienen_de_produccion_o_qa(cliente, delegados, headers):
    for ruta in ("/agente/iniciar", "/agente/detener"):
        assert cliente.post(ruta, headers=headers).status_code == 403
    assert delegados == []


@pytest.mark.parametrize("origen", [PROD, QA])
def test_preflight_de_produccion_y_qa(cliente, delegados, origen):
    r = cliente.options("/agente/iniciar", headers={"Origin": origen, "Access-Control-Request-Method": "POST"})
    assert r.status_code == 204
    assert r.headers["Access-Control-Allow-Origin"] == origen
    assert r.headers["Access-Control-Allow-Private-Network"] == "true"
    assert "POST" in r.headers["Access-Control-Allow-Methods"]
    assert "Content-Type" in r.headers["Access-Control-Allow-Headers"]
    assert delegados == []                            # el preflight no ejecuta la orden


def test_sin_origen_permitido_no_agrega_cabeceras_cors(cliente):
    r = cliente.get("/agente/estado", headers={"Origin": "https://sitio-malo.com"})
    assert r.status_code == 200 and "Access-Control-Allow-Origin" not in r.headers


def test_los_origenes_se_configuran(cliente, delegados, monkeypatch):
    monkeypatch.setenv("AGENTE_ORIGENES", "https://otro-panel.com/, ,http://192.168.0.195:5174")
    assert m.origenes_permitidos() == {"https://otro-panel.com", "http://192.168.0.195:5174"}
    assert cliente.post("/agente/iniciar", headers={"Origin": "https://otro-panel.com"}).status_code == 200
    assert cliente.post("/agente/iniciar", headers={"Origin": PROD}).status_code == 403

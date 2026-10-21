"""Tests de los endpoints de la caja y productos (frontend/api/productos.py): estado y acciones de la
cajera, venta (descuento de stock), stock, metricas, arranque/parada de la deteccion y proxy de la
camara del celular. La base de datos se simula con BDFalsa y los subprocesos/HTTP se reemplazan."""
import io
import subprocess

import psycopg2.extras
import pytest

from api import app
from api import productos as m


@pytest.fixture
def cliente():
    return app.test_client()


@pytest.fixture
def con_bd(monkeypatch, bd):
    monkeypatch.setattr(m, "_get_conn", lambda: bd)
    monkeypatch.setattr(m, "_proceso_caja", None)

    def execute_values(cur, sql, filas, fetch=False):   # sin Postgres real no se puede usar mogrify()
        cur.execute(sql, filas)
        return cur.fetchall() if fetch else None

    monkeypatch.setattr(psycopg2.extras, "execute_values", execute_values)
    return bd


@pytest.fixture
def sin_bd(monkeypatch):
    monkeypatch.setattr(m, "_get_conn", lambda: None)
    monkeypatch.setattr(m, "_proceso_caja", None)


class ProcesoFalso:
    pid = 4321

    def __init__(self, vivo=True):
        self.vivo, self.terminado = vivo, False

    def poll(self):
        return None if self.vivo else 0

    def terminate(self):
        self.terminado = True


# ── Comportamiento comun ──────────────────────────────────────────────────────

ENDPOINTS_BD = [("get", "/api/productos/estado", None), ("get", "/api/productos/stock", None),
                ("get", "/api/productos/metricas", None), ("post", "/api/productos/detener", None),
                ("post", "/api/productos/accion", {"accion": "cancelar"}),
                ("post", "/api/productos/venta", {"items": [{"sku": "A", "cantidad": 1}]}),
                ("post", "/api/productos/iniciar", {})]


@pytest.mark.parametrize("metodo, ruta, body", ENDPOINTS_BD)
def test_sin_base_de_datos_responde_503(cliente, sin_bd, metodo, ruta, body):
    assert getattr(cliente, metodo)(ruta, json=body).status_code == 503


@pytest.mark.parametrize("metodo, ruta, body", ENDPOINTS_BD[:-1])
def test_error_de_la_base_de_datos_responde_500(cliente, con_bd, metodo, ruta, body):
    con_bd.error = RuntimeError("timeout")
    r = getattr(cliente, metodo)(ruta, json=body)
    assert r.status_code == 500 and r.get_json() == {"error": "timeout"}


# ── Estado y acciones de la cajera ────────────────────────────────────────────

def test_estado_sin_fila_queda_inactivo(cliente, con_bd):
    assert cliente.get("/api/productos/estado").get_json() == {"corriendo": False, "estado": "inactivo",
                                                               "pendiente": None}


def test_estado_esperando_decision_con_la_caja_corriendo(cliente, con_bd, monkeypatch):
    monkeypatch.setattr(m, "_proceso_caja", ProcesoFalso())
    con_bd.responder("FROM caja_estado", [{"estado": "esperando_decision", "pendiente": {"tipo": "confirmar"},
                                          "actualizado_en": None}])
    datos = cliente.get("/api/productos/estado").get_json()
    assert datos == {"corriendo": True, "estado": "esperando_decision", "pendiente": {"tipo": "confirmar"}}


@pytest.mark.parametrize("rowcount, status", [(1, 200), (0, 409)])   # 409: no habia nada pendiente
def test_accion_de_la_cajera(cliente, con_bd, rowcount, status):
    con_bd.rowcount = rowcount
    r = cliente.post("/api/productos/accion", json={"accion": "confirmar", "cantidad": 2})
    assert r.status_code == status
    assert con_bd.commits == 1


@pytest.mark.parametrize("body", [None, {}])
def test_accion_sin_body_responde_400(cliente, con_bd, body):
    r = cliente.post("/api/productos/accion", data="" if body is None else "{}", content_type="application/json")
    assert r.status_code == 400


# ── Venta ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("items, mensaje", [
    ([], "vacio"),
    ([{"sku": "A", "cantidad": 0}], "items invalidos"),     # valor limite: cantidad 0
    ([{"sku": "A", "cantidad": -1}], "items invalidos"),
    ([{"cantidad": 1}], "items invalidos"),                 # sin sku
    ([{"sku": "A", "cantidad": "dos"}], "cantidad invalida"),
])
def test_venta_ticket_invalido_responde_400(cliente, con_bd, items, mensaje):
    r = cliente.post("/api/productos/venta", json={"items": items})
    assert r.status_code == 400 and mensaje in r.get_json()["error"]
    assert con_bd.consultas == []


def test_venta_suma_lineas_del_mismo_producto_y_registra_cada_item(cliente, con_bd):
    con_bd.responder("UPDATE productos", [("A", 7), ("B", 0)])
    items = [{"sku": "A", "cantidad": 2, "confianza_llm": 0.9}, {"sku": "A", "cantidad": 1},
             {"sku": "B", "cantidad": "1", "estado_matching": "reconocido"}]
    r = cliente.post("/api/productos/venta", json={"items": items})
    assert r.get_json() == {"ok": True, "stock": {"A": 7, "B": 0}}
    _, por_sku = con_bd.consultas[0]
    assert sorted(por_sku) == [("A", 3), ("B", 1)]
    _, transacciones = con_bd.consultas[1]
    assert len(transacciones) == 3 and transacciones[1][3] == "manual"   # sin estado: se registra como manual
    assert con_bd.commits == 1


def test_venta_con_producto_inexistente_no_descuenta_nada(cliente, con_bd):
    con_bd.responder("UPDATE productos", [("A", 5)])
    r = cliente.post("/api/productos/venta", json={"items": [{"sku": "A", "cantidad": 1}, {"sku": "ZZZ", "cantidad": 1}]})
    assert r.status_code == 400 and r.get_json()["error"] == "productos inexistentes: ZZZ"
    assert con_bd.rollbacks == 1 and con_bd.commits == 0


# ── Stock y metricas ──────────────────────────────────────────────────────────

def test_stock(cliente, con_bd):
    con_bd.responder("FROM productos ORDER BY nombre", [{"sku": "A", "nombre": "Agua", "cantidad": 3}])
    assert cliente.get("/api/productos/stock").get_json() == {"productos": [{"sku": "A", "nombre": "Agua", "cantidad": 3}]}


def test_metricas(cliente, con_bd):
    con_bd.responder("COUNT(*) AS total", [{"total": 12}])
    con_bd.responder("AVG(confianza_llm), 0) AS promedio", [{"promedio": 0.87654}])
    con_bd.responder("GROUP BY estado_matching", [{"estado_matching": "reconocido", "cantidad": 10}])
    con_bd.responder("GROUP BY sku", [{"sku": "B", "confianza_promedio": 0.4, "apariciones": 2}])
    datos = cliente.get("/api/productos/metricas").get_json()
    assert (datos["total_transacciones"], datos["confianza_promedio"]) == (12, 0.877)
    assert datos["productos_con_mas_problemas"][0]["sku"] == "B"


def test_detener(cliente, con_bd):
    assert cliente.post("/api/productos/detener").get_json()["ok"] is True
    assert "estado = 'detener'" in con_bd.consultas[0][0]


# ── Iniciar la deteccion de productos ─────────────────────────────────────────

@pytest.fixture
def popen(monkeypatch, tmp_path):
    llamadas = []

    def falso(comando, cwd=None, stdout=None, stderr=None):
        llamadas.append({"comando": comando, "cwd": cwd})
        return ProcesoFalso()

    monkeypatch.setattr(m, "DETECCION_PRODUCTOS_DIR", str(tmp_path))
    monkeypatch.setattr(subprocess, "Popen", falso)
    return llamadas


def test_iniciar_con_source_y_roi(cliente, con_bd, popen):
    r = cliente.post("/api/productos/iniciar", json={"source": "data/videos/prueba.mp4", "roi": "0,0,100,100"})
    assert r.get_json()["ok"] is True and r.get_json()["pid"] == ProcesoFalso.pid
    assert popen[0]["comando"][2:] == ["main.py", "--source", "data/videos/prueba.mp4", "--web", "--roi", "0,0,100,100"]
    assert con_bd.consultas == []   # con source no hace falta buscar la camara


def test_iniciar_sin_source_usa_la_camara_de_caja(cliente, con_bd, popen):
    con_bd.responder("WHERE nombre = 'Camara Caja'", [("rtsp://caja/stream",)])
    assert cliente.post("/api/productos/iniciar", json={}).get_json()["source"] == "rtsp://caja/stream"
    assert "--roi" not in popen[0]["comando"]


def test_iniciar_sin_source_ni_camara_de_caja_responde_400(cliente, con_bd, popen):
    assert cliente.post("/api/productos/iniciar", json={}).status_code == 400
    assert popen == []


def test_iniciar_dos_veces_responde_409(cliente, con_bd, popen, monkeypatch):
    monkeypatch.setattr(m, "_proceso_caja", ProcesoFalso(vivo=True))
    assert cliente.post("/api/productos/iniciar", json={"source": "x.mp4"}).status_code == 409
    assert popen == []


def test_al_cerrar_flask_se_termina_el_proceso_de_la_caja(monkeypatch):
    proceso = ProcesoFalso(vivo=True)
    monkeypatch.setattr(m, "_proceso_caja", proceso)
    m._matar_proceso_caja_al_salir()
    assert proceso.terminado
    terminado = ProcesoFalso(vivo=False)
    monkeypatch.setattr(m, "_proceso_caja", terminado)
    m._matar_proceso_caja_al_salir()
    assert not terminado.terminado


# ── Proxy de la camara del celular ────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "",
    "https://192.168.0.10:8081/video",      # solo http
    "http://8.8.8.8/video",                 # IP publica
    "http://camara.local/video",            # nombre en vez de IP
])
def test_camara_solo_acepta_ips_de_la_red_local(cliente, url):
    r = cliente.get("/api/productos/camara", query_string={"url": url})
    assert r.status_code == 400


class RespuestaFalsa:
    headers = {"Content-Type": "multipart/x-mixed-replace; boundary=frame"}

    def __init__(self):
        self.cuerpo, self.cerrada = io.BytesIO(b"--frame jpeg"), False

    def read1(self, n):
        return self.cuerpo.read(n)

    def close(self):
        self.cerrada = True


def test_camara_reenvia_el_video_con_las_credenciales_como_basic_auth(cliente, monkeypatch):
    pedidos = []
    respuesta = RespuestaFalsa()

    def urlopen(pedido, timeout):
        pedidos.append(pedido)
        return respuesta

    monkeypatch.setattr(m.urllib.request, "urlopen", urlopen)
    r = cliente.get("/api/productos/camara", query_string={"url": "http://usu%40rio:cl%3Ave@192.168.0.10:8081/video"})
    assert r.data == b"--frame jpeg" and r.content_type.startswith("multipart/x-mixed-replace")
    assert pedidos[0].full_url == "http://192.168.0.10:8081/video"   # sin credenciales en la URL
    assert pedidos[0].get_header("Authorization") == "Basic dXN1QHJpbzpjbDp2ZQ=="   # usu@rio:cl:ve
    assert respuesta.cerrada


def test_camara_inalcanzable_responde_502(cliente, monkeypatch):
    def urlopen(pedido, timeout):
        raise OSError("timed out")

    monkeypatch.setattr(m.urllib.request, "urlopen", urlopen)
    r = cliente.get("/api/productos/camara", query_string={"url": "http://10.0.0.5/video"})
    assert r.status_code == 502 and "timed out" in r.get_json()["error"]


# ── Pool de conexiones ────────────────────────────────────────────────────────

def test_pool_sin_database_url_o_que_no_conecta(monkeypatch):
    monkeypatch.setattr(m, "_pool", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert m._get_pool() is None and m._get_conn() is None
    m._release_conn(object())   # sin pool no hace nada
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/x")

    def pool_que_falla(*a, **k):
        raise psycopg2.OperationalError("connection refused")

    monkeypatch.setattr(m.psycopg2.pool, "ThreadedConnectionPool", pool_que_falla)
    assert m._get_pool() is None


class PoolFalso:
    def __init__(self, conexion=None, falla=False):
        self.conexion, self.falla, self.devueltas = conexion, falla, []

    def getconn(self):
        if self.falla:
            raise psycopg2.OperationalError("sin red")
        return self.conexion

    def putconn(self, conn):
        self.devueltas.append(conn)


class ConexionFalsa:
    autocommit = False


def test_pool_presta_conexiones_en_autocommit_y_las_recupera(monkeypatch):
    conexion = ConexionFalsa()
    pool = PoolFalso(conexion)
    monkeypatch.setattr(m, "_pool", pool)
    assert m._get_conn() is conexion and conexion.autocommit is True
    m._release_conn(conexion)
    assert pool.devueltas == [conexion]
    monkeypatch.setattr(m, "_pool", PoolFalso(falla=True))
    assert m._get_conn() is None

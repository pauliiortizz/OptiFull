"""Tests de deteccion/pipeline/aviso_push.py: el detector avisa cada alerta nueva al backend (POST /api/push/alerta)
para que salga como notificacion push. Se reemplaza urllib.request.urlopen por uno falso: no hay red."""
import io
import json
import urllib.error

import pytest

from deteccion.pipeline import aviso_push


class RespuestaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def pedidos(monkeypatch):
    """Guarda cada pedido; 'respuestas' es la lista de lo que pasa en cada intento (None = 200 OK)."""
    registro = {"pedidos": [], "respuestas": []}

    def urlopen(pedido, timeout=None):
        registro["pedidos"].append((pedido, timeout))
        resultado = registro["respuestas"].pop(0) if registro["respuestas"] else None
        if isinstance(resultado, Exception):
            raise resultado
        return RespuestaFalsa(b'{"enviadas": 1}')
    monkeypatch.setattr(aviso_push.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(aviso_push.time, "sleep", lambda s: None)
    return registro


@pytest.mark.parametrize("url, token", [(None, "t"), ("https://optifull.onrender.com", None), ("", "")])
def test_sin_configuracion_no_se_conecta_nada(url, token):
    assert aviso_push.crear_aviso(url, token) is None


def test_avisa_solo_el_id_con_el_token_y_sin_frenar_el_analisis(pedidos):
    avisar = aviso_push.crear_aviso("https://optifull.onrender.com/", "secreto")
    hilo = avisar(42)
    hilo.join(timeout=5)
    assert hilo.daemon
    (pedido, timeout), = pedidos["pedidos"]
    assert pedido.full_url == "https://optifull.onrender.com/api/push/alerta"
    assert pedido.get_method() == "POST" and pedido.get_header("X-push-token") == "secreto"
    assert json.loads(pedido.data) == {"alerta_id": 42}
    assert timeout == aviso_push.TIMEOUT_SEG   # alcanza para que Render despierte el backend


def test_si_falla_la_red_reintenta_una_sola_vez(pedidos):
    pedidos["respuestas"] = [urllib.error.URLError("sin red"), urllib.error.URLError("sin red")]
    aviso_push._avisar("https://x", "t", 1)
    assert len(pedidos["pedidos"]) == 2


def test_si_el_backend_rechaza_el_token_no_reintenta(pedidos):
    pedidos["respuestas"] = [urllib.error.HTTPError("https://x", 403, "no autorizado", None, None)]
    aviso_push._avisar("https://x", "t", 1)
    assert len(pedidos["pedidos"]) == 1


def test_si_el_backend_esta_reiniciando_reintenta(pedidos):
    pedidos["respuestas"] = [urllib.error.HTTPError("https://x", 502, "bad gateway", None, None)]
    aviso_push._avisar("https://x", "t", 1)
    assert len(pedidos["pedidos"]) == 2

"""VisionAgent (deteccion_productos): arma la imagen, llama al LLM y parsea el JSON.

El cliente de Anthropic se reemplaza por un doble que devuelve respuestas preparadas: no se llama a la API.
"""
import base64
import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

import agents.vision_agent as va
from agents.vision_agent import CALIDAD_JPEG, MAX_LADO_IMAGEN, PROMPT_SISTEMA, VisionAgent

COCA = {"producto_detectado": True, "marca": "Coca-Cola", "nombre_producto": "Coca-Cola Zero", "variante": "Zero",
        "tamano": {"valor": 500, "unidad": "ml"}, "categoria": "gaseosa", "confianza": 0.92}


class MensajesFalsos:
    """Doble de client.messages: cada create() consume la siguiente respuesta (texto o excepcion)."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = []

    def create(self, **kwargs):
        self.pedidos.append(kwargs)
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(content=[SimpleNamespace(text=r)])


@pytest.fixture
def esperas(monkeypatch):
    llamadas = []
    monkeypatch.setattr(va.time, "sleep", llamadas.append)
    return llamadas


@pytest.fixture
def agente(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")

    def crear(*respuestas, roi=None):
        a = VisionAgent(roi=roi)
        a.client = SimpleNamespace(messages=MensajesFalsos(respuestas))
        return a
    return crear


def frame(alto=720, ancho=1280):
    f = np.zeros((alto, ancho, 3), dtype=np.uint8)
    f[:, : ancho // 2] = (0, 0, 255)
    return f


def imagen_enviada(a, i=0):
    datos = a.client.messages.pedidos[i]["messages"][0]["content"][0]["source"]["data"]
    return cv2.imdecode(np.frombuffer(base64.standard_b64decode(datos), np.uint8), cv2.IMREAD_COLOR)


def test_sin_api_key_falla_con_mensaje_claro(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        VisionAgent()


def test_crea_el_cliente_real_con_conexion_persistente(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")
    a = VisionAgent(model="modelo-x")
    assert a.model == "modelo-x" and a.roi is None
    assert a.client.api_key == "sk-ant-prueba"


def test_respuesta_json_se_devuelve_como_dict(agente):
    a = agente(json.dumps(COCA))
    assert a.analizar(frame()) == COCA


def test_el_pedido_lleva_prompt_modelo_e_imagen_jpeg(agente):
    a = agente(json.dumps(COCA))
    a.analizar(frame())
    pedido = a.client.messages.pedidos[0]
    assert pedido["model"] == a.model
    assert pedido["system"] == PROMPT_SISTEMA
    imagen, texto = pedido["messages"][0]["content"]
    assert imagen["source"]["media_type"] == "image/jpeg"
    assert texto["type"] == "text"
    assert base64.standard_b64decode(imagen["source"]["data"])[:2] == b"\xff\xd8"   # cabecera JPEG


@pytest.mark.parametrize("texto", [
    "```json\n" + json.dumps(COCA) + "\n```",
    "```\n" + json.dumps(COCA) + "\n```",
    "  " + json.dumps(COCA) + "\n",
])
def test_tolera_backticks_y_espacios(agente, texto):
    assert agente(texto).analizar(frame()) == COCA


def test_sin_producto(agente):
    assert agente('{"producto_detectado": false}').analizar(frame()) == {"producto_detectado": False}


def test_json_invalido_reintenta_y_si_sigue_mal_devuelve_sin_producto(agente, esperas, capsys):
    a = agente("no es json", "tampoco")
    assert a.analizar(frame()) == {"producto_detectado": False, "error": "json_invalido"}
    assert len(a.client.messages.pedidos) == 2
    assert esperas == []                       # el JSON invalido se reintenta sin esperar
    assert "Respuesta no parseable" in capsys.readouterr().out


def test_json_invalido_y_despues_valido(agente):
    a = agente("{roto", json.dumps(COCA))
    assert a.analizar(frame()) == COCA


@pytest.mark.parametrize("error", ["Error code: 429 rate limit", "Error code: 529", "Overloaded"])
def test_error_transitorio_espera_y_reintenta(agente, esperas, error):
    a = agente(RuntimeError(error), json.dumps(COCA))
    assert a.analizar(frame()) == COCA
    assert esperas == [5]


def test_error_transitorio_que_se_repite_se_propaga(agente, esperas):
    a = agente(RuntimeError("429"), RuntimeError("429"))
    with pytest.raises(RuntimeError, match="429"):
        a.analizar(frame())
    assert esperas == [5]


def test_error_no_transitorio_se_propaga_sin_reintentar(agente, esperas):
    a = agente(RuntimeError("401 invalid x-api-key"))
    with pytest.raises(RuntimeError, match="401"):
        a.analizar(frame())
    assert esperas == [] and len(a.client.messages.pedidos) == 1


def test_sin_reintentos(agente):
    a = agente("no es json")
    assert a.analizar(frame(), max_retries=0)["error"] == "json_invalido"


def test_imagen_hasta_el_maximo_no_se_achica(agente):
    a = agente(json.dumps(COCA))
    a.analizar(frame(720, MAX_LADO_IMAGEN))
    assert imagen_enviada(a).shape[:2] == (720, MAX_LADO_IMAGEN)


def test_imagen_grande_se_achica_manteniendo_la_proporcion(agente):
    a = agente(json.dumps(COCA))
    a.analizar(frame(1080, 1920))
    assert imagen_enviada(a).shape[:2] == (720, 1280)


def test_imagen_vertical_grande_se_achica_por_el_lado_mayor(agente):
    a = agente(json.dumps(COCA))
    a.analizar(frame(1920, 1080))
    assert imagen_enviada(a).shape[:2] == (1280, 720)


def test_roi_recorta_antes_de_enviar(agente):
    a = agente(json.dumps(COCA), roi=(0, 0, 100, 50))
    a.analizar(frame())
    enviada = imagen_enviada(a)
    assert enviada.shape[:2] == (50, 100)
    assert enviada[..., 2].mean() > 200          # solo la mitad roja del frame


def test_si_no_se_puede_codificar_el_jpeg_falla(agente, monkeypatch):
    monkeypatch.setattr(va.cv2, "imencode", lambda *a, **k: (False, None))
    with pytest.raises(RuntimeError, match="JPEG"):
        agente(json.dumps(COCA)).analizar(frame())


def test_calidad_jpeg_configurada(agente, monkeypatch):
    usados = []
    original = cv2.imencode

    def espiar(ext, img, params):
        usados.append(params)
        return original(ext, img, params)
    monkeypatch.setattr(va.cv2, "imencode", espiar)
    agente(json.dumps(COCA)).analizar(frame())
    assert usados == [[cv2.IMWRITE_JPEG_QUALITY, CALIDAD_JPEG]]

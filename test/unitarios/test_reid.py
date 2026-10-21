"""Tests del Re-ID en la nube (deteccion/reid/): Gemini, Groq y Claude. No llaman a ninguna API: cada SDK
(google-genai, groq, anthropic) se reemplaza por un doble que responde lo que el test necesita, asi se prueba
el contrato con el proveedor (que se le manda y como se interpreta cada respuesta o error) sin gastar cupo.

Los tests de la logica comun (parseo del JSON, comparacion de descriptores, rate limiting, clasificacion) se
corren contra los TRES proveedores: fijan que se comporten igual."""
import base64
import json
import types
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest
from PIL import Image

from deteccion.reid import claude_reid, gemini_reid, groq_reid

PROVEEDORES = [
    pytest.param(gemini_reid, gemini_reid.GeminiReID, "gemini", "Gemini", id="gemini"),
    pytest.param(groq_reid, groq_reid.GroqReID, "groq", "Groq", id="groq"),
    pytest.param(claude_reid, claude_reid.ClaudeReID, "claude", "Claude", id="claude"),
]
MODULOS = [pytest.param(p.values[0], id=p.id) for p in PROVEEDORES]
REIDS = [pytest.param(p.values, id=p.id) for p in PROVEEDORES]   # para la fixture indirecta 'reid'

CROP = np.zeros((200, 80, 3), np.uint8)
CROP[:100] = (0, 0, 220)   # remera roja (BGR)
DESC = {"color_ropa_superior": "rojo", "color_ropa_inferior": "azul", "complexion": "media",
        "cabello": "corto oscuro", "accesorios": "ninguno"}


def crear(clase, nombre, activo=True, keys=("k1", "k2"), **cambios):
    opciones = {f"usar_{nombre}_reid": activo, f"has_{nombre}": True, "api_keys": list(keys), "model": "modelo-x",
                "min_intervalo_seg": 0, "rafaga_umbral": 99, "pausa_rafaga_seg": 0, "ventana_rafaga_seg": 60,
                "coincidencias_minimas": 3}
    opciones.update(cambios)
    return clase(**opciones)


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    """time.sleep no espera de verdad (rate limiting y pausas entre reintentos); se registran las pausas."""
    pausas = []
    import time
    monkeypatch.setattr(time, "sleep", pausas.append)
    monkeypatch.setattr(gemini_reid, "Image", Image)   # PIL esta instalado aunque google-genai no
    return pausas


# ── Parseo de la respuesta ────────────────────────────────────────────────────

@pytest.mark.parametrize("mod", MODULOS)
@pytest.mark.parametrize("texto, esperado", [
    ('{"a": "rojo"}', {"a": "rojo"}),
    ('```json\n{"a": "rojo"}\n```', {"a": "rojo"}),                     # bloque de codigo markdown
    ('{“a”: “rojo”}', {"a": "rojo"}),                                   # comillas tipograficas como delimitadores
    ('{"a": "rojo"} Espero que sirva.', {"a": "rojo"}),                 # texto de mas despues del JSON
    ('{"a": "rojo", "b": "az', {"a": "rojo", "b": "az"}),               # truncado a mitad de un string
    ('{"a": {"b": "c"}', {"a": {"b": "c"}}),                            # falta la llave de cierre
])
def test_parsear_json_tolera_las_fallas_tipicas_del_modelo(mod, texto, esperado):
    assert mod._parsear_json(texto) == esperado


@pytest.mark.parametrize("mod", MODULOS)
def test_comillas_tipograficas_dentro_de_un_valor_no_rompen_el_json(mod):
    # Regresion de DEF-009: describir un logo ('remera “Nike”') hacia perder la descripcion completa, porque
    # las comillas se pasaban a rectas y cortaban el string JSON.
    assert mod._parsear_json('{"accesorios": "remera “Nike”"}') == {"accesorios": "remera “Nike”"}


@pytest.mark.parametrize("mod", MODULOS)
def test_parsear_json_rechaza_lo_que_no_es_un_objeto(mod):
    with pytest.raises(ValueError, match="Se esperaba un objeto JSON"):
        mod._parsear_json('[{"a": 1}]')
    with pytest.raises(json.JSONDecodeError):
        mod._parsear_json("no es json")


# ── Comparacion de descriptores ───────────────────────────────────────────────

@pytest.mark.parametrize("mod", MODULOS)
@pytest.mark.parametrize("descriptor, valor", [
    ({"cabello": "  Corto Oscuro "}, "corto oscuro"),
    ({"cabello": "No Visible"}, None),     # 'no visible' no es evidencia ni a favor ni en contra
    ({"cabello": ""}, None),
    ({}, None),
    (["no es un dict"], None),             # descripcion corrupta guardada en la BD
])
def test_valor_visible(mod, descriptor, valor):
    assert mod._valor_visible(descriptor, "cabello") == valor


@pytest.mark.parametrize("mod", MODULOS)
@pytest.mark.parametrize("v1, v2, campo, coincide", [
    ("negro/azul", "azul/negro", "color_ropa_superior", True),   # mismo par en otro orden
    ("gris", "gris/azul", "color_ropa_inferior", True),          # alcanza con un color en comun
    ("rojo", "verde", "color_ropa_superior", False),
    ("media", "media", "complexion", True),
    ("corto oscuro", "corto", "cabello", False),                 # el resto de los campos: igualdad exacta
])
def test_valores_coinciden(mod, v1, v2, campo, coincide):
    assert mod._valores_coinciden(v1, v2, campo) is coincide


@pytest.mark.parametrize("mod", MODULOS)
def test_comparar_descriptores_solo_cuenta_campos_visibles_en_ambos(mod):
    otro = {**DESC, "cabello": "largo claro", "accesorios": "no visible"}
    assert mod._comparar_descriptores(DESC, otro) == (3, 4)   # 4 comparables, 3 coinciden


@pytest.mark.parametrize("mod", MODULOS)
def test_obligatorios(mod):
    assert mod._obligatorios_coinciden(DESC, {**DESC, "color_ropa_superior": "verde"}) is False
    assert mod._obligatorios_coinciden(DESC, {**DESC, "color_ropa_superior": "no visible"}) is True
    distinto_abajo = {**DESC, "color_ropa_inferior": "negro"}
    assert mod._obligatorios_coinciden(DESC, distinto_abajo) is True                 # cliente: no exige inferior
    assert mod._obligatorios_coinciden(DESC, distinto_abajo, estricto=True) is False  # empleado: exige ambos


# ── Activacion y rate limiting ────────────────────────────────────────────────

@pytest.mark.parametrize("mod, clase, nombre, etiqueta", PROVEEDORES)
def test_activacion_segun_config_dependencias_y_keys(mod, clase, nombre, etiqueta, capsys):
    assert crear(clase, nombre).activo is True
    assert crear(clase, nombre, activo=False).activo is False
    assert capsys.readouterr().out == ""
    sin_dependencias = crear(clase, nombre, **{f"has_{nombre}": False})
    assert sin_dependencias.activo is False and f"[{etiqueta}]" in capsys.readouterr().out
    assert crear(clase, nombre, keys=()).activo is False
    assert "No hay API keys" in capsys.readouterr().out


@pytest.mark.parametrize("mod, clase, nombre, etiqueta", PROVEEDORES)
def test_desactivado_no_hace_nada(mod, clase, nombre, etiqueta):
    r = crear(clase, nombre, activo=False)
    assert r.generar_descripcion(CROP) is None
    assert r.clasificar(CROP, [{"sid": 1, "descripcion": DESC}]) is None


@pytest.mark.parametrize("mod, clase, nombre, etiqueta", PROVEEDORES)
def test_intervalo_minimo_y_pausa_extra_ante_una_rafaga(mod, clase, nombre, etiqueta, sin_esperas, capsys):
    r = crear(clase, nombre, min_intervalo_seg=10, rafaga_umbral=2, pausa_rafaga_seg=30)
    r.esperar_turno()                    # primera llamada: no espera
    assert sin_esperas == []
    r.esperar_turno()                    # segunda: intervalo minimo + rafaga (2 eventos en la ventana)
    assert 39 < sin_esperas[-1] <= 40
    assert f"[{etiqueta}] Rafaga detectada (2 eventos" in capsys.readouterr().out


@pytest.mark.parametrize("mod, clase, nombre, etiqueta", PROVEEDORES)
def test_la_rafaga_solo_cuenta_eventos_dentro_de_la_ventana(mod, clase, nombre, etiqueta, monkeypatch):
    import time
    reloj = iter([0.0, 100.0, 100.5])
    monkeypatch.setattr(time, "monotonic", lambda: next(reloj))
    r = crear(clase, nombre, ventana_rafaga_seg=60)
    assert r._registrar_evento_y_medir_rafaga() == 1
    assert r._registrar_evento_y_medir_rafaga() == 1   # el de t=0 ya salio de la ventana
    assert r._registrar_evento_y_medir_rafaga() == 2


# ── generar_descripcion ───────────────────────────────────────────────────────

def con_respuestas(monkeypatch, r, *respuestas):
    llamadas = []
    pendientes = list(respuestas)

    def generar(imagen, prompt, *a, **k):
        llamadas.append(prompt)
        return pendientes.pop(0)

    monkeypatch.setattr(r, "_generar_contenido", generar)
    return llamadas


@pytest.mark.parametrize("mod, clase, nombre, etiqueta", PROVEEDORES)
def test_descripcion_valida(mod, clase, nombre, etiqueta, monkeypatch):
    r = crear(clase, nombre)
    llamadas = con_respuestas(monkeypatch, r, json.dumps(DESC))
    assert r.generar_descripcion(CROP) == DESC
    assert "SIN reconocimiento facial" in llamadas[0] and "'no visible'" in llamadas[0]


@pytest.mark.parametrize("mod, clase, nombre, etiqueta", PROVEEDORES)
def test_respuesta_no_parseable_se_reintenta_una_vez(mod, clase, nombre, etiqueta, monkeypatch, capsys):
    r = crear(clase, nombre)
    llamadas = con_respuestas(monkeypatch, r, "no es json", json.dumps(DESC))
    assert r.generar_descripcion(CROP) == DESC and len(llamadas) == 2
    assert f"[{etiqueta}] Respuesta no parseable al generar descripcion (intento 1/2)" in capsys.readouterr().out


@pytest.mark.parametrize("mod, clase, nombre, etiqueta", PROVEEDORES)
def test_dos_respuestas_no_parseables_o_falla_de_la_api_dan_none(mod, clase, nombre, etiqueta, monkeypatch):
    r = crear(clase, nombre)
    con_respuestas(monkeypatch, r, "x", "[1]")              # dos respuestas invalidas seguidas
    assert r.generar_descripcion(CROP) is None
    llamadas = con_respuestas(monkeypatch, r, None)          # la llamada fallo: no se reintenta
    assert r.generar_descripcion(CROP) is None and len(llamadas) == 1


# ── clasificar ────────────────────────────────────────────────────────────────

AHORA = datetime(2026, 10, 7, 15, 0, 0)


def cand(sid, **cambios):
    return {"sid": sid, "descripcion": {**DESC, **cambios}, "primera_deteccion": AHORA - timedelta(hours=2)}


@pytest.fixture
def reid(request, monkeypatch):
    mod, clase, nombre, etiqueta = request.param
    r = crear(clase, nombre)
    monkeypatch.setattr(r, "generar_descripcion", lambda crop: dict(DESC))
    r.etiqueta = etiqueta
    return r


@pytest.mark.parametrize("reid", REIDS, indirect=True)
def test_acepta_al_candidato_con_mas_coincidencias(reid, capsys):
    candidatos = [cand(1, cabello="largo claro", complexion="robusta"), cand(2, accesorios="mochila"), cand(3)]
    assert reid.clasificar(CROP, candidatos, momento=AHORA) == 3
    assert f"[{reid.etiqueta}] Candidato 3 con 5/5" in capsys.readouterr().out


@pytest.mark.parametrize("reid", REIDS, indirect=True)
def test_sin_candidatos_no_llama_a_la_api(reid, monkeypatch):
    monkeypatch.setattr(reid, "generar_descripcion", lambda crop: pytest.fail("no debia describir"))
    assert reid.clasificar(CROP, []) is None


@pytest.mark.parametrize("reid", REIDS, indirect=True)
def test_color_superior_distinto_descarta_al_candidato(reid, capsys):
    assert reid.clasificar(CROP, [cand(1, color_ropa_superior="verde")]) is None
    assert "Ningun candidato" in capsys.readouterr().out


@pytest.mark.parametrize("reid", REIDS, indirect=True)
def test_sin_campos_visibles_en_comun_no_hay_evidencia(reid):
    oculto = {c: "no visible" for c in DESC}
    assert reid.clasificar(CROP, [{"sid": 1, "descripcion": oculto}, {"sid": 2, "descripcion": None}]) is None


@pytest.mark.parametrize("reid", REIDS, indirect=True)
def test_por_debajo_del_minimo_de_coincidencias_se_descarta(reid, capsys):
    # 2 de 5 coinciden (superior e inferior), minimo 3
    assert reid.clasificar(CROP, [cand(1, complexion="robusta", cabello="calvo", accesorios="gorra")]) is None
    assert "(< 3 minimo) -> descartado" in capsys.readouterr().out


@pytest.mark.parametrize("reid", REIDS, indirect=True)
def test_el_minimo_se_escala_si_hay_pocos_campos_comparables(reid):
    # Solo la remera visible en el candidato: 1 comparable, 1 coincidencia -> alcanza (min(3, 1) = 1)
    solo_remera = {c: "no visible" for c in DESC} | {"color_ropa_superior": "rojo"}
    assert reid.clasificar(CROP, [{"sid": 8, "descripcion": solo_remera}]) == 8


@pytest.mark.parametrize("reid", REIDS, indirect=True)
def test_aparecer_al_mismo_tiempo_en_otra_camara_suma_un_punto(reid, capsys):
    # 2 de 3 comparables coinciden: sin el bonus no llega al minimo (3); con el bonus si
    parecido = {**DESC, "complexion": "robusta", "cabello": "no visible", "accesorios": "no visible"}
    lejos = {"sid": 4, "descripcion": parecido, "primera_deteccion": AHORA - timedelta(minutes=5)}
    cerca = {"sid": 5, "descripcion": parecido, "primera_deteccion": AHORA - timedelta(seconds=60)}
    assert reid.clasificar(CROP, [lejos], momento=AHORA) is None
    assert reid.clasificar(CROP, [lejos, cerca], momento=AHORA) == 5
    assert "+ mismo momento en otra camara" in capsys.readouterr().out


@pytest.mark.parametrize("reid", REIDS, indirect=True)
def test_si_no_se_puede_describir_la_aparicion_nueva_no_clasifica(reid, monkeypatch):
    monkeypatch.setattr(reid, "generar_descripcion", lambda crop: None)
    assert reid.clasificar(CROP, [cand(1)]) is None


# ── Contrato con cada SDK ─────────────────────────────────────────────────────

class ErrorSDK(Exception):
    def __init__(self, msg="error", code=None, status_code=None):
        super().__init__(msg)
        self.code, self.status_code = code, status_code


def guion(*pasos):
    """Cliente falso: cada llamada consume el siguiente paso (una respuesta o una excepcion a lanzar)."""
    pendientes, recibidos = list(pasos), []

    def llamar(**kwargs):
        recibidos.append(kwargs)
        paso = pendientes.pop(0)
        if isinstance(paso, Exception):
            raise paso
        return paso

    return llamar, recibidos


# Gemini (google-genai)

@pytest.fixture
def sdk_gemini(monkeypatch):
    class ClientError(ErrorSDK):
        pass

    class ServerError(ErrorSDK):
        pass

    estado = types.SimpleNamespace(llamar=None, keys=[])

    class Client:
        def __init__(self, api_key):
            estado.keys.append(api_key)
            self.models = types.SimpleNamespace(generate_content=estado.llamar)

    monkeypatch.setattr(gemini_reid, "genai", types.SimpleNamespace(Client=Client))
    monkeypatch.setattr(gemini_reid, "types", types.SimpleNamespace(GenerateContentConfig=lambda **k: k))
    monkeypatch.setattr(gemini_reid, "ClientError", ClientError)
    monkeypatch.setattr(gemini_reid, "ServerError", ServerError)
    estado.ClientError, estado.ServerError = ClientError, ServerError
    return estado


def test_gemini_pide_json_con_temperatura_cero(sdk_gemini):
    sdk_gemini.llamar, recibidos = guion(types.SimpleNamespace(text='{"a": 1}'))
    r = crear(gemini_reid.GeminiReID, "gemini")
    assert r._generar_contenido("imagen", "prompt", json_response=True) == '{"a": 1}'
    assert recibidos[0]["model"] == "modelo-x" and recibidos[0]["contents"] == ["imagen", "prompt"]
    assert recibidos[0]["config"] == {"temperature": 0, "response_mime_type": "application/json"}


def test_gemini_ante_cupo_agotado_o_error_del_servidor_prueba_la_siguiente_key(sdk_gemini, sin_esperas):
    sdk_gemini.llamar, _ = guion(sdk_gemini.ClientError(code=429), types.SimpleNamespace(text="ok"))
    assert crear(gemini_reid.GeminiReID, "gemini")._generar_contenido("i", "p") == "ok"
    assert sdk_gemini.keys == ["k1", "k2"]
    sdk_gemini.llamar, _ = guion(sdk_gemini.ServerError(code=503), types.SimpleNamespace(text="ok"))
    assert crear(gemini_reid.GeminiReID, "gemini")._generar_contenido("i", "p") == "ok"
    assert sin_esperas == [2]


@pytest.mark.parametrize("errores, mensaje", [
    (["cliente400"], "Error de cliente"),
    ([RuntimeError("raro")], "Error inesperado"),
    (["cupo", "cupo"], "Todas las API keys fallaron"),
])
def test_gemini_errores_que_cortan_la_llamada(sdk_gemini, capsys, errores, mensaje):
    traducir = {"cliente400": sdk_gemini.ClientError(code=400), "cupo": sdk_gemini.ClientError(code=429)}
    sdk_gemini.llamar, _ = guion(*[traducir.get(e, e) for e in errores])
    assert crear(gemini_reid.GeminiReID, "gemini")._generar_contenido("i", "p") is None
    assert mensaje in capsys.readouterr().out


def test_gemini_convierte_el_recorte_de_bgr_a_rgb():
    img = crear(gemini_reid.GeminiReID, "gemini")._crop_a_imagen(CROP)
    assert img.getpixel((0, 0)) == (220, 0, 0)


def test_gemini_recorte_invalido_no_se_envia(capsys):
    assert crear(gemini_reid.GeminiReID, "gemini")._crop_a_imagen("no es una imagen") is None
    assert "No se pudo preparar el crop" in capsys.readouterr().out


# Groq

@pytest.fixture
def sdk_groq(monkeypatch):
    class APIStatusError(ErrorSDK):
        pass

    class APIConnectionError(ErrorSDK):
        pass

    estado = types.SimpleNamespace(llamar=None, keys=[])

    class Groq:
        def __init__(self, api_key):
            estado.keys.append(api_key)
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=estado.llamar))

    monkeypatch.setattr(groq_reid, "Groq", Groq)
    monkeypatch.setattr(groq_reid, "APIStatusError", APIStatusError)
    monkeypatch.setattr(groq_reid, "APIConnectionError", APIConnectionError)
    estado.APIStatusError, estado.APIConnectionError = APIStatusError, APIConnectionError
    return estado


def respuesta_groq(texto):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=texto))])


def test_groq_manda_la_imagen_como_data_uri_y_pide_json(sdk_groq):
    sdk_groq.llamar, recibidos = guion(respuesta_groq('{"a": 1}'))
    r = crear(groq_reid.GroqReID, "groq")
    assert r._generar_contenido("QUJD", "prompt", json_response=True) == '{"a": 1}'
    pedido = recibidos[0]
    assert pedido["temperature"] == 0 and pedido["response_format"] == {"type": "json_object"}
    contenido = pedido["messages"][0]["content"]
    assert contenido[0] == {"type": "text", "text": "prompt"}
    assert contenido[1]["image_url"]["url"] == "data:image/jpeg;base64,QUJD"
    sdk_groq.llamar, recibidos = guion(respuesta_groq("x"))
    r._generar_contenido("QUJD", "prompt")
    assert "response_format" not in recibidos[0]


@pytest.mark.parametrize("primero", ["429", "503", "red"])
def test_groq_errores_transitorios_prueban_la_siguiente_key(sdk_groq, primero, sin_esperas):
    error = {"429": sdk_groq.APIStatusError(status_code=429), "503": sdk_groq.APIStatusError(status_code=503),
             "red": sdk_groq.APIConnectionError()}[primero]
    sdk_groq.llamar, _ = guion(error, respuesta_groq("ok"))
    assert crear(groq_reid.GroqReID, "groq")._generar_contenido("b64", "p") == "ok"
    assert sdk_groq.keys == ["k1", "k2"]
    assert sin_esperas == ([2] if primero == "red" else [])


@pytest.mark.parametrize("errores, mensaje", [
    (["400"], "Error de cliente"), (["raro"], "Error inesperado"), (["429", "429"], "Todas las API keys fallaron")])
def test_groq_errores_que_cortan_la_llamada(sdk_groq, capsys, errores, mensaje):
    traducir = {"400": sdk_groq.APIStatusError(status_code=400), "429": sdk_groq.APIStatusError(status_code=429),
                "raro": RuntimeError("raro")}
    sdk_groq.llamar, _ = guion(*[traducir[e] for e in errores])
    assert crear(groq_reid.GroqReID, "groq")._generar_contenido("b64", "p") is None
    assert mensaje in capsys.readouterr().out


def test_groq_codifica_el_recorte_en_jpeg_base64(capsys):
    r = crear(groq_reid.GroqReID, "groq")
    jpg = base64.b64decode(r._crop_a_base64(CROP))
    assert cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR).shape == CROP.shape
    assert r._crop_a_base64(np.zeros((0, 0, 3), np.uint8)) is None
    assert r._crop_a_base64("no es una imagen") is None


# Claude (anthropic)

@pytest.fixture
def sdk_claude(monkeypatch):
    class APIStatusError(ErrorSDK):
        pass

    class RateLimitError(APIStatusError):
        pass

    class APIConnectionError(ErrorSDK):
        pass

    estado = types.SimpleNamespace(llamar=None, keys=[])

    class Anthropic:
        def __init__(self, api_key):
            estado.keys.append(api_key)
            self.messages = types.SimpleNamespace(create=estado.llamar)

    monkeypatch.setattr(claude_reid, "anthropic", types.SimpleNamespace(
        Anthropic=Anthropic, APIStatusError=APIStatusError, RateLimitError=RateLimitError,
        APIConnectionError=APIConnectionError))
    estado.APIStatusError, estado.RateLimitError = APIStatusError, RateLimitError
    estado.APIConnectionError = APIConnectionError
    return estado


def respuesta_claude(texto='{"a": 1}', stop="end_turn", con_texto=True):
    bloques = [types.SimpleNamespace(type="text", text=texto)] if con_texto else []
    return types.SimpleNamespace(stop_reason=stop, content=bloques,
                                 usage=types.SimpleNamespace(input_tokens=10, output_tokens=5))


@pytest.mark.parametrize("modelo, temperatura, thinking", [
    ("claude-haiku-4-5", 0, None),                        # Haiku: temperature 0, sin thinking configurable
    ("claude-opus-5-5", None, {"type": "disabled"}),      # Opus/Sonnet/Fable: thinking apagado + effort bajo
])
def test_claude_fuerza_el_esquema_json_y_ajusta_parametros_por_modelo(sdk_claude, modelo, temperatura, thinking):
    sdk_claude.llamar, recibidos = guion(respuesta_claude())
    r = crear(claude_reid.ClaudeReID, "claude", model=modelo)
    assert r._generar_contenido("QUJD", "prompt") == '{"a": 1}'
    pedido = recibidos[0]
    assert pedido["output_config"]["format"] == {"type": "json_schema", "schema": claude_reid.DESCRIPTOR_SCHEMA}
    assert pedido.get("temperature") == temperatura and pedido.get("thinking") == thinking
    assert pedido["output_config"].get("effort") == (None if temperatura == 0 else "low")
    imagen, texto = pedido["messages"][0]["content"]
    assert imagen["source"] == {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}
    assert texto == {"type": "text", "text": "prompt"}


@pytest.mark.parametrize("respuesta, mensaje", [
    (respuesta_claude(stop="refusal"), "rechazada por los filtros"),
    (respuesta_claude(con_texto=False, stop="max_tokens"), "sin bloque de texto"),
])
def test_claude_respuestas_sin_descripcion_usable(sdk_claude, capsys, respuesta, mensaje):
    sdk_claude.llamar, _ = guion(respuesta)
    assert crear(claude_reid.ClaudeReID, "claude")._generar_contenido("b64", "p") is None
    assert mensaje in capsys.readouterr().out


@pytest.mark.parametrize("primero, pausas", [("429", []), ("red", [2]), ("500", [2])])
def test_claude_errores_transitorios_prueban_la_siguiente_key(sdk_claude, sin_esperas, primero, pausas):
    error = {"429": sdk_claude.RateLimitError(status_code=429), "red": sdk_claude.APIConnectionError(),
             "500": sdk_claude.APIStatusError(status_code=500)}[primero]
    sdk_claude.llamar, _ = guion(error, respuesta_claude())
    assert crear(claude_reid.ClaudeReID, "claude")._generar_contenido("b64", "p") == '{"a": 1}'
    assert sdk_claude.keys == ["k1", "k2"] and sin_esperas == pausas


@pytest.mark.parametrize("errores, mensaje", [
    (["400"], "Error de cliente"), (["raro"], "Error inesperado"), (["429", "429"], "Todas las API keys fallaron")])
def test_claude_errores_que_cortan_la_llamada(sdk_claude, capsys, errores, mensaje):
    traducir = {"400": sdk_claude.APIStatusError(status_code=400), "429": sdk_claude.RateLimitError(status_code=429),
                "raro": RuntimeError("raro")}
    sdk_claude.llamar, _ = guion(*[traducir[e] for e in errores])
    assert crear(claude_reid.ClaudeReID, "claude")._generar_contenido("b64", "p") is None
    assert mensaje in capsys.readouterr().out


@pytest.mark.parametrize("alto, alto_enviado", [(200, 384), (500, 500)])
def test_claude_agranda_los_recortes_chicos(alto, alto_enviado):
    crop = np.zeros((alto, 80, 3), np.uint8)
    jpg = base64.b64decode(crear(claude_reid.ClaudeReID, "claude")._crop_a_base64(crop))
    assert cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR).shape[0] == alto_enviado


def test_claude_recorte_invalido_no_se_envia(capsys):
    assert crear(claude_reid.ClaudeReID, "claude")._crop_a_base64("no es una imagen") is None
    assert "No se pudo preparar el crop" in capsys.readouterr().out


def test_claude_informa_la_descripcion_obtenida(monkeypatch, capsys):
    r = crear(claude_reid.ClaudeReID, "claude")
    con_respuestas(monkeypatch, r, json.dumps(DESC))
    r.generar_descripcion(CROP)
    salida = capsys.readouterr().out
    assert "[Claude] Enviando crop de persona" in salida and '[Claude] Descripcion: {"color_ropa_superior"' in salida

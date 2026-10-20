"""MatchingAgent (deteccion_productos): del JSON que devuelve el LLM al producto del catalogo.

Se prueba con el catalogo real de data/productos.csv (el mismo que carga StockAgent sin base) y con
catalogos chicos armados a mano para aislar cada regla (piso de marca, ambiguedad, umbrales).
"""
import pytest

import config
import test_matching as calibracion   # deteccion_productos/test_matching.py: casos reales de calibracion
from agents import stock_agent
from agents.matching_agent import (MatchingAgent, _mejor_similitud_contra_tokens, _score_tamano,
                                   convertir_a_ml, normalizar, similitud)


@pytest.fixture(scope="module")
def catalogo():
    import os
    from pathlib import Path
    from unittest import mock
    csv = Path(stock_agent.__file__).resolve().parent.parent / config.CSV_PATH
    with mock.patch.object(stock_agent, "CSV_PATH", str(csv)), mock.patch.dict(os.environ, clear=False) as env:
        env.pop("DATABASE_URL", None)
        return stock_agent.StockAgent().cargar_productos()


@pytest.fixture(scope="module")
def matcher(catalogo):
    return MatchingAgent(catalogo)


def producto(sku, marca, variante, valor, unidad, nombre=None):
    return {"sku": sku, "nombre": nombre or f"{marca} {variante} {valor}{unidad}", "marca": marca,
            "variante": variante, "tamano_valor": valor, "tamano_unidad": unidad, "categoria": "x"}


def llm(marca, variante=None, valor=None, unidad=None, nombre=None, confianza=0.9):
    return {"producto_detectado": True, "marca": marca, "nombre_producto": nombre or marca,
            "variante": variante, "tamano": {"valor": valor, "unidad": unidad} if valor is not None else None,
            "categoria": "x", "confianza": confianza}


# ── Funciones de texto ───────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada, esperado", [
    ("Coca-Cola", "coca cola"),
    ("  Clásicas   Lays ", "clasicas lays"),
    ("PIÑA", "pina"),
    (None, ""),
    ("", ""),
])
def test_normalizar(entrada, esperado):
    assert normalizar(entrada) == esperado


def test_similitud_texto_identico_es_100():
    assert similitud("milka", "milka") == 100


@pytest.mark.parametrize("a, b, ediciones", [
    ("tofi", "toff", 1),            # corto (<=5): tolera 1
    ("orignal", "original", 1),     # medio (6-9): tolera 2
    ("gatoradde", "gatorade", 1),
    ("villa del sr", "villa del sur", 1),
    ("vila dl sur", "villa del sur", 2),   # largo (10+): tolera 3
])
def test_similitud_tolera_typos_segun_largo(a, b, ediciones):
    assert similitud(a, b) == 100 - 5 * ediciones


def test_similitud_corto_no_tolera_dos_ediciones():
    assert similitud("lays", "ladz") == 0


@pytest.mark.parametrize("a, b", [("lays", "ades"), ("chuker", "cofler"), ("saladix", "guaymallen")])
def test_similitud_palabras_sin_relacion_dan_cero(a, b):
    # Con un % generico (fuzz.ratio) estos pares daban ~50 por letras sueltas en comun.
    assert similitud(a, b) == 0


def test_similitud_por_contencion_es_proporcional_a_lo_que_cubre():
    assert similitud("negro", "chocolate negro") == pytest.approx(100 * 5 / 15)
    assert similitud("chocolate negro", "negro") == pytest.approx(100 * 5 / 15)


@pytest.mark.parametrize("a, b", [("", "milka"), ("milka", ""), (None, "x")])
def test_similitud_con_vacio_es_cero(a, b):
    assert similitud(a, b) == 0


def test_mejor_similitud_contra_tokens_busca_la_marca_palabra_por_palabra():
    assert _mejor_similitud_contra_tokens("alfajor toffi negro", "tofi") == 95


def test_mejor_similitud_contra_tokens_agrupa_marcas_de_varias_palabras():
    assert _mejor_similitud_contra_tokens("bizcochos 9 de oro agridulces", "9 de oro") == 100


def test_mejor_similitud_contra_tokens_texto_mas_corto_que_la_marca():
    assert _mejor_similitud_contra_tokens("oro", "9 de oro") == pytest.approx(100 * 3 / 8)


@pytest.mark.parametrize("texto, objetivo", [("", "tofi"), ("tofi", "")])
def test_mejor_similitud_contra_tokens_vacio(texto, objetivo):
    assert _mejor_similitud_contra_tokens(texto, objetivo) == 0


# ── Tamaños ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor, unidad, esperado", [
    (500, "ml", (500, "volumen")),
    (500, "CC", (500, "volumen")),
    (1.5, "l", (1500, "volumen")),
    (2, " Litros ", (2000, "volumen")),
    (1, "lt", (1000, "volumen")),
    (46, "g", (46, "peso")),
    (46, "gr", (46, "peso")),
    (1, "kg", (1000, "peso")),
    (6, "unidades", (6, "unidades")),
    (6, "u", (6, "unidades")),
    (3, "oz", (3, "otro")),
    (None, "ml", (None, None)),
    (500, None, (None, None)),
])
def test_convertir_a_ml(valor, unidad, esperado):
    assert convertir_a_ml(valor, unidad) == esperado


def test_score_tamano_exacto_es_100_aunque_cambie_la_unidad():
    assert _score_tamano({"tamano_valor": 1.5, "tamano_unidad": "l"}, 1500, "ml") == 100


def test_score_tamano_es_proporcional_al_desvio():
    # 46g leido como 40g: desvio 13 % -> ~80 puntos (ver PENALIZACION_TAMANO en config.py)
    assert _score_tamano({"tamano_valor": 46, "tamano_unidad": "g"}, 40, "g") == pytest.approx(
        100 - (6 / 46) * config.PENALIZACION_TAMANO)


def test_score_tamano_nunca_es_negativo():
    assert _score_tamano({"tamano_valor": 500, "tamano_unidad": "ml"}, 1.5, "l") == 0


@pytest.mark.parametrize("prod, valor, unidad", [
    ({"tamano_valor": 500, "tamano_unidad": "ml"}, 500, "g"),    # volumen vs peso
    ({"tamano_valor": None, "tamano_unidad": None}, 500, "ml"),  # producto sin tamano
    ({"tamano_valor": 500, "tamano_unidad": "ml"}, None, None),  # el LLM no lo leyo
])
def test_score_tamano_sin_comparacion_posible_es_cero(prod, valor, unidad):
    assert _score_tamano(prod, valor, unidad) == 0


# ── identificar(): casos de calibracion reales ───────────────────────────────

@pytest.mark.parametrize("datos_llm, sku_esperado", calibracion.CASOS,
                         ids=[f"{i:02d}-{c[0].get('marca', 'sin_producto')}" for i, c in enumerate(calibracion.CASOS)])
def test_calibracion_identifica_el_producto_esperado(matcher, datos_llm, sku_esperado):
    """Los mismos casos de deteccion_productos/test_matching.py: si alguien toca un umbral de config.py y un
    caso real que andaba deja de andar, el pipeline lo frena."""
    r = matcher.identificar(datos_llm)
    obtenido = None if r["estado"] == "no_reconocido" else r["producto"]["sku"]
    assert obtenido == sku_esperado


# ── identificar(): cada regla aislada ────────────────────────────────────────

def test_sin_producto_detectado():
    r = MatchingAgent([producto("A", "Milka", "Leche", 100, "g")]).identificar({"producto_detectado": False})
    assert r == {"estado": "no_reconocido", "razon": "sin_producto", "datos_llm": {"producto_detectado": False}}


def test_confianza_del_llm_bajo_el_umbral():
    datos = llm("Milka", "Leche", 100, "g", confianza=config.UMBRAL_CONFIANZA_LLM - 0.01)
    r = MatchingAgent([producto("A", "Milka", "Leche", 100, "g")]).identificar(datos)
    assert (r["estado"], r["razon"]) == ("no_reconocido", "confianza_llm_baja")


def test_confianza_justo_en_el_umbral_se_procesa():
    datos = llm("Milka", "Leche", 100, "g", confianza=config.UMBRAL_CONFIANZA_LLM)
    r = MatchingAgent([producto("A", "Milka", "Leche", 100, "g")]).identificar(datos)
    assert r["estado"] == "reconocido"


def test_reconocido_devuelve_producto_y_confianza_del_llm():
    p = producto("A", "Milka", "Leche", 100, "g")
    r = MatchingAgent([p]).identificar(llm("Milka", "Leche", 100, "g", confianza=0.93))
    assert r == {"estado": "reconocido", "producto": p, "confianza": 0.93}


def test_marca_distinta_no_compite_aunque_coincida_el_tamano():
    r = MatchingAgent([producto("A", "Guaymallen", "Negro", 40, "g")]).identificar(
        llm("Saladix", "Calabresa", 40, "g"))
    assert (r["estado"], r["razon"]) == ("no_reconocido", "marca_no_esta_en_base")


def test_marca_dentro_del_nombre_rescata_si_el_llm_invirtio_los_campos():
    p = producto("A", "Tofi", "Chocolate Negro", 46, "g")
    r = MatchingAgent([p]).identificar(llm("Alfajor", "Chocolate Negro", 46, "g", nombre="Alfajor Tofi Negro"))
    assert r["estado"] == "reconocido" and r["producto"] is p


def test_respaldo_por_nombre_no_gana_con_parecido_debil():
    # "oro" dentro de "9 de oro" con una sola palabra -> 37.5 < UMBRAL_RESPALDO_NOMBRE: no rescata
    r = MatchingAgent([producto("A", "9 de Oro", "Agridulce", 200, "g")]).identificar(
        llm("Galletitas", None, 200, "g", nombre="oro"))
    assert r["razon"] == "marca_no_esta_en_base"


def test_variante_sin_dato_es_neutra_y_variante_vacia_del_catalogo_cuenta_como_original():
    sin_variante = producto("A", "Sprite", None, 500, "ml")
    r = MatchingAgent([sin_variante]).identificar(llm("Sprite", "Original", 500, "ml"))
    assert r["estado"] == "reconocido"
    r = MatchingAgent([sin_variante]).identificar(llm("Sprite", None, 500, "ml"))
    # marca 100*0.40 + variante neutra 50*0.25 + tamano 100*0.35 = 87.5
    assert r["estado"] == "reconocido"


def test_score_bajo_el_umbral_de_descarte_informa_el_mas_cercano():
    r = MatchingAgent([producto("A", "Milka", "Leche", 100, "g")]).identificar(llm("Milka", "Almendras", 500, "ml"))
    assert r["estado"] == "no_reconocido"
    assert r["razon"] == "sin_coincidencia_suficiente"
    assert r["candidato_mas_cercano"] == "A"
    assert r["score_mas_cercano"] == 40.0   # solo la marca: 100 * 0.40


def test_dos_candidatos_parejos_piden_confirmar_por_multiples_matches():
    a = producto("A", "Lays", "Clasicas", 100, "g")
    b = producto("B", "Lays", "Clasicas", 105, "g")
    r = MatchingAgent([a, b]).identificar(llm("Lays", "Clasicas", 100, "g"))
    assert r["estado"] == "confirmar"
    assert r["motivo"] == "multiples_matches"
    assert r["producto"] is a and r["candidatos"] == [a, b]


def test_score_razonable_pero_no_alto_pide_confirmar_por_similitud_baja():
    p = producto("A", "Chuker", None, 200, "ml")
    r = MatchingAgent([p]).identificar(llm("Chuker", None, 150, "ml"))
    assert config.UMBRAL_DESCARTE <= 40 + 12.5 + (100 - 0.25 * config.PENALIZACION_TAMANO) * 0.35 \
        < config.UMBRAL_AUTOACEPTAR
    assert (r["estado"], r["motivo"]) == ("confirmar", "similitud_baja")
    assert r["candidatos"] == [p]


def test_candidatos_bajo_el_piso_no_se_muestran_aunque_sean_de_la_marca():
    bueno = producto("A", "Ades", "Manzana", 1, "l")
    malo1 = producto("B", "Ades", "Durazno", 200, "ml")
    malo2 = producto("C", "Ades", "Naranja", 200, "ml")
    r = MatchingAgent([malo1, bueno, malo2]).identificar(llm("Ades", "Manzana", 1.4, "l"))
    assert r["estado"] == "confirmar"
    assert r["candidatos"] == [bueno]


def test_como_mucho_tres_candidatos():
    prods = [producto(str(i), "Lays", "Clasicas", 100 + i, "g") for i in range(5)]
    r = MatchingAgent(prods).identificar(llm("Lays", "Clasicas", 100, "g"))
    assert r["estado"] == "confirmar" and len(r["candidatos"]) == 3


def test_catalogo_vacio():
    r = MatchingAgent([]).identificar(llm("Milka", "Leche", 100, "g"))
    assert r["razon"] == "marca_no_esta_en_base"

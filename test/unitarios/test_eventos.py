"""Tests unitarios de deteccion/pipeline/eventos.py -- maquina de estados PURA
(Escenario A=COMPRA_NORMAL, B=POSIBLE_HURTO, C=TRANSITO_SIN_COMPRA) que
clasifica una visita ya cerrada. Sin YOLO, sin BD, sin llamadas a Gemini/Groq/
Claude -- esta clasificacion es determinista una vez que se conoce la
secuencia de zonas, tomar_producto y paso_por_caja (este ultimo ya resuelto
por PersonTracker.marcar_acercamiento_caja via proximidad + companero
presente, no por si 'caja' aparece en la secuencia de zonas -- ver comentario
en clasificar_evento). paso_por_caja es la condicion DOMINANTE: cubre compra
en gondola, compra directa en el mostrador y pedido preparado en cocina, que
tomar_producto (deteccion YOLO) nunca podria confirmar por si solo."""
from deteccion.pipeline.eventos import clasificar_evento, resumen_evento

ZONA_NOMBRE = {1: "Entrada", 2: "Gondola A", 3: "Caja", 4: "Salon"}


def _clasificar(secuencia, tomo_producto, paso_por_caja):
    return clasificar_evento(secuencia, tomo_producto, paso_por_caja, ZONA_NOMBRE)


# ── Escenario A: COMPRA_NORMAL ──────────────────────────────────────────────

def test_escenario_a_compra_normal_tomo_producto_y_se_acerco_a_caja():
    evento = _clasificar([1, 2, 4], tomo_producto=True, paso_por_caja=True)
    assert evento["accion_detectada"] == "COMPRA_NORMAL"
    assert evento["es_sospechoso"] is False
    assert evento["nivel_alerta"] == "NINGUNA"
    assert evento["paso_por_caja"] is True


def test_escenario_a_compra_en_el_mostrador_sin_tomar_producto_de_gondola():
    # Compra directa en caja (golosinas, cigarrillos) o pedido preparado en
    # cocina (cafe, tostado) -- el cliente nunca agarra nada de una gondola/
    # heladera (tomo_producto=False) pero SI se acerco a pagar con alguien
    # mas presente. paso_por_caja domina: sigue siendo COMPRA_NORMAL.
    evento = _clasificar([1, 3, 4], tomo_producto=False, paso_por_caja=True)
    assert evento["accion_detectada"] == "COMPRA_NORMAL"
    assert evento["es_sospechoso"] is False


# ── Escenario B: POSIBLE_HURTO ──────────────────────────────────────────────

def test_escenario_b_hurto_tomo_producto_sin_acercarse_a_caja():
    evento = _clasificar([1, 2, 4], tomo_producto=True, paso_por_caja=False)
    assert evento["accion_detectada"] == "POSIBLE_HURTO"
    assert evento["es_sospechoso"] is True
    assert evento["nivel_alerta"] == "ALTA"
    assert evento["paso_por_caja"] is False


def test_escenario_b_no_depende_de_que_caja_aparezca_en_la_secuencia():
    # 'paso_por_caja' viene resuelto aparte (proximidad, ver
    # PersonTracker.marcar_acercamiento_caja) -- que la zona 'Caja' (id=3) NO
    # figure en la secuencia no cambia nada si paso_por_caja=True, y que SI
    # figure tampoco alcanza si paso_por_caja=False (un cliente puede pasar
    # cerca de la zona caminando sin haber ido a pagar).
    evento_sin_zona_caja_pero_pago = _clasificar([1, 2, 4], tomo_producto=True, paso_por_caja=True)
    assert evento_sin_zona_caja_pero_pago["accion_detectada"] == "COMPRA_NORMAL"

    evento_con_zona_caja_pero_no_pago = _clasificar([1, 2, 3, 4], tomo_producto=True, paso_por_caja=False)
    assert evento_con_zona_caja_pero_no_pago["accion_detectada"] == "POSIBLE_HURTO"


# ── Escenario C: TRANSITO_SIN_COMPRA ────────────────────────────────────────

def test_escenario_c_transito_sin_tomar_producto():
    evento = _clasificar([1, 4, 1], tomo_producto=False, paso_por_caja=False)
    assert evento["accion_detectada"] == "TRANSITO_SIN_COMPRA"
    assert evento["es_sospechoso"] is False
    assert evento["nivel_alerta"] == "NINGUNA"


def test_escenario_c_ni_tomo_producto_ni_se_acerco_a_pagar():
    evento = _clasificar([1, 2, 4], tomo_producto=False, paso_por_caja=False)
    assert evento["accion_detectada"] == "TRANSITO_SIN_COMPRA"
    assert evento["es_sospechoso"] is False


# ── secuencia_zonas_recorridas ───────────────────────────────────────────────

def test_secuencia_zonas_recorridas_usa_nombres_legibles():
    evento = _clasificar([2, 3], tomo_producto=True, paso_por_caja=True)
    assert evento["secuencia_zonas_recorridas"] == ["Gondola A", "Caja"]


def test_zona_id_desconocida_cae_a_fallback_legible():
    evento = clasificar_evento([99], False, False, ZONA_NOMBRE)
    assert evento["secuencia_zonas_recorridas"] == ["zona_99"]


def test_secuencia_vacia_no_rompe_y_no_es_sospechoso():
    evento = _clasificar([], tomo_producto=False, paso_por_caja=False)
    assert evento["accion_detectada"] == "TRANSITO_SIN_COMPRA"
    assert evento["secuencia_zonas_recorridas"] == []


# ── resumen_evento ───────────────────────────────────────────────────────────

def test_resumen_evento_hurto_menciona_recorrido_y_alerta():
    evento = _clasificar([2, 4], tomo_producto=True, paso_por_caja=False)
    texto = resumen_evento(evento)
    assert "SIN pasar por caja" in texto
    assert "Gondola A -> Salon" in texto


def test_resumen_evento_compra_normal():
    evento = _clasificar([2, 3], tomo_producto=True, paso_por_caja=True)
    texto = resumen_evento(evento)
    assert "Compra normal" in texto
    assert "tomo un producto" in texto


def test_resumen_evento_compra_en_el_mostrador_sin_tomar_producto():
    evento = _clasificar([1, 3], tomo_producto=False, paso_por_caja=True)
    texto = resumen_evento(evento)
    assert "Compra normal" in texto
    assert "compro en el mostrador" in texto


def test_resumen_evento_transito():
    evento = _clasificar([1], tomo_producto=False, paso_por_caja=False)
    texto = resumen_evento(evento)
    assert "Transito sin compra" in texto


def test_resumen_evento_secuencia_vacia_usa_placeholder():
    evento = _clasificar([], tomo_producto=False, paso_por_caja=False)
    texto = resumen_evento(evento)
    assert "(sin zonas registradas)" in texto

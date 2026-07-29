"""Tests unitarios del estado por-visita que PersonTracker acumula para la
clasificacion Escenario A/B/C (secuencia de zonas, tomar_producto y
acercamiento a Zona Caja, ver pipeline/eventos.py). Se instancia PersonTracker
directo, sin YOLO/video/BD: estos metodos (actualizar_zona,
actualizar_interaccion, actualizar_acercamiento_caja, _cerrar_segmento) solo
tocan diccionarios en memoria, nunca 'gemini' ni resultados de deteccion."""
from deteccion.pipeline.tracking import PersonTracker


def _tracker(interaccion_frames_minimos=3, caja_frames_minimos=1, on_visita_cerrada=None):
    return PersonTracker(
        frame_skip=5,
        max_dist=100.0,
        quick_expiry_frames=10,
        long_expiry_frames=100,
        appearance_thresh=0.7,
        max_app_samples=20,
        descripcion_streak_frames=25,
        min_frames_confirmacion=3,
        gemini=None,  # no se usa en ninguno de estos metodos
        on_visita_cerrada=on_visita_cerrada,
        interaccion_frames_minimos=interaccion_frames_minimos,
        caja_frames_minimos=caja_frames_minimos,
    )


# ── actualizar_zona ──────────────────────────────────────────────────────────

def test_actualizar_zona_agrega_solo_en_los_cambios():
    t = _tracker()
    for zona in (10, 10, 20, 20, 10):
        t.actualizar_zona(1, zona)
    assert t.secuencia_zonas[1] == [10, 20, 10]


def test_actualizar_zona_ignora_none():
    t = _tracker()
    t.actualizar_zona(1, 10)
    t.actualizar_zona(1, None)
    t.actualizar_zona(1, 20)
    assert t.secuencia_zonas[1] == [10, 20]


def test_actualizar_zona_es_independiente_por_sid():
    t = _tracker()
    t.actualizar_zona(1, 10)
    t.actualizar_zona(2, 20)
    assert t.secuencia_zonas[1] == [10]
    assert t.secuencia_zonas[2] == [20]


# ── actualizar_interaccion ───────────────────────────────────────────────────

def test_actualizar_interaccion_confirma_tras_n_frames_consecutivos():
    t = _tracker(interaccion_frames_minimos=3)
    t.actualizar_interaccion(1, True)
    assert t.tomo_producto.get(1) is not True
    t.actualizar_interaccion(1, True)
    assert t.tomo_producto.get(1) is not True
    t.actualizar_interaccion(1, True)
    assert t.tomo_producto[1] is True


def test_actualizar_interaccion_resetea_contador_si_se_interrumpe_la_racha():
    t = _tracker(interaccion_frames_minimos=3)
    t.actualizar_interaccion(1, True)
    t.actualizar_interaccion(1, True)
    t.actualizar_interaccion(1, False)  # corta la racha antes de confirmar
    t.actualizar_interaccion(1, True)
    t.actualizar_interaccion(1, True)
    assert t.tomo_producto.get(1) is not True  # solo 2 consecutivos de nuevo
    t.actualizar_interaccion(1, True)
    assert t.tomo_producto[1] is True


def test_actualizar_interaccion_es_sticky_una_vez_confirmado():
    t = _tracker(interaccion_frames_minimos=1)
    t.actualizar_interaccion(1, True)
    assert t.tomo_producto[1] is True
    t.actualizar_interaccion(1, False)
    assert t.tomo_producto[1] is True  # no se revierte


def test_actualizar_interaccion_sin_producto_cerca_nunca_confirma():
    t = _tracker(interaccion_frames_minimos=2)
    t.actualizar_interaccion(1, False)
    t.actualizar_interaccion(1, False)
    assert t.tomo_producto.get(1) is not True


# ── actualizar_acercamiento_caja ─────────────────────────────────────────────

def test_actualizar_acercamiento_caja_confirma_tras_n_frames_consecutivos():
    # Exige permanencia (ver CAJA_PERMANENCIA_MINIMA_SEG): un solo frame
    # cerca del mostrador no alcanza, igual criterio que actualizar_interaccion.
    t = _tracker(caja_frames_minimos=3)
    t.actualizar_acercamiento_caja(1, True)
    assert t.acerco_a_caja.get(1) is not True
    t.actualizar_acercamiento_caja(1, True)
    assert t.acerco_a_caja.get(1) is not True
    t.actualizar_acercamiento_caja(1, True)
    assert t.acerco_a_caja[1] is True


def test_actualizar_acercamiento_caja_resetea_contador_si_se_interrumpe_la_racha():
    # Alguien que pasa CAMINANDO cerca del mostrador (sin quedarse) no debe
    # confirmar paso_por_caja aunque sume frames sueltos no consecutivos.
    t = _tracker(caja_frames_minimos=3)
    t.actualizar_acercamiento_caja(1, True)
    t.actualizar_acercamiento_caja(1, True)
    t.actualizar_acercamiento_caja(1, False)  # se aleja antes de completar el minimo
    t.actualizar_acercamiento_caja(1, True)
    t.actualizar_acercamiento_caja(1, True)
    assert t.acerco_a_caja.get(1) is not True  # solo 2 consecutivos de nuevo
    t.actualizar_acercamiento_caja(1, True)
    assert t.acerco_a_caja[1] is True


def test_actualizar_acercamiento_caja_es_sticky_una_vez_confirmado():
    t = _tracker(caja_frames_minimos=1)
    t.actualizar_acercamiento_caja(1, True)
    assert t.acerco_a_caja[1] is True
    t.actualizar_acercamiento_caja(1, False)
    assert t.acerco_a_caja[1] is True  # no se revierte al alejarse


def test_actualizar_acercamiento_caja_sin_estar_cerca_nunca_confirma():
    t = _tracker(caja_frames_minimos=2)
    t.actualizar_acercamiento_caja(1, False)
    t.actualizar_acercamiento_caja(1, False)
    assert t.acerco_a_caja.get(1) is not True


def test_sin_actualizar_acercamiento_caja_queda_false_por_default():
    t = _tracker()
    assert t.acerco_a_caja.get(1, False) is False


# ── _cerrar_segmento ─────────────────────────────────────────────────────────

def test_cerrar_segmento_pasa_secuencia_tomo_producto_y_acerco_a_caja_al_callback():
    cerrados = []

    def _on_visita_cerrada(sid, frame_inicio, frame_fin, secuencia, tomo_producto, acerco_a_caja):
        cerrados.append((sid, frame_inicio, frame_fin, secuencia, tomo_producto, acerco_a_caja))

    t = _tracker(interaccion_frames_minimos=1, caja_frames_minimos=1, on_visita_cerrada=_on_visita_cerrada)
    t.actualizar_zona(1, 10)
    t.actualizar_zona(1, 20)
    t.actualizar_interaccion(1, True)
    t.actualizar_acercamiento_caja(1, True)

    t._cerrar_segmento(1, 100, 500)

    assert cerrados == [(1, 100, 500, [10, 20], True, True)]


def test_cerrar_segmento_sin_zonas_ni_interaccion_pasa_vacio_y_false():
    cerrados = []
    t = _tracker(on_visita_cerrada=lambda *args: cerrados.append(args))
    t._cerrar_segmento(1, 0, 50)
    assert cerrados == [(1, 0, 50, [], False, False)]


def test_cerrar_segmento_resetea_estado_para_la_proxima_visita_del_mismo_sid():
    t = _tracker(interaccion_frames_minimos=1, caja_frames_minimos=1)
    t.actualizar_zona(1, 10)
    t.actualizar_interaccion(1, True)
    t.actualizar_acercamiento_caja(1, True)

    t._cerrar_segmento(1, 0, 100)

    assert t.secuencia_zonas.get(1) is None
    assert t.tomo_producto.get(1) is None
    assert t.frames_interaccion.get(1) is None
    assert t.zona_actual.get(1) is None
    assert t.acerco_a_caja.get(1) is None
    assert t.frames_cerca_caja.get(1) is None

    # Reconexion del mismo sid (misma corrida, hueco largo) -> visita nueva
    # arranca de cero, sin arrastrar nada de la visita ya cerrada.
    t.actualizar_zona(1, 30)
    assert t.secuencia_zonas[1] == [30]
    assert t.tomo_producto.get(1) is not True
    assert t.acerco_a_caja.get(1) is not True


def test_cerrar_segmento_no_afecta_el_estado_de_otros_sids():
    t = _tracker(interaccion_frames_minimos=1, caja_frames_minimos=1)
    t.actualizar_zona(1, 10)
    t.actualizar_zona(2, 20)
    t.actualizar_interaccion(2, True)
    t.actualizar_acercamiento_caja(2, True)

    t._cerrar_segmento(1, 0, 10)

    assert t.secuencia_zonas.get(1) is None
    assert t.secuencia_zonas[2] == [20]
    assert t.tomo_producto[2] is True
    assert t.acerco_a_caja[2] is True


def test_cerrar_segmento_sin_callback_no_rompe():
    t = _tracker()  # on_visita_cerrada=None por default
    t.actualizar_zona(1, 10)
    t._cerrar_segmento(1, 0, 10)  # no debe lanzar excepcion
    assert t.secuencia_zonas.get(1) is None

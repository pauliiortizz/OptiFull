"""Tests de PersonTracker.procesar_frame() (deteccion/pipeline/tracking.py): como se le asigna una identidad
estable a cada persona entre frames -- reconexion por posicion, por apariencia, por Re-ID en la nube (con un
doble del proveedor) --, la confirmacion tardia, las visitas y el resumen final."""
import numpy as np
import pytest

from deteccion.pipeline import tracking as t

ROJO, AZUL = (0, 0, 220), (220, 0, 0)   # colores BGR de la ropa


class Tensor:
    def __init__(self, datos):
        self.datos = datos

    def int(self):
        return self

    def tolist(self):
        return list(self.datos)


class Resultado:
    """Doble minimo de un resultado de YOLO con tracking: results[0].boxes.id / .xyxy."""

    def __init__(self, detecciones):
        if detecciones is None:
            self.boxes = None
            return
        self.boxes = type("Boxes", (), {})()
        self.boxes.id = Tensor([d[0] for d in detecciones]) if detecciones else None
        self.boxes.xyxy = Tensor([d[1] for d in detecciones])


def frame_con(*personas):
    """Frame negro de 640x480 con un rectangulo de color por persona: (box, color)."""
    f = np.zeros((480, 640, 3), np.uint8)
    for (x1, y1, x2, y2), color in personas:
        f[int(y1):int(y2), int(x1):int(x2)] = color
    return f


class ReIDFalso:
    """Doble del proveedor de Re-ID en la nube (Gemini/Groq/Claude): no llama a ninguna API."""

    def __init__(self, activo=True, respuesta=None, descripcion=None):
        self.activo, self.respuesta, self.descripcion = activo, respuesta, descripcion
        self.clasificaciones, self.descripciones = [], 0

    def clasificar(self, crop, candidatos, momento=None):
        self.clasificaciones.append((crop.shape, candidatos, momento))
        return self.respuesta

    def generar_descripcion(self, crop):
        self.descripciones += 1
        return self.descripcion


class GroqReID(ReIDFalso):
    """Mismo doble con nombre de proveedor: el metodo de Re-ID se llama como la clase ('groq')."""


def tracker(reid=None, **cambios):
    eventos = {"nuevas": [], "descripciones": [], "visitas": []}

    def nueva(sid, frame, metodo, hint):
        eventos["nuevas"].append((sid, frame, metodo, hint))
        return 100 + sid

    def descripcion(sid, frame, metodo, desc, hint):
        eventos["descripciones"].append((sid, desc))
        return 100 + sid

    def visita(sid, f0, f1, secuencia, tomo, caja):
        eventos["visitas"].append((sid, f0, f1, secuencia, tomo, caja))

    opciones = dict(frame_skip=1, max_dist=80, quick_expiry_frames=5, long_expiry_frames=50, appearance_thresh=0.8,
                    max_app_samples=3, descripcion_streak_frames=2, min_frames_confirmacion=2,
                    gemini=reid or ReIDFalso(activo=False), on_nueva_persona=nueva, on_descripcion=descripcion,
                    on_visita_cerrada=visita, obtener_candidatos_dia=lambda excluir, frame: ([], None))
    opciones.update(cambios)
    tr = t.PersonTracker(**opciones)
    return tr, eventos


A = (100, 100, 160, 300)   # box de una persona
LEJOS = (500, 100, 560, 300)


def pasar(tr, frame_num, *detecciones, colores=None):
    colores = colores or [ROJO] * len(detecciones)
    f = frame_con(*[(box, c) for (_, box), c in zip(detecciones, colores)])
    return tr.procesar_frame(f, frame_num, [Resultado(list(detecciones))])


# ── Funciones de apariencia ───────────────────────────────────────────────────

def test_apariencia_de_un_recorte_muy_chico_es_none():
    assert t._compute_appearance(frame_con(), (0, 0, 5, 5)) is None


def test_misma_ropa_es_mas_parecida_que_ropa_distinta():
    f = frame_con(((0, 0, 60, 200), ROJO), ((100, 0, 160, 200), ROJO), ((200, 0, 260, 200), AZUL))
    a, b, c = (t._compute_appearance(f, box) for box in ((0, 0, 60, 200), (100, 0, 160, 200), (200, 0, 260, 200)))
    assert t._appearance_sim(a, b) == pytest.approx(1.0, abs=1e-3)
    assert t._appearance_sim(a, c) < 0.5


def test_distancia_entre_centros():
    assert t._centroid_dist((0, 0, 10, 10), (30, 40, 40, 50)) == pytest.approx(50.0)


# ── Identidad estable y confirmacion ──────────────────────────────────────────

def test_misma_deteccion_de_bytetrack_mantiene_el_id_y_devuelve_la_posicion_de_los_pies():
    tr, ev = tracker()
    d1 = pasar(tr, 1, (7, A))
    d2 = pasar(tr, 2, (7, (110, 100, 170, 300)))
    assert d1[0]["sid"] == d2[0]["sid"] == 1
    assert (d2[0]["cx"], d2[0]["cy"]) == (140, 300)   # centro horizontal, base del box
    assert tr.conteo_metodo_reid["nuevo"] == 1


def test_la_persona_se_crea_en_la_bd_recien_al_confirmar_frames_seguidos():
    tr, ev = tracker(min_frames_confirmacion=3)
    pasar(tr, 1, (7, A))
    pasar(tr, 2, (7, A))
    assert ev["nuevas"] == []
    pasar(tr, 3, (7, A))
    assert ev["nuevas"] == [(1, 1, "nuevo", None)] and tr.sid_to_persona_db_id[1] == 101


def test_una_deteccion_suelta_no_cuenta_como_persona():
    tr, ev = tracker()
    pasar(tr, 1, (7, A))           # un solo frame: ruido
    pasar(tr, 2)                   # frame sin detecciones
    assert tr.resumen_por_persona() == [] and ev["nuevas"] == []


def test_frame_sin_cajas_marca_como_perdidas_a_las_personas_activas():
    tr, _ = tracker()
    pasar(tr, 1, (7, A))
    tr.procesar_frame(frame_con(), 2, [Resultado(None)])
    assert 1 in tr.lost_tracks and tr.active_boxes == {}
    assert tr.registro_clientes[1]["estado"] == "perdido"


# ── Reconexion local ──────────────────────────────────────────────────────────

def test_reconexion_por_posicion_tras_un_hueco_corto():
    tr, ev = tracker()
    pasar(tr, 1, (7, A))
    pasar(tr, 2)                                    # se pierde (oclusion)
    d = pasar(tr, 4, (9, (105, 100, 165, 300)))     # bytetrack le da otro id, pero esta al lado
    assert d[0]["sid"] == 1 and tr.metodo_reid[1] == "posicion"   # el metodo queda el de la ultima reconexion
    assert tr.conteo_metodo_reid["posicion"] == 1
    assert ev["visitas"] == []                      # hueco corto: sigue la misma visita


def test_hueco_corto_pero_lejos_es_una_persona_nueva():
    tr, _ = tracker()
    pasar(tr, 1, (7, A))
    pasar(tr, 2)
    assert pasar(tr, 3, (9, LEJOS))[0]["sid"] == 2


def test_reconexion_por_apariencia_tras_un_hueco_largo_cierra_la_visita_anterior():
    tr, ev = tracker()
    for f in (1, 2):
        pasar(tr, f, (7, A))
    tr.actualizar_zona(1, 3)
    pasar(tr, 3)                                         # se pierde en el frame 3
    d = pasar(tr, 20, (9, LEJOS))                        # vuelve lejos, con la misma ropa
    assert d[0]["sid"] == 1 and tr.conteo_metodo_reid["apariencia"] == 1
    assert ev["visitas"] == [(1, 1, 3, [3], False, False)]   # la visita 1 termino donde se lo perdio
    assert tr.segment_start[1] == 20


def test_con_ropa_distinta_no_reconecta_por_apariencia():
    tr, _ = tracker()
    for f in (1, 2):
        pasar(tr, f, (7, A))
    pasar(tr, 3)
    assert pasar(tr, 20, (9, LEJOS), colores=[AZUL])[0]["sid"] == 2


def test_despues_del_hueco_maximo_ya_no_reconecta():
    tr, _ = tracker()
    for f in (1, 2):
        pasar(tr, f, (7, A))
    pasar(tr, 3)
    assert pasar(tr, 60, (9, A))[0]["sid"] == 2      # 57 frames perdido > long_expiry_frames (50)


# ── Re-ID en la nube (con doble del proveedor) ────────────────────────────────

CANDIDATO = {"persona_id": 55, "cliente_id": 40, "descripcion": {"ropa": "roja"}, "primera_deteccion": None}


def test_sin_candidatos_del_dia_no_llama_a_la_api():
    reid = ReIDFalso()
    tr, _ = tracker(reid)
    pasar(tr, 1, (7, A))
    assert reid.clasificaciones == []


def test_reid_en_la_nube_reconoce_un_cliente_de_otro_video():
    reid = GroqReID(respuesta=55)
    tr, ev = tracker(reid, obtener_candidatos_dia=lambda excluir, frame: ([CANDIDATO], "momento"),
                     min_frames_confirmacion=1)
    d = pasar(tr, 1, (7, A))
    assert d[0]["sid"] == 1 and tr.metodo_reid[1] == "groq"
    assert tr.sid_cliente_id_hint[1] == 40                    # mismo cliente que la persona 40
    assert ev["nuevas"] == [(1, 1, "groq", 40)]
    _, candidatos, momento = reid.clasificaciones[0]
    assert candidatos == [{"sid": 55, "descripcion": {"ropa": "roja"}, "primera_deteccion": None}]
    assert momento == "momento"


def test_reid_en_la_nube_reconoce_a_alguien_perdido_de_este_mismo_video():
    reid = ReIDFalso(respuesta=101)
    excluidos = []

    def candidatos(excluir, frame):
        excluidos.append(set(excluir))
        return [{**CANDIDATO, "persona_id": 101}], None

    tr, ev = tracker(reid, obtener_candidatos_dia=candidatos)
    for f in (1, 2):
        pasar(tr, f, (7, A))                                  # persona 1 confirmada -> persona_id 101
    pasar(tr, 3)
    d = pasar(tr, 20, (9, LEJOS), colores=[AZUL])             # otra ropa: la apariencia local no alcanza
    assert d[0]["sid"] == 1 and tr.metodo_reid[1] == "falso"  # proveedor = nombre de la clase sin "ReID"
    # 2 resoluciones por la nube: al aparecer (coincidio con el cliente 40 de otro video) y al reconectar
    assert tr.conteo_metodo_reid["falso"] == 2 and tr.sid_cliente_id_hint[1] == 40
    assert ev["visitas"][0][:3] == (1, 1, 3)
    assert excluidos[-1] == set()                             # nadie activo en ese momento


def test_reid_sin_coincidencia_da_una_persona_nueva():
    tr, _ = tracker(ReIDFalso(respuesta=None), obtener_candidatos_dia=lambda e, f: ([CANDIDATO], None))
    pasar(tr, 1, (7, A))
    assert tr.metodo_reid[1] == "nuevo" and tr.sid_cliente_id_hint == {}


def test_la_descripcion_visual_se_genera_una_sola_vez_al_llegar_a_la_racha():
    reid = ReIDFalso(descripcion={"ropa_superior": "roja"})
    tr, ev = tracker(reid)
    for f in range(1, 6):
        pasar(tr, f, (7, A))
    assert reid.descripciones == 1
    assert ev["descripciones"] == [(1, {"ropa_superior": "roja"})]
    assert tr.registro_clientes[1]["descripcion"] == {"ropa_superior": "roja"}


def test_si_la_api_no_describe_no_se_guarda_nada():
    reid = ReIDFalso(descripcion=None)
    tr, ev = tracker(reid)
    for f in (1, 2, 3):
        pasar(tr, f, (7, A))
    assert reid.descripciones == 1 and ev["descripciones"] == []


# ── Visitas, expiracion y resumen ─────────────────────────────────────────────

def test_expirar_perdidos_cierra_su_visita():
    tr, ev = tracker()
    for f in (1, 2):
        pasar(tr, f, (7, A))
    pasar(tr, 3)
    tr.expirar_perdidos(20)
    assert ev["visitas"] == []           # todavia dentro del plazo
    tr.expirar_perdidos(60)
    assert ev["visitas"] == [(1, 1, 3, [], False, False)] and tr.lost_tracks == {}


def test_al_terminar_el_video_se_cierran_las_visitas_abiertas():
    tr, ev = tracker()
    for f in (1, 2, 3):
        pasar(tr, f, (7, A), (8, LEJOS))
    tr.cerrar_visitas_abiertas(100)
    assert sorted(v[:3] for v in ev["visitas"]) == [(1, 1, 3), (2, 1, 3)]
    assert tr.segment_start == {}


def test_resumen_solo_incluye_personas_confirmadas_y_las_muestras_de_apariencia_rotan():
    tr, _ = tracker(max_app_samples=2)
    for f in range(1, 6):
        pasar(tr, f, (7, A))
    pasar(tr, 6, (8, LEJOS))                 # aparece un solo frame: no confirmada
    resumen = tr.resumen_por_persona()
    assert [r["sid"] for r in resumen] == [1]
    assert (resumen[0]["first_frame"], resumen[0]["last_frame"]) == (1, 5)
    assert len(tr.app_samples[1]) == 2
    assert tr.max_personas == 1

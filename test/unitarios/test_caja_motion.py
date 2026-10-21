"""MotionAgent (deteccion_productos): decide CUANDO llamar al LLM (escena quieta + distinta a la ultima analizada).

Frames sinteticos de numpy y timestamps controlados: no hace falta camara ni video.
"""
import numpy as np
import pytest

from agents.motion_agent import MotionAgent
from config import ESTABLE_MS

FPS = 15


def plano(valor, alto=60, ancho=80):
    return np.full((alto, ancho, 3), valor, dtype=np.uint8)


def con_cuadro(valor_fondo, valor_cuadro, x1=40, y1=0, x2=80, y2=60):
    f = plano(valor_fondo)
    f[y1:y2, x1:x2] = valor_cuadro
    return f


def alimentar(motion, frames, t0=0.0, fps=FPS):
    """Pasa los frames con timestamps a 'fps' y devuelve en que indices se pidio analizar."""
    disparos = []
    for i, f in enumerate(frames):
        if motion.deberia_analizar(f, t0 + i / fps):
            disparos.append(i)
            motion.marcar_analizado(f)
    return disparos


def frames_para(ms, fps=FPS):
    return int(np.ceil(ms / 1000 * fps)) + 1


def test_escena_quieta_dispara_una_sola_vez():
    disparos = alimentar(MotionAgent(), [plano(100)] * 30)
    assert len(disparos) == 1


def test_no_dispara_antes_de_cubrir_la_ventana_de_estabilidad():
    disparos = alimentar(MotionAgent(), [plano(100)] * 30)
    # recien cuando hay ESTABLE_MS de historia: con 15 fps son 3 frames (0, 1/15, 2/15, 3/15 s)
    assert disparos[0] == frames_para(ESTABLE_MS) - 1


def test_un_solo_frame_nunca_es_estable():
    assert MotionAgent().deberia_analizar(plano(100), 0.0) is False


def test_escena_en_movimiento_no_dispara():
    # alterna claro/oscuro en cada frame: la velocidad de cambio es enorme
    frames = [plano(0 if i % 2 else 200) for i in range(40)]
    assert alimentar(MotionAgent(), frames) == []


def test_un_tramo_con_movimiento_impide_disparar_aunque_el_promedio_sea_bajo():
    # salto de 6 en un frame (1/15 s) = 90/s: el promedio de la ventana (30/s) pasaria el umbral de 40/s,
    # pero se exige que NINGUN tramo lo supere -> recien dispara cuando el salto sale de la ventana
    frames = [plano(100)] * 3 + [plano(106)] * 10
    disparos = alimentar(MotionAgent(), frames)
    assert len(disparos) == 1 and disparos[0] > 3


def test_producto_nuevo_dispara_de_nuevo_y_el_mismo_no():
    a, b = plano(40), plano(200)
    frames = [a] * 20 + [b] * 20 + [b] * 20
    disparos = alimentar(MotionAgent(), frames)
    assert len(disparos) == 2
    assert 20 <= disparos[1] < 40


def test_volver_a_la_misma_escena_tras_moverse_no_vuelve_a_disparar():
    a = plano(100)
    frames = [a] * 20 + [plano(0 if i % 2 else 255) for i in range(10)] + [a] * 20
    assert len(alimentar(MotionAgent(), frames)) == 1


def test_cambio_chico_de_escena_no_cuenta_como_producto_nuevo():
    # menos de UMBRAL_ESCENA_NUEVA de diferencia media (el mismo producto que rota un poco)
    frames = [plano(100)] * 20 + [plano(110)] * 20
    assert len(alimentar(MotionAgent(), frames)) == 1


def test_es_independiente_del_fps():
    for fps in (5, 15, 30):
        assert len(alimentar(MotionAgent(), [plano(100)] * 40, fps=fps)) == 1, fps


def test_pausa_mas_corta_que_la_ventana_no_dispara():
    a, b = plano(40), plano(200)
    mov = [plano(0 if i % 2 else 255) for i in range(6)]
    # 'b' quieto solo 1 frame (66 ms < ESTABLE_MS) entre movimientos
    frames = [a] * 20 + mov + [b] + mov
    assert len(alimentar(MotionAgent(), frames)) == 1


def test_frames_con_timestamp_repetido_no_rompen_la_velocidad():
    motion = MotionAgent()
    for ts in (0.0, 0.1, 0.1):                     # dos frames con el mismo ts (dt = 0): se ignoran
        motion.deberia_analizar(plano(100), ts)
    assert motion.deberia_analizar(plano(100), 0.2) is True


def test_ventana_descarta_frames_viejos():
    motion = MotionAgent()
    alimentar(motion, [plano(100)] * 100)
    ventana = ESTABLE_MS / 1000
    assert motion.frames_recientes[-1][1] - motion.frames_recientes[1][1] < ventana
    assert len(motion.frames_recientes) <= frames_para(ESTABLE_MS) + 1


def test_sin_timestamp_usa_el_reloj(monkeypatch):
    import agents.motion_agent as m
    reloj = iter([10.0, 10.1, 10.2, 10.3])
    monkeypatch.setattr(m.time, "time", lambda: next(reloj))
    motion = MotionAgent()
    resultados = [motion.deberia_analizar(plano(100)) for _ in range(4)]
    assert resultados == [False, False, True, True]


def test_roi_ignora_el_movimiento_fuera_de_la_region():
    # en la mitad izquierda hay movimiento continuo; la ROI mira solo la derecha, que esta quieta
    frames = [con_cuadro(0 if i % 2 else 255, 120) for i in range(30)]
    assert alimentar(MotionAgent(), frames) == []
    assert len(alimentar(MotionAgent(roi=(40, 0, 80, 60)), frames)) == 1


def test_roi_detecta_producto_nuevo_solo_dentro_de_la_region():
    roi = (40, 0, 80, 60)
    frames = [con_cuadro(10, 50)] * 20 + [con_cuadro(10, 220)] * 20
    assert len(alimentar(MotionAgent(roi=roi), frames)) == 2


def test_marcar_analizado_guarda_la_referencia_en_gris_recortada():
    motion = MotionAgent(roi=(40, 0, 80, 60))
    motion.marcar_analizado(con_cuadro(0, 200))
    assert motion.gris_ultimo_analizado.shape == (60, 40)
    assert motion.gris_ultimo_analizado.mean() == pytest.approx(200, abs=1)

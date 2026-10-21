"""CaptureAgent (deteccion_productos): frames de un archivo de video o de una camara en vivo.

El modo archivo se prueba con un video chico generado en el momento. El modo en vivo, con una camara falsa
(reemplaza cv2.VideoCapture) para controlar cuando entrega frames, cuando se corta y si reconecta.
"""
import threading
import time

import cv2
import numpy as np
import pytest

import agents.capture_agent as ca
from agents.capture_agent import CaptureAgent, _es_en_vivo, _sin_credenciales


@pytest.fixture
def video(tmp_path):
    """Video MJPG de 30 frames a 30 fps; el frame i tiene todos sus pixeles en 8*i."""
    ruta = tmp_path / "caja.avi"
    w = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"MJPG"), 30, (64, 48))
    for i in range(30):
        w.write(np.full((48, 64, 3), 8 * i, dtype=np.uint8))
    w.release()
    return str(ruta)


@pytest.mark.parametrize("source, esperado", [
    (0, True),
    ("1", True),
    ("http://192.168.0.10:8080/video", True),
    ("rtsp://user:clave@cam/stream", True),
    ("data/videos/prueba1.mp4", False),
])
def test_es_en_vivo(source, esperado):
    assert _es_en_vivo(source) is esperado


def test_un_archivo_existente_no_es_en_vivo(tmp_path):
    archivo = tmp_path / "v.mp4"
    archivo.write_bytes(b"")
    assert _es_en_vivo(str(archivo)) is False


@pytest.mark.parametrize("source, esperado", [
    ("http://admin:secreta@192.168.0.10:8080/video", "http://192.168.0.10:8080/video"),
    ("rtsp://cam/stream", "rtsp://cam/stream"),
    (0, "0"),
])
def test_sin_credenciales(source, esperado):
    assert _sin_credenciales(source) == esperado


# ── Archivo de video ─────────────────────────────────────────────────────────

def test_archivo_procesa_uno_de_cada_n_frames_con_tiempo_de_video(video):
    cap = CaptureAgent(video, target_fps=10)
    frames = list(cap.frames())
    cap.release()
    assert cap.en_vivo is False and cap.frame_skip == 3
    assert [round(ts, 3) for _, ts in frames] == [round(i / 30, 3) for i in range(0, 30, 3)]
    # el contenido corresponde al frame indicado (MJPG tiene perdida: tolerancia)
    assert [int(round(f.mean() / 8)) for f, _ in frames] == list(range(0, 30, 3))


def test_archivo_con_target_mayor_a_la_fuente_no_saltea(video):
    cap = CaptureAgent(video, target_fps=60)
    assert len(list(cap.frames())) == 30 and cap.frame_skip == 1
    cap.release()


def test_archivo_inexistente_falla_sin_reintentar(tmp_path, monkeypatch):
    esperas = []
    monkeypatch.setattr(ca.time, "sleep", esperas.append)
    cap = CaptureAgent(str(tmp_path / "no_existe.mp4"))
    with pytest.raises(RuntimeError, match="No se pudo abrir la fuente"):
        list(cap.frames())
    assert esperas == []


def test_release_sin_haber_arrancado():
    CaptureAgent("no_existe.mp4").release()


# ── Camara en vivo (falsa) ───────────────────────────────────────────────────

class CamaraFalsa:
    """Imita cv2.VideoCapture. 'guion' es la lista de lecturas: un int = frame con ese valor, None = corte."""
    aperturas = []

    def __init__(self, abre=True, guion=(), fps=30.0):
        self.abre, self.guion, self.fps = abre, list(guion), fps
        self.liberada = False

    def isOpened(self):
        return self.abre

    def get(self, prop):
        return {cv2.CAP_PROP_FPS: self.fps, cv2.CAP_PROP_FRAME_WIDTH: 64, cv2.CAP_PROP_FRAME_HEIGHT: 48}.get(prop, 0)

    def read(self):
        time.sleep(0.002)
        if not self.guion:
            return False, None
        v = self.guion.pop(0)
        if v is None:
            return False, None
        return True, np.full((48, 64, 3), v, dtype=np.uint8)

    def release(self):
        self.liberada = True


@pytest.fixture
def camaras(monkeypatch):
    """Cada apertura de cv2.VideoCapture devuelve la siguiente CamaraFalsa de la lista."""
    cola, abiertas, args = [], [], []

    def abrir(*a, **k):
        args.append(a)
        cam = cola.pop(0) if cola else CamaraFalsa(abre=False)
        abiertas.append(cam)
        return cam
    monkeypatch.setattr(ca.cv2, "VideoCapture", abrir)
    monkeypatch.setattr(ca, "ESPERA_ENTRE_INTENTOS_SEG", 0.0)
    return cola, abiertas, args


def test_en_vivo_entrega_el_ultimo_frame_y_nunca_repite(camaras):
    cola, _, _ = camaras
    cola.append(CamaraFalsa(guion=list(range(1, 200))))
    cap = CaptureAgent("http://cel:8080/video", target_fps=50)
    vistos = []
    for f, ts in cap.frames():
        vistos.append((int(f[0, 0, 0]), ts))
        if len(vistos) == 5:
            break
    cap.release()
    valores = [v for v, _ in vistos]
    assert valores == sorted(set(valores))        # siempre un frame mas nuevo, nunca el mismo dos veces
    assert all(b > a for (_, a), (_, b) in zip(vistos, vistos[1:]))


def test_en_vivo_descarta_lo_viejo_mientras_el_programa_esta_ocupado(camaras):
    cola, _, _ = camaras
    cola.append(CamaraFalsa(guion=list(range(1, 250))))
    cap = CaptureAgent(0, target_fps=100)
    gen = cap.frames()
    primero = int(next(gen)[0][0, 0, 0])
    time.sleep(0.15)                               # "esperando al LLM": la camara sigue leyendo
    segundo = int(next(gen)[0][0, 0, 0])
    cap.release()
    assert segundo - primero > 10


def test_en_vivo_respeta_target_fps(camaras):
    cola, _, _ = camaras
    cola.append(CamaraFalsa(guion=list(range(1, 1000))))
    cap = CaptureAgent(0, target_fps=20)
    ts = []
    for _, t in cap.frames():
        ts.append(t)
        if len(ts) == 4:
            break
    cap.release()
    assert min(b - a for a, b in zip(ts, ts[1:])) >= 0.045


def test_en_vivo_reintenta_la_conexion_al_arrancar(camaras, capsys):
    cola, abiertas, _ = camaras
    cola.extend([CamaraFalsa(abre=False), CamaraFalsa(abre=False), CamaraFalsa(guion=[7] * 50)])
    cap = CaptureAgent("rtsp://u:p@cam/s")
    frame, _ = next(cap.frames())
    cap.release()
    assert int(frame[0, 0, 0]) == 7
    assert len(abiertas) == 3 and abiertas[0].liberada and abiertas[1].liberada
    salida = capsys.readouterr().out
    assert "intento 1/4" in salida and "Conectado" in salida
    assert "u:p@" not in salida                    # nunca se imprime la clave de la camara


def test_en_vivo_se_rinde_tras_los_intentos(camaras):
    _, abiertas, _ = camaras
    cap = CaptureAgent("http://cel/video")
    with pytest.raises(RuntimeError, match="http://cel/video"):
        cap.start()
    assert len(abiertas) == ca.INTENTOS_CONEXION


def test_en_vivo_reconecta_si_se_corta(camaras, capsys):
    cola, abiertas, _ = camaras
    cola.extend([CamaraFalsa(guion=[1, None]), CamaraFalsa(guion=[2] * 100)])
    cap = CaptureAgent(0, target_fps=100)
    valores = set()
    for f, _ in cap.frames():
        valores.add(int(f[0, 0, 0]))
        if 2 in valores:
            break
    cap.release()
    assert "Se cortó la cámara, reconectando" in capsys.readouterr().out
    assert len(abiertas) == 2


def test_en_vivo_termina_si_no_puede_reconectar(camaras, capsys, monkeypatch):
    cola, _, _ = camaras
    # como en la realidad, los reintentos tardan: el aviso de "camara perdida" llega con frames() ya esperando
    monkeypatch.setattr(ca, "ESPERA_ENTRE_INTENTOS_SEG", 0.05)
    cola.append(CamaraFalsa(guion=[1, 1, None]))   # despues del corte ninguna apertura funciona
    cap = CaptureAgent(0, target_fps=100)
    resultado = []

    def consumir():
        resultado.extend(cap.frames())
    hilo = threading.Thread(target=consumir)
    hilo.start()
    hilo.join(timeout=5)
    cap.release()
    assert not hilo.is_alive()                      # frames() termino solo
    assert "No se pudo reconectar" in capsys.readouterr().out


def test_en_vivo_url_usa_ffmpeg_con_timeouts(camaras):
    cola, _, args = camaras
    cola.append(CamaraFalsa(guion=[1] * 10))
    cap = CaptureAgent("http://cel/video")
    cap.start()
    cap.release()
    assert args[0][1] == cv2.CAP_FFMPEG
    assert cv2.CAP_PROP_OPEN_TIMEOUT_MSEC in args[0][2]


def test_en_vivo_si_opencv_no_acepta_los_parametros_abre_sin_ellos(camaras, monkeypatch):
    cola, _, _ = camaras
    cola.append(CamaraFalsa(guion=[1] * 10))
    abrir = ca.cv2.VideoCapture
    llamadas = []

    def sin_parametros(*a):
        llamadas.append(a)
        if len(a) > 1:
            raise TypeError("parametros no soportados")
        return abrir(*a)
    monkeypatch.setattr(ca.cv2, "VideoCapture", sin_parametros)
    cap = CaptureAgent("http://cel/video")
    cap.start()
    cap.release()
    assert llamadas[-1] == ("http://cel/video",)


def test_webcam_por_indice_no_usa_parametros_de_red(camaras):
    cola, _, args = camaras
    cola.append(CamaraFalsa(guion=[1] * 10, fps=0))
    cap = CaptureAgent("0")
    cap.start()
    cap.release()
    assert cap.source == 0 and args[0] == (0,)
    assert cap.source_fps == 25.0                  # la camara no informa fps: se asume 25


def test_release_libera_la_camara_despues_de_frenar_el_hilo(camaras):
    cola, abiertas, _ = camaras
    cola.append(CamaraFalsa(guion=list(range(1, 10_000))))
    cap = CaptureAgent(0)
    cap.start()
    cap.release()
    assert not cap._thread.is_alive() and abiertas[-1].liberada

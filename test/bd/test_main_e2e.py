"""Prueba de punta a punta de deteccion/main.py: un video sintetico, un YOLO simulado (no hace falta el modelo
ni la GPU) y el Postgres real de prueba. Recorre el pipeline completo -- lectura del video, tracking, zonas,
interaccion con productos, acercamiento a la caja, evento de compra, trayectorias, heatmaps, cierre de sesion,
auditoria y fusiones -- y verifica lo que queda guardado en la base.

Escenario: una persona aparece en la gondola, toma un producto y camina hasta la caja -> COMPRA_NORMAL."""
import sys
import types
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest

from conftest import CAJA, GONDOLA, URL

sys.modules.setdefault("ultralytics", types.SimpleNamespace(YOLO=None))   # en CI no se instala torch/YOLO
from deteccion import config  # noqa: E402
from deteccion import main as m  # noqa: E402

FPS, FRAMES, W, H = 10, 60, 640, 360
INICIO = datetime(2026, 10, 7, 10, 0, 0)
EN_GONDOLA = (450, 130, 490, 250)   # box de la persona (640x360): pies dentro de la gondola
EN_CAJA = (60, 10, 100, 120)        # pies dentro de la caja
PRODUCTO = (480, 180, 500, 200)     # una botella en la mano (centro dentro del box + margen)


class Tensor:
    def __init__(self, datos):
        self.datos = datos

    def int(self):
        return self

    def tolist(self):
        return [list(d) if isinstance(d, tuple) else d for d in self.datos]


def resultado(ids, boxes):
    r = types.SimpleNamespace(boxes=types.SimpleNamespace(id=Tensor(ids) if ids else None, xyxy=Tensor(boxes)))
    return [r]


class YOLOFalso:
    """Doble de ultralytics.YOLO: .track() 've' a la persona del guion; llamarlo directo detecta productos."""
    procesados = 0

    def __init__(self, pesos):
        self.pesos = pesos

    def track(self, frame, **kwargs):
        assert kwargs["persist"] is True and kwargs["classes"] == [0]
        k = YOLOFalso.procesados
        YOLOFalso.procesados += 1
        if k >= 28:                       # al final sale de cuadro
            return resultado([], [])
        return resultado([1], [EN_GONDOLA if k < 10 else EN_CAJA])

    def __call__(self, frame, **kwargs):
        en_gondola = YOLOFalso.procesados <= 10
        return resultado([9], [PRODUCTO]) if en_gondola else resultado([], [])


def crear_video(ruta):
    w = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for i in range(FRAMES):
        f = np.full((H, W, 3), 40, np.uint8)
        x1, y1, x2, y2 = EN_GONDOLA if i < 20 else EN_CAJA
        f[y1:y2, x1:x2] = (0, 0, 200)
        w.write(f)
    w.release()


@pytest.fixture
def pipeline(monkeypatch, tmp_path, datos):
    """Configura main.py contra el video sintetico y la base de prueba (sin Re-ID en la nube ni Storage)."""
    datos.camara(2, "Salon")
    datos.zona(2, "gondola", GONDOLA, nombre="Gondola")
    datos.zona(2, "caja", CAJA, nombre="Caja")
    video = tmp_path / "D02_20261007100000.mp4"
    crear_video(video)
    YOLOFalso.procesados = 0
    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)   # cada corrida de main() es un proceso
    monkeypatch.chdir(tmp_path)                                    # heatmaps_pendientes/ queda en tmp
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.setattr(m, "YOLO", YOLOFalso)
    monkeypatch.setattr(m, "tqdm", None)
    for nombre, valor in {
        "VIDEO_PATH": str(video), "DATABASE_URL": URL, "HAS_DB": True, "SHOW_PREVIEW": False, "FRAME_SKIP": 2,
        "CAMARA_ID_OVERRIDE": None, "SOLO_LEER_ZONAS": False, "HAS_SUPABASE_STORAGE": False,
        "USAR_GEMINI_REID": False, "USAR_GROQ_REID": False, "USAR_CLAUDE_REID": False,
        "TRAYECTORIA_INTERVALO_SEG": 0.5, "MIN_FRAMES_CONFIRMACION": 3, "CAJA_PERMANENCIA_MINIMA_SEG": 1.0,
        "TRAYECTORIAS_FLUSH_CADA_N_FRAMES": 5,
    }.items():
        monkeypatch.setattr(config, nombre, valor)
    return video


def test_video_completo_queda_guardado_en_la_base(pipeline, datos, tmp_path, capsys):
    m.main()
    salida = capsys.readouterr().out

    sesion_id, fin, frame_w = datos.filas("SELECT id, fin, frame_w FROM sesiones_video")[0]
    assert (fin, frame_w) == (INICIO + timedelta(seconds=FRAMES / FPS), W)
    assert datos.valor("SELECT count(*) FROM personas") == 1                  # una sola persona, id estable
    assert datos.valor("SELECT count(*) FROM trayectorias") >= 4
    assert datos.valor("SELECT count(*) FROM trayectorias WHERE camara_id = 2") >= 4
    assert datos.valor("SELECT count(*) FROM visitas") == 1
    accion, tomo, caja, secuencia = datos.filas(
        "SELECT accion_detectada, tomo_producto, paso_por_caja, secuencia_zonas FROM eventos")[0]
    assert (accion, tomo, caja) == ("COMPRA_NORMAL", True, True)
    assert secuencia == ["Gondola", "Caja"]
    assert datos.valor("SELECT count(*) FROM alertas") == 0
    assert datos.valor("SELECT count(*) FROM mapas_calor WHERE sesion_id = %s", (sesion_id,)) == 1
    assert datos.valor("SELECT sesiones_combinadas FROM mapas_calor_camara WHERE camara_id = 2") == 1
    assert sorted(p.name for p in (tmp_path / "heatmaps_pendientes").iterdir()) == [
        "camara_2_20261007_100000.png", "camara_2_combinado.png"]              # sin Storage: respaldo local
    assert "Personas unicas detectadas  : 1" in salida
    assert "[Evento] Persona 1: COMPRA_NORMAL" in salida


def test_el_mismo_video_no_se_procesa_dos_veces(pipeline, datos, capsys):
    m.main()
    YOLOFalso.procesados = 0
    m.main()
    assert "Ya existe un video analizado con el mismo nombre de archivo" in capsys.readouterr().out
    assert datos.valor("SELECT count(*) FROM sesiones_video") == 1
    assert datos.valor("SELECT count(*) FROM personas") == 1


def test_sin_base_de_datos_el_analisis_igual_termina(pipeline, monkeypatch, datos, capsys):
    monkeypatch.setattr(config, "HAS_DB", False)
    m.main()
    salida = capsys.readouterr().out
    assert "Sin zonas definidas" in salida and "Personas unicas detectadas  : 1" in salida
    assert datos.valor("SELECT count(*) FROM sesiones_video") == 0


def test_solo_leer_zonas_no_escribe_nada(pipeline, monkeypatch, datos, capsys):
    monkeypatch.setattr(config, "SOLO_LEER_ZONAS", True)
    m.main()
    salida = capsys.readouterr().out
    assert "SOLO_LEER_ZONAS activo" in salida
    assert "[Evento] Persona 1: COMPRA_NORMAL" in salida      # la clasificacion se ve igual por consola
    assert datos.valor("SELECT count(*) FROM sesiones_video") == 0


def test_si_el_analisis_falla_la_sesion_queda_cerrada_con_lo_ya_guardado(pipeline, monkeypatch, datos):
    original = YOLOFalso.track

    def falla_a_mitad(self, frame, **kwargs):
        if YOLOFalso.procesados == 15:
            raise RuntimeError("se corto la GPU")
        return original(self, frame, **kwargs)

    monkeypatch.setattr(YOLOFalso, "track", falla_a_mitad)
    with pytest.raises(RuntimeError, match="se corto la GPU"):
        m.main()
    assert datos.valor("SELECT fin IS NOT NULL FROM sesiones_video") is True
    assert datos.valor("SELECT count(*) FROM personas") == 1                # lo ya guardado se conserva


def test_nombre_de_video_sin_camara_corre_sin_persistir(pipeline, monkeypatch, tmp_path, datos, capsys):
    otro = tmp_path / "grabacion_sin_prefijo.mp4"
    crear_video(otro)
    monkeypatch.setattr(config, "VIDEO_PATH", str(otro))
    m.main()
    assert "[AVISO] No se pudo determinar la camara" in capsys.readouterr().out
    assert datos.valor("SELECT count(*) FROM sesiones_video") == 0


# ── Funciones auxiliares de main.py ───────────────────────────────────────────

def test_fps_real_de_procesamiento():
    from collections import deque
    assert m._fps_actual(deque([1.0])) == 0.0
    assert m._fps_actual(deque([0.0, 0.5, 1.0])) == pytest.approx(2.0)


def test_heatmap_sin_storage_se_guarda_local_y_con_storage_se_reintenta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    sin_storage = types.SimpleNamespace(enabled=False, subir_png=lambda p, c: None)
    assert m._subir_o_guardar_local(sin_storage, "camara_2/a.png", b"png") == "heatmaps_pendientes/camara_2_a.png"
    intentos = iter([None, "https://storage/a.png"])
    con_storage = types.SimpleNamespace(enabled=True, subir_png=lambda p, c: next(intentos))
    assert m._subir_o_guardar_local(con_storage, "camara_2/a.png", b"png") == "https://storage/a.png"


@pytest.mark.parametrize("args, error", [
    (["--webcam", "--screen"], True),     # regresion DEF-011: sin valor tambien son dos modos a la vez
    (["--webcam", "1", "--rtsp", "2"], True),
    (["--rtsp", "2"], False),
    ([], False),
])
def test_argumentos_de_linea_de_comandos(monkeypatch, args, error):
    monkeypatch.setattr(sys, "argv", ["main.py", *args])
    if error:
        with pytest.raises(SystemExit):
            m._parse_args()
    else:
        assert m._parse_args().rtsp == (2 if args else None)


# ── Modos en vivo: RTSP (persiste), webcam y pantalla (no persisten) ──────────

class FuenteEnVivo:
    """Doble de WebcamVideoSource/ScreenVideoSource: entrega frames del guion y despues corta."""
    is_live, total_frames, fps, frame_w, frame_h = True, None, 10.0, W, H

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.pendientes = [np.full((H, W, 3), 40, np.uint8) for _ in range(30)]
        self.pendientes.insert(3, None)            # un momento sin frame nuevo (stream en pausa)
        self.liberada = False

    def open(self):
        pass

    def read(self):
        if not self.pendientes:
            return False, None
        frame = self.pendientes.pop(0)
        return True, frame

    def error(self):
        return None

    def release(self):
        self.liberada = True


@pytest.fixture
def en_vivo(pipeline, monkeypatch):
    import signal

    from deteccion import utils
    manejador = signal.getsignal(signal.SIGINT)
    monkeypatch.setattr(m, "WebcamVideoSource", FuenteEnVivo)
    monkeypatch.setattr(m, "ScreenVideoSource", FuenteEnVivo)
    for nombre, valor in {"RTSP_URLS": {2: "rtsp://usuario:clave@camara/1"}, "RTSP_TARGET_FPS": 1000.0,
                          "RTSP_FLUSH_CADA_SEG": 0, "RTSP_HEATMAP_CADA_SEG": 0, "RTSP_FUSION_CADA_SEG": 1e-9,
                          "RTSP_MOSTRAR_PREVIEW": False, "EVIDENCIA_ACTIVA": True, "FOTOS_ACTIVAS": False,
                          "RTSP_USAR_REID_NUBE": False,
                          "CAJA_PERMANENCIA_MINIMA_SEG": 0.005}.items():   # 5 frames a 1000 fps simulados
        monkeypatch.setattr(config, nombre, valor)
    yield
    signal.signal(signal.SIGINT, manejador)    # main() instala su propio manejador de Ctrl+C en modo RTSP
    utils.set_reloj_vivo(None)                 # y el reloj de frames en vivo


def test_rtsp_en_vivo_guarda_incrementalmente_y_no_expone_la_url(en_vivo, monkeypatch, datos, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "--rtsp", "2"])
    m.main()
    salida = capsys.readouterr().out
    archivo = datos.valor("SELECT archivo_path FROM sesiones_video")
    assert archivo.startswith("rtsp://camara_2/") and "clave" not in archivo   # nunca se guarda la URL real
    assert datos.valor("SELECT heartbeat IS NOT NULL AND fin IS NOT NULL FROM sesiones_video") is True
    assert datos.valor("SELECT count(*) FROM personas") == 1
    assert datos.valor("SELECT accion_detectada FROM eventos") == "COMPRA_NORMAL"
    assert datos.valor("SELECT count(*) FROM mapas_calor") == 1                # upsert: no se duplica
    assert "Modo RTSP en vivo -- camara 2" in salida


def test_rtsp_sin_url_configurada_no_arranca(en_vivo, monkeypatch, datos, capsys):
    monkeypatch.setattr(config, "RTSP_URLS", {2: None})
    monkeypatch.setattr(sys, "argv", ["main.py", "--rtsp", "2"])
    m.main()
    assert "Falta RTSP_URL_2 en .env" in capsys.readouterr().out
    assert datos.valor("SELECT count(*) FROM sesiones_video") == 0


def test_rtsp_ctrl_c_cierra_y_guarda(en_vivo, monkeypatch, datos, capsys):
    import signal
    original = FuenteEnVivo.read

    def corte_a_mitad(self):
        if len(self.pendientes) == 10:
            signal.getsignal(signal.SIGINT)(signal.SIGINT, None)   # el usuario aprieta Ctrl+C
        return original(self)

    monkeypatch.setattr(FuenteEnVivo, "read", corte_a_mitad)
    monkeypatch.setattr(sys, "argv", ["main.py", "--rtsp", "2"])
    m.main()
    assert "Corte pedido (Ctrl+C)" in capsys.readouterr().out
    assert datos.valor("SELECT fin IS NOT NULL FROM sesiones_video") is True


def test_rtsp_si_la_camara_se_cae_termina_y_guarda(en_vivo, monkeypatch, datos, capsys):
    monkeypatch.setattr(FuenteEnVivo, "error", lambda self: "la camara no volvio" if len(self.pendientes) < 5 else None)
    monkeypatch.setattr(sys, "argv", ["main.py", "--rtsp", "2"])
    m.main()
    assert "[ERROR] la camara no volvio" in capsys.readouterr().out
    assert datos.valor("SELECT fin IS NOT NULL FROM sesiones_video") is True


@pytest.fixture
def ventana(monkeypatch):
    """La vista previa (cv2.imshow) no se puede abrir en el pipeline: se reemplaza y se guardan las teclas."""
    mostrado = []
    teclas = []
    monkeypatch.setattr(m.cv2, "imshow", lambda nombre, img: mostrado.append(img.shape))
    monkeypatch.setattr(m.cv2, "waitKey", lambda ms: teclas.pop(0) if teclas else -1)
    monkeypatch.setattr(m.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(config, "PREVIEW_CADA_N", 1)
    return mostrado, teclas


def test_webcam_muestra_la_vista_previa_y_no_persiste_nada(en_vivo, ventana, monkeypatch, datos, capsys):
    mostrado, teclas = ventana
    teclas += [-1, ord("p"), -1, ord("p")]                    # pausa y reanuda
    monkeypatch.setattr(config, "WEBCAM_CAMARA_ID_ZONAS", 2)   # solo LEE las zonas para dibujarlas
    monkeypatch.setattr(sys, "argv", ["main.py", "--webcam"])
    m.main()
    salida = capsys.readouterr().out
    assert "2 zonas cargadas para camara 2" in salida and "Pausado" in salida and "Reanudado" in salida
    assert "no se persistio nada" in salida
    assert mostrado and mostrado[0][2] == 3
    assert datos.valor("SELECT count(*) FROM sesiones_video") == 0
    assert not (m.Path.cwd() / "heatmaps_pendientes").exists()


def test_q_en_la_vista_previa_detiene_el_analisis(en_vivo, ventana, monkeypatch, capsys):
    mostrado, teclas = ventana
    teclas += [-1, -1, ord("q")]
    monkeypatch.setattr(sys, "argv", ["main.py", "--webcam", "0"])
    m.main()
    assert len(mostrado) == 3


def test_pantalla_sin_vista_previa_y_sin_persistir(en_vivo, monkeypatch, datos, capsys):
    monkeypatch.setattr(config, "SCREEN_MOSTRAR_PREVIEW", False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--screen", "2"])
    m.main()
    salida = capsys.readouterr().out
    assert "Modo pantalla en vivo (monitor=2)" in salida
    assert datos.valor("SELECT count(*) FROM sesiones_video") == 0


def test_video_con_vista_previa(pipeline, ventana, monkeypatch, datos):
    mostrado, _ = ventana
    monkeypatch.setattr(config, "SHOW_PREVIEW", True)
    m.main()
    assert len(mostrado) > 10


# ── Regresion DEF-012: opciones de ffmpeg para RTSP aplicadas a videos grabados ─────────────
# main.py seteaba OPENCV_FFMPEG_CAPTURE_OPTIONS (con 'fflags;nobuffer') al importarse, para TODO el
# proceso: al analizar un video grabado se perdia el primer frame. Solo tiene que aplicarse en modo RTSP.

def test_un_video_grabado_se_lee_entero_sin_las_opciones_de_rtsp(pipeline, monkeypatch):
    m.main()
    assert "nobuffer" not in m.os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS", "")
    assert YOLOFalso.procesados == FRAMES // 2          # 60 frames con FRAME_SKIP=2: ninguno perdido


def test_en_rtsp_se_aplican_las_opciones_de_baja_latencia(en_vivo, monkeypatch):
    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--rtsp", "2"])
    m.main()
    assert m.os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay"


# ── Ramas restantes (red de seguridad antes de partir main() en funciones) ────

@pytest.mark.parametrize("proveedor", ["groq", "gemini", "claude"])
def test_cada_proveedor_de_reid_se_configura(pipeline, monkeypatch, capsys, proveedor):
    monkeypatch.setattr(config, "REID_PROVIDER", proveedor)
    m.main()
    assert f"[ReID] Proveedor configurado: {proveedor}  (activo=False)" in capsys.readouterr().out


class ReIDActivo:
    """Doble de un proveedor de Re-ID en la nube activo (no llama a ninguna API)."""
    creados = []

    def __init__(self, **kwargs):
        self.kwargs, self.activo = kwargs, True
        ReIDActivo.creados.append(self)

    def generar_descripcion(self, crop):
        return {"color_ropa_superior": "rojo", "color_ropa_inferior": "azul", "complexion": "media",
                "cabello": "corto", "accesorios": "ninguno"}

    def clasificar(self, crop, candidatos, momento=None):
        return None


def test_con_reid_activo_la_descripcion_se_guarda_durante_el_analisis(pipeline, monkeypatch, datos):
    ReIDActivo.creados = []
    monkeypatch.setattr(m, "ClaudeReID", ReIDActivo)
    monkeypatch.setattr(config, "REID_PROVIDER", "claude")
    monkeypatch.setattr(config, "DESCRIPCION_STREAK_FRAMES", 3)
    m.main()
    assert ReIDActivo.creados[0].kwargs["usar_claude_reid"] is False   # USAR_CLAUDE_REID del fixture
    assert "rojo" in datos.valor("SELECT descripcion_visual FROM personas")


def test_rtsp_posible_hurto_con_evidencia_y_fotos(en_vivo, monkeypatch, datos):
    import time as tiempo
    publicadas, fotos = [], []
    monkeypatch.setattr(config, "CAJA_PERMANENCIA_MINIMA_SEG", 100.0)    # nunca llega a pagar
    monkeypatch.setattr(config, "FOTOS_ACTIVAS", True)
    monkeypatch.setattr(m, "publicar_evidencia", lambda *args: publicadas.append(args[2]))

    class FotosFalsas:
        def __init__(self, *args):
            pass

        def registrar(self, sid, frame_count, frame, box):
            fotos.append(sid)

        def publicar_pendientes(self, ids, frame_count):
            pass

    monkeypatch.setattr(m, "CapturadorFotos", FotosFalsas)
    monkeypatch.setattr(sys, "argv", ["main.py", "--rtsp", "2"])
    m.main()
    alerta = datos.valor("SELECT id FROM alertas WHERE tipo = 'posible_hurto'")
    assert datos.valor("SELECT accion_detectada FROM eventos") == "POSIBLE_HURTO"
    for _ in range(50):                       # la evidencia se publica en un hilo aparte
        if publicadas:
            break
        tiempo.sleep(0.02)
    assert publicadas == [alerta] and fotos


def test_si_nadie_aparece_no_se_guarda_heatmap(pipeline, monkeypatch, datos, capsys):
    monkeypatch.setattr(YOLOFalso, "track", lambda self, frame, **k: resultado([], []))
    m.main()
    assert "Acumulador vacio, no se guarda en BD" in capsys.readouterr().out
    assert datos.valor("SELECT count(*) FROM mapas_calor") == 0


def test_barra_de_progreso(pipeline, monkeypatch):
    barras = []

    class Barra:
        def __init__(self, total, **kwargs):
            self.total, self.avance, self.cerrada = total, 0, False
            barras.append(self)

        def update(self, n):
            self.avance += n

        def close(self):
            self.cerrada = True

    monkeypatch.setattr(m, "tqdm", Barra)
    m.main()
    assert (barras[0].total, barras[0].avance, barras[0].cerrada) == (30, 30, True)


def test_rtsp_informa_las_fusiones_en_vivo_y_el_retraso_de_la_cpu(en_vivo, monkeypatch, capsys):
    monkeypatch.setattr(m.Persistencia, "fusionar_en_vivo", lambda self, *a: 2)
    monkeypatch.setattr(m, "_fps_actual", lambda muestras: 0.1)
    monkeypatch.setattr(sys, "argv", ["main.py", "--rtsp", "2"])
    m.main()
    salida = capsys.readouterr().out
    assert "[Fusion] 2 personas unificadas" in salida and "muy por debajo del objetivo" in salida


def test_webcam_que_falla_se_informa_y_relanza(en_vivo, monkeypatch, capsys):
    def rota(self):
        raise OSError("se desconecto la camara")

    monkeypatch.setattr(FuenteEnVivo, "read", rota)
    monkeypatch.setattr(sys, "argv", ["main.py", "--webcam"])
    with pytest.raises(OSError):
        m.main()
    assert "Camara en vivo detenida" in capsys.readouterr().out


def test_q_durante_la_pausa_termina(en_vivo, ventana, monkeypatch):
    mostrado, teclas = ventana
    teclas += [ord("p"), -1, ord("q")]
    monkeypatch.setattr(sys, "argv", ["main.py", "--webcam"])
    m.main()
    assert len(mostrado) == 1

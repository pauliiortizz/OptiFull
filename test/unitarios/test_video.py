"""Tests de los endpoints de video y tracking (frontend/api/video.py): streaming con Range, sesiones,
clips (ffmpeg simulado), tracking por sesion y por camara. La base de datos se simula con BDFalsa."""
import io
import json
from datetime import date, datetime

import pytest

from api import app
from api import video as m

CONTENIDO = bytes(range(256)) * 4   # 1024 bytes de "video"


@pytest.fixture
def cliente():
    return app.test_client()


@pytest.fixture
def videos(monkeypatch, tmp_path):
    (tmp_path / "caja.mp4").write_bytes(CONTENIDO)
    (tmp_path / "salon.MKV").write_bytes(b"mkv")
    (tmp_path / "notas.txt").write_text("no es video")
    monkeypatch.setattr(m, "VIDEOS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def con_bd(monkeypatch, bd):
    monkeypatch.setattr(m, "_db_connect", lambda: bd)
    return bd


# ── Carpeta local de videos y streaming ───────────────────────────────────────

def test_lista_solo_archivos_de_video(cliente, videos):
    assert cliente.get("/api/videos").get_json() == ["caja.mp4", "salon.MKV"]


def test_sin_carpeta_de_videos_devuelve_lista_vacia(cliente, monkeypatch, tmp_path):
    monkeypatch.setattr(m, "VIDEOS_DIR", str(tmp_path / "no_existe"))
    assert cliente.get("/api/videos").get_json() == []


def test_video_completo(cliente, videos):
    r = cliente.get("/api/video/caja.mp4")
    assert r.status_code == 200 and r.data == CONTENIDO
    assert (r.headers["Content-Type"], r.headers["Accept-Ranges"]) == ("video/mp4", "bytes")


@pytest.mark.parametrize("rango, desde, hasta", [
    ("bytes=0-99", 0, 99),
    ("bytes=1000-", 1000, 1023),     # sin fin: hasta el ultimo byte
    ("bytes=1023-1023", 1023, 1023),  # valor limite: el ultimo byte solo
])
def test_video_parcial_con_range(cliente, videos, rango, desde, hasta):
    r = cliente.get("/api/video/caja.mp4", headers={"Range": rango})
    assert r.status_code == 206
    assert r.data == CONTENIDO[desde:hasta + 1]
    assert r.headers["Content-Range"] == f"bytes {desde}-{hasta}/1024"


@pytest.mark.parametrize("ruta, status", [
    ("no_existe.mp4", 404),
    ("../secreto.mp4", 403),   # no puede salir de la carpeta de videos
])
def test_video_inexistente_o_fuera_de_la_carpeta(cliente, videos, ruta, status):
    (videos.parent / "secreto.mp4").write_bytes(b"x")
    assert cliente.get(f"/api/video/{ruta}").status_code == status


def test_mime_por_extension(cliente, videos):
    assert cliente.get("/api/video/salon.MKV").headers["Content-Type"] == "video/x-matroska"


# ── /sessions ─────────────────────────────────────────────────────────────────

def test_sesiones_con_offset_al_primer_evento(cliente, con_bd, videos):
    inicio = datetime(2026, 10, 7, 10)
    con_bd.responder("FROM sesiones_video sv", [
        {"id": 1, "camara_id": 2, "inicio": inicio, "fin": datetime(2026, 10, 7, 11),
         "archivo_path": str(videos / "caja.mp4"), "primer_evento": datetime(2026, 10, 7, 10, 0, 30)},
        {"id": 2, "camara_id": 2, "inicio": None, "fin": None, "archivo_path": None, "primer_evento": None},
        {"id": 3, "camara_id": 2, "inicio": inicio, "fin": None, "archivo_path": "x.mp4",
         "primer_evento": datetime(2026, 10, 7, 10, 0, 2)},
    ])
    s1, s2, s3 = cliente.get("/api/sessions").get_json()
    assert (s1["nombre"], s1["disponible"], s1["offset_seg"]) == ("caja.mp4", True, 25)   # 5 s antes del evento
    assert (s2["inicio"], s2["nombre"], s2["disponible"], s2["offset_seg"]) == (None, "", False, 0)
    assert s3["offset_seg"] == 0   # evento en los primeros 5 s: no puede quedar negativo


def test_sesiones_con_error_devuelve_lista_vacia(cliente, monkeypatch):
    monkeypatch.setattr(m, "_db_connect", lambda: None)
    assert cliente.get("/api/sessions").get_json() == []


# ── /sessions/<id>/video y /clip ──────────────────────────────────────────────

@pytest.mark.parametrize("ruta", ["/api/sessions/1/video", "/api/sessions/1/clip"])
def test_sesion_inexistente_o_sin_archivo_responde_404(cliente, con_bd, ruta):
    assert cliente.get(ruta).status_code == 404                     # la sesion no existe
    con_bd.responder("SELECT archivo_path", [("/no/existe.mp4",)])
    r = cliente.get(ruta)
    assert r.status_code == 404 and b"Archivo no encontrado" in r.data


@pytest.mark.parametrize("ruta", ["/api/sessions/1/video", "/api/sessions/1/clip"])
def test_sesion_con_error_de_bd_responde_500(cliente, con_bd, ruta):
    con_bd.error = RuntimeError("caida")
    assert cliente.get(ruta).status_code == 500


def test_video_de_sesion_y_clip_sin_ffmpeg_sirven_el_video_completo(cliente, con_bd, videos, monkeypatch):
    con_bd.responder("SELECT archivo_path", [(str(videos / "caja.mp4"),)])
    monkeypatch.setattr(m, "FFMPEG", None)
    assert cliente.get("/api/sessions/1/video").data == CONTENIDO
    assert cliente.get("/api/sessions/1/clip?t=10&dur=5").data == CONTENIDO


class ProcesoFalso:
    def __init__(self, cmd, stdout=None, stderr=None):
        ProcesoFalso.cmd = cmd
        self.stdout, self.stderr = io.BytesIO(b"mp4-recortado"), io.BytesIO(b"error de ffmpeg")

    def wait(self):
        self.terminado = True
        return ProcesoFalso.rc

    def poll(self):
        return ProcesoFalso.rc if getattr(self, "terminado", False) else None

    def kill(self):
        ProcesoFalso.matado = True


@pytest.mark.parametrize("rc", [0, 1])
def test_clip_con_ffmpeg_recorta_desde_t_con_duracion_dur(cliente, con_bd, videos, monkeypatch, rc):
    import subprocess
    con_bd.responder("SELECT archivo_path", [(str(videos / "caja.mp4"),)])
    monkeypatch.setattr(m, "FFMPEG", "/usr/bin/ffmpeg")
    ProcesoFalso.rc = rc
    monkeypatch.setattr(subprocess, "Popen", ProcesoFalso)
    r = cliente.get("/api/sessions/1/clip?t=12.5&dur=30")
    assert r.data == b"mp4-recortado" and r.mimetype == "video/mp4"
    cmd = ProcesoFalso.cmd
    assert cmd[cmd.index("-ss") + 1] == "12.5" and cmd[cmd.index("-t") + 1] == "30.0"
    # sale en H.264 (lo reproduce cualquier navegador) y se descarga como .mp4, no como 'clip' sin extension
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert r.headers["Content-Disposition"] == 'inline; filename="sesion_1_clip.mp4"'


def test_clip_si_el_navegador_corta_se_mata_ffmpeg(cliente, con_bd, videos, monkeypatch):
    import subprocess
    con_bd.responder("SELECT archivo_path", [(str(videos / "caja.mp4"),)])
    monkeypatch.setattr(m, "FFMPEG", "/usr/bin/ffmpeg")
    ProcesoFalso.rc, ProcesoFalso.matado = 0, False
    monkeypatch.setattr(subprocess, "Popen", ProcesoFalso)
    r = cliente.get("/api/sessions/1/clip", buffered=False)
    next(iter(r.response))   # el navegador recibe el primer pedazo y cierra la conexion
    r.close()
    assert ProcesoFalso.matado


def test_find_ffmpeg_en_el_path_o_ausente(monkeypatch):
    import glob
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _: "/opt/ffmpeg")
    assert m._find_ffmpeg() == "/opt/ffmpeg"
    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.setattr(glob, "glob", lambda *a, **k: [])
    assert m._find_ffmpeg() is None
    monkeypatch.setattr(glob, "glob", lambda *a, **k: [r"C:\ffmpeg\bin\ffmpeg.exe"])
    assert m._find_ffmpeg() == r"C:\ffmpeg\bin\ffmpeg.exe"


# ── Tracking por sesion y por camara ──────────────────────────────────────────

SESION = {"id": 1, "camara_id": 2, "inicio": datetime(2026, 10, 7, 10), "fin": datetime(2026, 10, 7, 11),
          "archivo_path": "/videos/caja.mp4", "frame_w": 1920, "frame_h": 1080, "camara_nombre": "Salón"}
PERSONA = {"id": 5, "cliente_id": 5, "primera_deteccion": datetime(2026, 10, 7, 10, 1), "ultima_deteccion": None,
           "duracion_total_seg": 60, "metodo_reid": "gemini", "es_empleado": False,
           "descripcion_visual": json.dumps({"ropa": "roja"})}
PUNTOS = [{"persona_id": 5, "timestamp": datetime(2026, 10, 7, 10, 1), "centroide_x": 100, "centroide_y": 400,
           "zona_id": 1, "zona_nombre": "Caja"},
          {"persona_id": 5, "timestamp": datetime(2026, 10, 7, 10, 2), "centroide_x": 300, "centroide_y": 200,
           "zona_id": None, "zona_nombre": None}]
ZONA = {"id": 1, "nombre": "Caja", "tipo": "caja", "poligono": [[0, 0], [10, 0], [10, 10]]}


def _responder_tracking(bd, personas=(PERSONA,), puntos=PUNTOS):
    bd.responder("FROM personas p", list(personas)).responder("FROM trayectorias t", list(puntos))
    bd.responder("FROM zonas WHERE camara_id", [ZONA])


def test_tracking_de_sesion_con_personas_trayectorias_y_limites(cliente, con_bd):
    con_bd.responder("WHERE sv.id = %s", [SESION])
    _responder_tracking(con_bd)
    datos = cliente.get("/api/sessions/1/tracking").get_json()
    assert datos["sesion"]["nombre"] == "caja.mp4"
    assert datos["personas"][0]["descripcion_visual"] == {"ropa": "roja"}
    assert datos["bounds"] == {"min_x": 100, "max_x": 300, "min_y": 200, "max_y": 400}
    assert datos["zonas"] == [ZONA]


def test_tracking_de_sesion_sin_personas_no_tiene_limites(cliente, con_bd):
    con_bd.responder("WHERE sv.id = %s", [{**SESION, "archivo_path": None, "fin": None}])
    _responder_tracking(con_bd, personas=())
    datos = cliente.get("/api/sessions/1/tracking").get_json()
    assert (datos["personas"], datos["trayectorias"], datos["bounds"]) == ([], [], None)


@pytest.mark.parametrize("ruta", ["/api/sessions/1/tracking", "/api/cameras/2/tracking"])
def test_tracking_sin_bd_o_sin_datos_devuelve_null_y_con_error_500(cliente, monkeypatch, bd, ruta):
    monkeypatch.setattr(m, "_db_connect", lambda: None)
    assert cliente.get(ruta).get_json() is None
    monkeypatch.setattr(m, "_db_connect", lambda: bd)
    assert cliente.get(ruta).get_json() is None
    bd.error = RuntimeError("caida")
    assert cliente.get(ruta).status_code == 500


@pytest.mark.parametrize("fecha, esperada", [(None, "2026-10-07"), ("2026-10-06", "2026-10-06"), ("1999-01-01", "2026-10-07")])
def test_tracking_de_camara_junta_las_sesiones_del_dia(cliente, con_bd, fecha, esperada):
    con_bd.responder("SELECT DISTINCT inicio::date", [{"fecha": date(2026, 10, 7)}, {"fecha": date(2026, 10, 6)}])
    con_bd.responder("WHERE sv.camara_id = %s AND sv.inicio::date", [
        {**SESION, "frame_w": None, "frame_h": None, "fin": None},
        {**SESION, "id": 2, "inicio": datetime(2026, 10, 7, 12), "fin": datetime(2026, 10, 7, 13)},
    ])
    _responder_tracking(con_bd)
    datos = cliente.get("/api/cameras/2/tracking", query_string={"fecha": fecha} if fecha else {}).get_json()
    sesion = datos["sesion"]
    assert sesion["fecha"] == esperada and sesion["n_videos"] == 2
    assert (sesion["inicio"], sesion["fin"]) == ("2026-10-07T10:00:00", "2026-10-07T13:00:00")
    assert (sesion["frame_w"], sesion["frame_h"]) == (1920, 1080)   # el primero que tenga resolucion
    assert len(datos["trayectorias"]) == 2


def test_tracking_de_camara_sin_sesiones_ese_dia_o_sin_fin(cliente, con_bd):
    con_bd.responder("SELECT DISTINCT inicio::date", [{"fecha": date(2026, 10, 7)}])
    assert cliente.get("/api/cameras/2/tracking").get_json() is None   # hay fecha pero no sesiones
    con_bd.responder("WHERE sv.camara_id = %s AND sv.inicio::date", [{**SESION, "fin": None}])
    _responder_tracking(con_bd, personas=())
    datos = cliente.get("/api/cameras/2/tracking").get_json()
    assert datos["sesion"]["fin"] is None and datos["bounds"] is None


# ── Regresion DEF-005 / DEF-006 / DEF-007 ─────────────────────────────────────

def test_range_de_sufijo_devuelve_los_ultimos_bytes(cliente, videos):
    # DEF-005: "bytes=-50" (los ultimos 50 bytes) es un Range valido y respondia 500
    r = cliente.get("/api/video/caja.mp4", headers={"Range": "bytes=-50"})
    assert r.status_code == 206
    assert r.data == CONTENIDO[-50:]
    assert r.headers["Content-Range"] == "bytes 974-1023/1024"


@pytest.mark.parametrize("rango, desde, hasta", [
    ("bytes=1000-5000", 1000, 1023),   # DEF-006: el fin se recorta al ultimo byte del archivo
    ("bytes=-5000", 0, 1023),          # sufijo mas largo que el archivo: el archivo entero
])
def test_range_mas_largo_que_el_archivo_se_recorta(cliente, videos, rango, desde, hasta):
    r = cliente.get("/api/video/caja.mp4", headers={"Range": rango})
    assert r.status_code == 206
    assert r.headers["Content-Range"] == f"bytes {desde}-{hasta}/1024"
    assert r.headers["Content-Length"] == str(hasta - desde + 1) == str(len(r.data))


@pytest.mark.parametrize("rango", ["bytes=1024-", "bytes=2000-3000", "bytes=50-10", "bytes=-0"])
def test_range_imposible_de_satisfacer_responde_416(cliente, videos, rango):
    r = cliente.get("/api/video/caja.mp4", headers={"Range": rango})
    assert r.status_code == 416
    assert r.headers["Content-Range"] == "bytes */1024"


@pytest.mark.parametrize("rango", ["items=0-10", "bytes=abc", "bytes=0-10,20-30"])
def test_range_mal_formado_o_multiple_se_ignora_y_devuelve_el_video_completo(cliente, videos, rango):
    r = cliente.get("/api/video/caja.mp4", headers={"Range": rango})
    assert r.status_code == 200 and r.data == CONTENIDO


@pytest.mark.parametrize("query", ["t=abc", "dur=diez", "t=-1", "dur=0", "dur=-5", "t=nan", "dur=inf"])
def test_clip_con_parametros_invalidos_responde_400(cliente, con_bd, videos, query):
    # DEF-007: ?t=abc respondia 500 (ValueError sin capturar)
    con_bd.responder("SELECT archivo_path", [(str(videos / "caja.mp4"),)])
    r = cliente.get(f"/api/sessions/1/clip?{query}")
    assert r.status_code == 400
    assert con_bd.consultas == []   # se valida antes de consultar la base de datos


def test_clip_sin_base_de_datos_responde_503(cliente, monkeypatch):
    monkeypatch.setattr(m, "_db_connect", lambda: None)
    assert cliente.get("/api/sessions/1/clip").status_code == 503
    assert cliente.get("/api/sessions/1/video").status_code == 503

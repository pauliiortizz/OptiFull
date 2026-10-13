"""Tests unitarios de deteccion/pipeline/evidencia.py: frames clave + clip de las alertas de posible hurto.
Frames sinteticos (sin camara ni BD); el clip usa ffmpeg real si esta instalado (si no, se saltea)."""
import json
import shutil
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from deteccion.pipeline.evidencia import GrabadorEvidencia, armar_clip_mp4, publicar_evidencia

T0 = datetime(2026, 10, 6, 12, 0, 0)


def _frame(n: int = 0) -> np.ndarray:
    img = np.full((180, 320, 3), 90 + n % 50, dtype=np.uint8)
    return img


def _grabador(**kw) -> GrabadorEvidencia:
    args = dict(fps=2.0, camara_id=2, buffer_seg=60, pre_seg=3, post_seg=3, salida_seg=5, frames_clave=6)
    args.update(kw)
    return GrabadorEvidencia(**args)


def _cargar(g: GrabadorEvidencia, desde: int, hasta: int, sid: int = 7, presente: bool = True) -> None:
    for n in range(desde, hasta + 1):
        det = [{"sid": sid, "box": (100 + n, 40, 160 + n, 150)}] if presente else []
        g.registrar_frame(n, T0 + timedelta(seconds=n / 2), _frame(n), det)


def test_el_buffer_conserva_solo_los_ultimos_segundos():
    g = _grabador(buffer_seg=10)               # 10 s * 2 fps = 20 frames
    _cargar(g, 1, 100)
    assert len(g._ring) == 20 and g._ring[0].frame == 81


def test_evidencia_de_un_hurto_incluye_antes_toma_despues_y_salida():
    g = _grabador()
    _cargar(g, 1, 20)
    g.marcar_toma(7, 20)                        # toma el producto en el frame 20
    _cargar(g, 21, 26)                          # sigue en camara 3 s mas (post)
    _cargar(g, 27, 80, presente=False)          # se va; el buffer sigue corriendo sin el
    # (reubicamos al final unos frames con el para simular la salida)
    ev = g.construir(7, 80)
    assert ev is not None
    etiquetas = [f["etiqueta"] for f in ev["frames"]]
    assert "Toma el producto" in etiquetas
    assert "Se acerca al producto" in etiquetas
    assert any("Se aleja" in e or "Se retira" in e for e in etiquetas)
    assert len(ev["frames"]) <= 8
    assert [f["frame"] for f in ev["frames"]] == sorted(f["frame"] for f in ev["frames"])
    assert len(ev["clip_jpgs"]) >= len(ev["frames"])


def test_los_frames_salen_anotados_y_se_pueden_decodificar():
    g = _grabador()
    _cargar(g, 1, 12)
    g.marcar_toma(7, 6)
    ev = g.construir(7, 12)
    img = cv2.imdecode(np.frombuffer(ev["frames"][0]["jpg"], np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[:2] == (180, 320)
    # el recuadro rojo de la persona (BGR ~ (40, 40, 230)) tiene que estar en la imagen
    rojo = (img[:, :, 2] > 180) & (img[:, :, 1] < 90) & (img[:, :, 0] < 90)
    assert rojo.sum() > 30
    assert ev["frames"][0]["ts"].startswith("2026-10-06T12:00")


def test_sin_toma_reservada_se_usan_los_ultimos_frames_en_camara():
    g = _grabador()
    _cargar(g, 1, 30)
    ev = g.construir(7, 30)                     # nunca se llamo a marcar_toma
    assert ev and all(f["etiqueta"] == "Se retira sin pasar por caja" for f in ev["frames"])


def test_sin_ninguna_imagen_de_esa_persona_devuelve_none():
    g = _grabador()
    _cargar(g, 1, 20, sid=99)
    assert g.construir(7, 20) is None


def test_liberar_descarta_lo_reservado_y_construir_lo_consume():
    g = _grabador()
    _cargar(g, 1, 10)
    g.marcar_toma(7, 5)
    assert g.tiene_toma(7)
    g.liberar(7)
    assert not g.tiene_toma(7)
    g.marcar_toma(7, 8)
    g.construir(7, 10)
    assert not g.tiene_toma(7)                  # ya se uso


def test_marcar_toma_dos_veces_no_pisa_la_primera():
    g = _grabador()
    _cargar(g, 1, 10)
    g.marcar_toma(7, 4)
    g.marcar_toma(7, 9)
    assert g._tomas[7]["frame"] == 4


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg no instalado")
def test_clip_mp4_real():
    jpgs = [cv2.imencode(".jpg", _frame(i))[1].tobytes() for i in range(8)]
    mp4 = armar_clip_mp4(jpgs, fps=3.0, ancho=320)
    assert mp4 and mp4[4:8] == b"ftyp"          # contenedor MP4 valido
    assert armar_clip_mp4([]) is None


class _AlmacenFalso:
    enabled = True

    def __init__(self, falla=False):
        self.falla, self.subidos = falla, {}

    def subir(self, ruta, contenido, content_type):
        if self.falla:
            return None
        self.subidos[ruta] = (len(contenido), content_type)
        return f"https://storage.test/{ruta}"


def _evidencia_de_prueba():
    g = _grabador()
    _cargar(g, 1, 12)
    g.marcar_toma(7, 6)
    return g.construir(7, 12)


def test_publicar_sube_frames_y_clip_y_actualiza_la_alerta():
    almacen, conn = _AlmacenFalso(), MagicMock()
    with patch("psycopg2.connect", return_value=conn):
        res = publicar_evidencia(almacen, "postgresql://x", 55, _evidencia_de_prueba())
    assert res and res["frames"] and all(f["url"].startswith("https://storage.test/evidencias/alerta_55/frame_") for f in res["frames"])
    if shutil.which("ffmpeg"):
        assert res["video"] == "https://storage.test/evidencias/alerta_55/clip.mp4"
        assert almacen.subidos["evidencias/alerta_55/clip.mp4"][1] == "video/mp4"
    sql, params = conn.cursor.return_value.execute.call_args[0]
    assert "UPDATE alertas SET evidencia" in sql and params[1] == 55
    assert json.loads(params[0])["frames"][0]["etiqueta"]
    conn.commit.assert_called_once()


def test_si_storage_falla_se_guarda_en_la_carpeta_local(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conn = MagicMock()
    with patch("psycopg2.connect", return_value=conn):
        res = publicar_evidencia(_AlmacenFalso(falla=True), "postgresql://x", 56, _evidencia_de_prueba())
    assert res["frames"][0]["url"] == "alerta_56/frame_01.jpg"      # ruta relativa a la carpeta evidencias/
    assert (tmp_path / "evidencias" / "alerta_56" / "frame_01.jpg").is_file()


# ── API: evidencia que ve el frontend ───────────────────────────────────────

from api.alertas import _evidencia_para_front, _url_evidencia


def test_url_de_storage_se_deja_igual_y_la_local_pasa_por_la_api():
    assert _url_evidencia("https://x.supabase.co/storage/v1/object/public/h/e.jpg") == "https://x.supabase.co/storage/v1/object/public/h/e.jpg"
    assert _url_evidencia("alerta_5/frame_01.jpg") == "/api/evidencias/alerta_5/frame_01.jpg"
    assert _url_evidencia(r"alerta_5\frame_01.jpg") == "/api/evidencias/alerta_5/frame_01.jpg"
    assert _url_evidencia(None) is None


def test_alerta_sin_evidencia_devuelve_none():
    assert _evidencia_para_front(None) is None
    assert _evidencia_para_front({}) is None
    assert _evidencia_para_front({"video": None, "frames": []}) is None


def test_evidencia_para_el_frontend_con_y_sin_clip():
    ev = {"video": "alerta_5/clip.mp4", "frames": [{"url": "alerta_5/frame_01.jpg", "etiqueta": "Toma el producto", "ts": "2026-10-06T12:00:03"}]}
    r = _evidencia_para_front(ev)
    assert r["video"] == "/api/evidencias/alerta_5/clip.mp4"
    assert r["frames"] == [{"url": "/api/evidencias/alerta_5/frame_01.jpg", "etiqueta": "Toma el producto", "ts": "2026-10-06T12:00:03"}]
    assert _evidencia_para_front({"video": None, "frames": ev["frames"]})["video"] is None


def test_la_api_no_sirve_archivos_fuera_de_la_carpeta_de_evidencias():
    from api import app
    c = app.test_client()
    assert c.get("/api/evidencias/../.env").status_code == 404
    assert c.get("/api/evidencias/no_existe.jpg").status_code == 404

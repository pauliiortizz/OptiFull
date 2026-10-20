"""Tests de los endpoints de mapas de calor (frontend/api/heatmap.py).
La base de datos se simula con BDFalsa (conftest.py)."""
import pytest

from api import app
from api import heatmap as m

PNG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def cliente():
    return app.test_client()


# ── /heatmap/image/<archivo> ──────────────────────────────────────────────────
# Regresion de DEF-002: el endpoint servia CUALQUIER archivo de la carpeta del proyecto
# (incluido el .env con DATABASE_URL y las API keys). Solo debe servir imagenes de heatmap.

@pytest.fixture
def proyecto(monkeypatch, tmp_path):
    """Carpeta de proyecto falsa: heatmap.BASE apunta a <tmp>/frontend, la raiz es <tmp>."""
    (tmp_path / "frontend" / "api").mkdir(parents=True)
    (tmp_path / "heatmaps_pendientes").mkdir()
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql://usuario:clave@supabase/optifull")
    (tmp_path / "frontend" / "api" / "db.py").write_text("codigo fuente")
    (tmp_path / "README.md").write_text("readme")
    (tmp_path / "heatmaps_pendientes" / "camara_1_combinado.png").write_bytes(PNG)
    (tmp_path / "heatmaps_pendientes" / "notas.txt").write_text("no es imagen")
    (tmp_path / "camara_2_viejo.png").write_bytes(PNG)   # heatmaps viejos: nombre suelto en la raiz
    monkeypatch.setattr(m, "BASE", str(tmp_path / "frontend"))
    return tmp_path


@pytest.mark.parametrize("ruta", [
    "heatmaps_pendientes/camara_1_combinado.png",
    "camara_2_viejo.png",
])
def test_sirve_las_imagenes_de_heatmap_guardadas_localmente(cliente, proyecto, ruta):
    r = cliente.get(f"/api/heatmap/image/{ruta}")
    assert r.status_code == 200
    assert r.data == PNG


@pytest.mark.parametrize("ruta", [
    ".env",                                     # credenciales de la base de datos y API keys
    "frontend/api/db.py",                       # codigo fuente
    "README.md",
    "heatmaps_pendientes/notas.txt",            # carpeta correcta, pero no es una imagen
    "frontend/api/../../.env",                  # mismo archivo por otro camino
    "heatmaps_pendientes/../.env",
])
def test_no_sirve_archivos_que_no_son_imagenes_de_heatmap(cliente, proyecto, ruta):
    r = cliente.get(f"/api/heatmap/image/{ruta}")
    assert r.status_code == 404
    assert b"DATABASE_URL" not in r.data


def test_imagen_inexistente_responde_404(cliente, proyecto):
    assert cliente.get("/api/heatmap/image/heatmaps_pendientes/no_existe.png").status_code == 404


# ── Sin base de datos o con error ─────────────────────────────────────────────
# DEF-003: /heatmap/latest y /heatmap/camara/<id> respondian 500 ("'NoneType' object has no
# attribute 'cursor'") sin base de datos; el resto de la API responde 503.

@pytest.mark.parametrize("ruta", ["/api/heatmap/latest", "/api/heatmap/camara/2", "/api/heatmap/plano",
                                  "/api/heatmap/plano/tiempo?refrescar=1", "/api/heatmap/plano/flujo?refrescar=1"])
def test_sin_base_de_datos_responde_503(cliente, monkeypatch, ruta):
    monkeypatch.setattr(m, "_db_connect", lambda: None)
    r = cliente.get(ruta)
    assert r.status_code == 503
    assert r.get_json() == {"error": "sin conexion a la BD"}


@pytest.mark.parametrize("ruta", ["/api/heatmap/latest", "/api/heatmap/camara/2", "/api/heatmap/plano",
                                  "/api/heatmap/plano/tiempo?refrescar=1", "/api/heatmap/plano/flujo?refrescar=1",
                                  "/api/cameras/2/heatmaps"])
def test_error_de_la_base_de_datos_responde_500(cliente, monkeypatch, bd, ruta):
    bd.error = RuntimeError("timeout")
    monkeypatch.setattr(m, "_db_connect", lambda: bd)
    r = cliente.get(ruta)
    assert r.status_code == 500 and r.get_json() == {"error": "timeout"}

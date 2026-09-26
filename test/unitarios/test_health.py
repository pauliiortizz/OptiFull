"""Tests de /api/health (frontend/api/health.py): sin BD real, se mockea _get_conn."""
from unittest.mock import MagicMock, patch

from api import app


def _get_health():
    return app.test_client().get("/api/health")


def test_health_ok_con_bd_disponible(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    monkeypatch.setenv("APP_ENV", "qa")
    conn = MagicMock()
    with patch("api.health._get_conn", return_value=conn):
        r = _get_health()
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "db": "ok", "commit": "abc123", "env": "qa"}
    conn.close.assert_called_once()


def test_health_sigue_200_si_no_hay_conexion_a_la_bd():
    # Liveness: un corte de BD no debe tirar el servicio, solo reportarse en el body.
    with patch("api.health._get_conn", return_value=None):
        r = _get_health()
    assert r.status_code == 200
    assert r.get_json()["db"] == "error"


def test_health_db_error_si_la_consulta_falla():
    conn = MagicMock()
    conn.cursor.side_effect = RuntimeError("boom")
    with patch("api.health._get_conn", return_value=conn):
        r = _get_health()
    assert r.status_code == 200
    assert r.get_json()["db"] == "error"
    conn.close.assert_called_once()

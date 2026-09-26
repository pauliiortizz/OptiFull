"""Pruebas de integracion contra un despliegue REAL (contenedor local, QA o PROD).

No usan mocks: le pegan por HTTP a la URL indicada en BASE_URL y validan que
frontend, API y base de datos funcionan juntos. Solo hacen lecturas (GET) y un
export (POST que no escribe nada).

  BASE_URL=https://optifull-qa.onrender.com pytest test/integracion
  EXPECTED_COMMIT=<sha>   (opcional) exige que el servicio corra ese commit
  pytest -m smoke         solo lo minimo (lo que se corre tambien en PRODUCCION)

Si BASE_URL no esta definida se saltean todas (para no romper `pytest` local).
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
EXPECTED_COMMIT = os.environ.get("EXPECTED_COMMIT")
# Render (plan gratuito) duerme el servicio tras 15 min sin trafico: el primer
# request puede tardar ~1 min en despertarlo.
TIMEOUT = 90

pytestmark = pytest.mark.skipif(not BASE_URL, reason="BASE_URL no definida")


def _get(path, **kw):
    return requests.get(f"{BASE_URL}{path}", timeout=TIMEOUT, **kw)


# ── Smoke: minimo indispensable (se corre tambien contra produccion) ──────────

@pytest.mark.smoke
def test_health_servicio_vivo_y_con_bd():
    r = _get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok", "La API no logra conectarse a la base de datos"


@pytest.mark.smoke
@pytest.mark.skipif(not EXPECTED_COMMIT, reason="EXPECTED_COMMIT no definido")
def test_health_corre_el_commit_esperado():
    assert _get("/api/health").json()["commit"] == EXPECTED_COMMIT


@pytest.mark.smoke
def test_frontend_se_sirve():
    r = _get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["Content-Type"]
    assert "OptiFull" in r.text


# ── Integracion completa (solo QA / contenedor local) ─────────────────────────

def test_spa_fallback_devuelve_index_en_rutas_desconocidas():
    r = _get("/reportes/alguna-ruta-del-frontend")
    assert r.status_code == 200
    assert "text/html" in r.headers["Content-Type"]


def test_stats_devuelve_kpis_desde_la_bd():
    r = _get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    for campo in ("personas_totales", "personas_unicas", "permanencia_promedio_min", "distribucion"):
        assert campo in body
    assert body["fuente"] == "db"


def test_personas_lista_registros():
    r = _get("/api/personas")
    assert r.status_code == 200
    assert isinstance(r.json()["registros"], list)


def test_alertas_responde_json():
    r = _get("/api/alertas")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/json")


def test_sesiones_devuelve_lista():
    r = _get("/api/sessions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_reportes_opciones_expone_catalogo_y_camaras():
    r = _get("/api/reportes/opciones")
    assert r.status_code == 200
    body = r.json()
    assert body["metricas"] and body["formatos"]
    assert isinstance(body["camaras"], list)


def test_reportes_exportar_valida_el_body():
    # Sin metricas debe rechazar con 400 (valida que el endpoint POST esta vivo
    # sin generar ningun archivo pesado).
    r = requests.post(f"{BASE_URL}/api/reportes/exportar", json={}, timeout=TIMEOUT)
    assert r.status_code == 400
    assert "error" in r.json()


def test_reportes_exportar_csv_end_to_end():
    opciones = _get("/api/reportes/opciones").json()
    metrica = opciones["metricas"][0]
    metrica_id = metrica["id"] if isinstance(metrica, dict) else metrica
    r = requests.post(
        f"{BASE_URL}/api/reportes/exportar",
        json={"metricas": [metrica_id], "formato": "csv", "camaras": []},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200
    assert len(r.content) > 0

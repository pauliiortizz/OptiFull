"""Tests de los endpoints de mapas de calor (frontend/api/heatmap.py).
La base de datos se simula con BDFalsa (conftest.py)."""
import json
from datetime import date, datetime

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


# ── /heatmap/latest y /heatmap/camara/<id> ────────────────────────────────────

MAPA = {"id": 1, "camara_id": 2, "camara_nombre": "Salón", "periodo_inicio": datetime(2026, 10, 7, 9),
        "periodo_fin": None, "imagen_path": "heatmaps_pendientes/c.png", "punto_max_x": 10, "punto_max_y": 20,
        "valor_maximo": 9, "area_activa_pct": 30.5, "concentracion": 0.4, "total_detecciones": 100,
        "frames_procesados": 500, "zona_mas_caliente_nombre": "Góndola A", "sesion_id": 7,
        "sesiones_combinadas": 3, "actualizado_en": datetime(2026, 10, 7, 10)}


@pytest.fixture
def con_bd(monkeypatch, bd):
    monkeypatch.setattr(m, "_db_connect", lambda: bd)
    return bd


@pytest.fixture(autouse=True)
def sin_cache(monkeypatch):
    """Cada test arranca sin las respuestas ni matrices cacheadas por otro."""
    monkeypatch.setattr(m, "_CACHE_MATRICES", {})
    monkeypatch.setattr(m, "_CACHE_PLANO_TIEMPO", {"t": 0.0, "clave": None, "version": None, "resp": None})
    monkeypatch.setattr(m, "_CACHE_PLANO_FLUJO", {"t": 0.0, "clave": None, "version": None, "resp": None})


def test_latest_sin_mapas_devuelve_null(cliente, con_bd):
    assert cliente.get("/api/heatmap/latest").get_json() is None


def test_latest_arma_el_ranking_de_zonas_de_la_sesion(cliente, con_bd):
    con_bd.responder("FROM   mapas_calor mc", [MAPA])
    con_bd.responder("FROM   trayectorias t", [{"nombre": "Góndola A", "detecciones": 3},
                                                {"nombre": "Caja", "detecciones": 1}])
    datos = cliente.get("/api/heatmap/latest").get_json()
    assert datos["imagen_url"] == "/api/heatmap/image/heatmaps_pendientes/c.png"
    assert (datos["periodo_inicio"], datos["periodo_fin"]) == ("2026-10-07T09:00:00", None)
    assert datos["zonas_ranking"] == [{"nombre": "Góndola A", "detecciones": 3, "pct": 75},
                                      {"nombre": "Caja", "detecciones": 1, "pct": 25}]


def test_latest_sin_sesion_no_consulta_trayectorias(cliente, con_bd):
    con_bd.responder("FROM   mapas_calor mc", [{**MAPA, "sesion_id": None, "periodo_inicio": None}])
    datos = cliente.get("/api/heatmap/latest").get_json()
    assert datos["zonas_ranking"] == [] and len(con_bd.consultas) == 1


@pytest.mark.parametrize("filas, esperado", [([], None), ([MAPA], 3), ([{**MAPA, "actualizado_en": None}], 3)])
def test_heatmap_acumulado_de_una_camara(cliente, con_bd, filas, esperado):
    con_bd.responder("FROM   mapas_calor_camara", filas)
    datos = cliente.get("/api/heatmap/camara/2").get_json()
    assert (datos or {}).get("sesiones_combinadas") == esperado


# ── /heatmap/plano, /plano/tiempo y /plano/flujo ──────────────────────────────

CAJA = [[0, 0], [960, 0], [960, 540], [0, 540]]   # cuarto superior izquierdo del frame 1920x1080


def _zonas_plano(bd, cam=4):
    bd.responder("FROM zonas", [{"camara_id": cam, "nombre": "Caja", "tipo": "caja", "poligono": json.dumps(CAJA)}])


def test_plano_usa_la_camara_fuente_de_cada_tipo(cliente, con_bd):
    con_bd.responder("FROM mapas_calor_camara", [
        {"camara_id": 4, "matriz": json.dumps([[1.0, 0.0], [0.0, 0.0]]), "valor_maximo": 8, "total_detecciones": 50,
         "actualizado_en": None, "nombre": "Caja lateral"},
        {"camara_id": 9, "matriz": [[1.0]], "valor_maximo": 1, "total_detecciones": 1,     # no es fuente de nada
         "actualizado_en": None, "nombre": "Otra"},
    ])
    _zonas_plano(con_bd)
    datos = cliente.get("/api/heatmap/plano").get_json()
    assert datos["zonas"]["caja"]["camara_id"] == 4 and datos["zonas"]["caja"]["pico"] == 1.0
    assert list(datos["camaras"]) == ["4"]
    assert con_bd.consultas[0][1] == ([2, 4],)          # solo pide las camaras fuente


def test_plano_trae_la_matriz_solo_cuando_cambia(cliente, con_bd):
    mapa = {"camara_id": 4, "matriz": [[1.0, 0.0], [0.0, 0.0]], "valor_maximo": 8, "total_detecciones": 50,
            "actualizado_en": datetime(2026, 10, 7, 10), "nombre": "Caja lateral"}
    con_bd.responder("FROM mapas_calor_camara", [mapa])
    _zonas_plano(con_bd)
    primera = cliente.get("/api/heatmap/plano").get_json()
    assert sum("SELECT camara_id, matriz" in sql for sql, _ in con_bd.consultas) == 1
    assert cliente.get("/api/heatmap/plano").get_json() == primera
    assert sum("SELECT camara_id, matriz" in sql for sql, _ in con_bd.consultas) == 1   # misma version: del cache
    mapa["actualizado_en"] = datetime(2026, 10, 7, 11)
    cliente.get("/api/heatmap/plano")
    assert sum("SELECT camara_id, matriz" in sql for sql, _ in con_bd.consultas) == 2


def test_plano_el_parametro_fuentes_cambia_la_camara_e_ignora_valores_invalidos(cliente, con_bd):
    con_bd.responder("FROM mapas_calor_camara", [
        {"camara_id": 3, "matriz": [[1.0, 1.0], [1.0, 1.0]], "valor_maximo": 2, "total_detecciones": 4,
         "actualizado_en": datetime(2026, 10, 7), "nombre": "Frontal"},
        {"camara_id": 4, "matriz": [], "valor_maximo": 0, "total_detecciones": 0,   # sin matriz: se saltea
         "actualizado_en": None, "nombre": "Lateral"},
    ])
    _zonas_plano(con_bd, cam=3)
    datos = cliente.get("/api/heatmap/plano?fuentes=caja:3,gondola:x,inventado:5").get_json()
    assert datos["zonas"]["caja"]["camara_id"] == 3
    assert datos["camaras"]["3"]["actualizado_en"] == "2026-10-07T00:00:00"


def _trayectorias_plano(bd):
    """Lo que devuelve la base ya agrupado: posiciones por dia, celdas de /tiempo y corridas de /flujo."""
    bd.responder("GROUP BY camara_id, dia", [{"camara_id": 4, "dia": date(2026, 10, 7), "n": 6}])
    bd.responder("AS bloque", [{"tipo": "caja", "bloque": 120, "col": 3, "fila": 3, "n": 6}])
    bd.responder("AS corrida", [{"camara_id": 4, "persona_id": 1, "corrida": 1, "tipo": "caja", "seg": 36000 + i * 10,
                                 "xn": (100 + i * 80) / 1920, "yn": 100 / 1080} for i in range(6)])


def test_plano_tiempo_arma_las_celdas_que_agrupa_la_base(cliente, con_bd):
    _trayectorias_plano(con_bd)
    _zonas_plano(con_bd)
    datos = cliente.get("/api/heatmap/plano/tiempo?refrescar=1").get_json()
    assert datos["zonas"]["caja"]["celdas"] == [[120, 3, 3, 6]] and datos["zonas"]["caja"]["dias"] == 1
    assert datos["rango"] == {"desde": 10 * 60, "hasta": 11 * 60}
    sql, params = next(c for c in con_bd.consultas if "AS bloque" in c[0])
    assert params["tipos"] == ["caja"] and params["polys"] == ["((0.0,0.0),(960.0,0.0),(960.0,540.0),(0.0,540.0))"]


def test_plano_flujo_arma_los_tramos_de_las_corridas_que_parte_la_base(cliente, con_bd):
    _trayectorias_plano(con_bd)
    _zonas_plano(con_bd)
    tramos = cliente.get("/api/heatmap/plano/flujo?refrescar=1").get_json()["zonas"]["caja"]["tramos"]
    assert len(tramos) == 1 and tramos[0][0] == 600 and len(tramos[0][1]) == 12


@pytest.mark.parametrize("ruta, clave", [("/api/heatmap/plano/tiempo", "rango"), ("/api/heatmap/plano/flujo", "zonas")])
def test_plano_tiempo_y_flujo_se_cachean_dos_minutos(cliente, con_bd, ruta, clave):
    _trayectorias_plano(con_bd)
    _zonas_plano(con_bd)
    primera = cliente.get(f"{ruta}?refrescar=1").get_json()
    consultas = len(con_bd.consultas)
    segunda = cliente.get(ruta).get_json()          # misma clave de fuentes: sale del cache
    assert clave in primera and segunda == primera
    assert len(con_bd.consultas) == consultas


@pytest.mark.parametrize("ruta", ["/api/heatmap/plano/tiempo", "/api/heatmap/plano/flujo"])
def test_plano_tiempo_y_flujo_no_vuelven_a_traer_datos_que_no_cambiaron(cliente, con_bd, ruta):
    con_bd.responder("FROM pg_stat_user_tables", [{"cambios": 1234}])
    _trayectorias_plano(con_bd)
    _zonas_plano(con_bd)
    primera = cliente.get(f"{ruta}?refrescar=1").get_json()
    consultas = len(con_bd.consultas)
    assert cliente.get(f"{ruta}?refrescar=1").get_json() == primera
    assert [sql for sql, _ in con_bd.consultas[consultas:]] == [con_bd.consultas[0][0]]   # solo la de la version


def test_plano_tiempo_vuelve_a_consultar_si_cambiaron_los_datos(cliente, con_bd):
    _trayectorias_plano(con_bd)
    _zonas_plano(con_bd)
    con_bd.reglas.insert(0, ("FROM pg_stat_user_tables", [{"cambios": 1}]))
    cliente.get("/api/heatmap/plano/tiempo?refrescar=1")
    con_bd.reglas[0] = ("FROM pg_stat_user_tables", [{"cambios": 2}])
    consultas = len(con_bd.consultas)
    cliente.get("/api/heatmap/plano/tiempo?refrescar=1")
    assert any("AS bloque" in sql for sql, _ in con_bd.consultas[consultas:])


# ── /cameras/<id>/heatmaps ────────────────────────────────────────────────────

def test_heatmaps_de_una_camara_sin_bd_o_sin_fechas_devuelve_null(cliente, monkeypatch, bd):
    monkeypatch.setattr(m, "_db_connect", lambda: None)
    assert cliente.get("/api/cameras/2/heatmaps").get_json() is None
    monkeypatch.setattr(m, "_db_connect", lambda: bd)
    assert cliente.get("/api/cameras/2/heatmaps").get_json() is None


@pytest.mark.parametrize("fecha, esperada", [
    (None, "2026-10-07"),            # sin fecha: el dia mas reciente
    ("2026-10-06", "2026-10-06"),    # fecha con datos
    ("2025-01-01", "2026-10-07"),    # fecha sin datos: vuelve al mas reciente
])
def test_heatmaps_de_una_camara_por_dia(cliente, con_bd, fecha, esperada):
    con_bd.responder("SELECT DISTINCT periodo_inicio::date", [{"fecha": date(2026, 10, 7)}, {"fecha": date(2026, 10, 6)}])
    con_bd.responder("FROM mapas_calor mc", [MAPA])
    con_bd.responder("FROM camaras WHERE id", [{"nombre": "Salón"}])
    datos = cliente.get("/api/cameras/2/heatmaps", query_string={"fecha": fecha} if fecha else {}).get_json()
    assert datos["fecha"] == esperada
    assert datos["fechas_disponibles"] == ["2026-10-07", "2026-10-06"]
    assert datos["camara_nombre"] == "Salón" and len(datos["heatmaps"]) == 1


# ── /heatmap/fondo/<id> ───────────────────────────────────────────────────────

def test_fondo_de_camara(cliente, monkeypatch, tmp_path):
    monkeypatch.setattr(m, "FONDOS_DIR", str(tmp_path / "no_existe"))
    assert cliente.get("/api/heatmap/fondo/2").status_code == 404
    monkeypatch.setattr(m, "FONDOS_DIR", str(tmp_path))
    (tmp_path / "camara_2.webp").write_bytes(b"webp")
    assert cliente.get("/api/heatmap/fondo/2").data == b"webp"
    assert cliente.get("/api/heatmap/fondo/3").status_code == 404

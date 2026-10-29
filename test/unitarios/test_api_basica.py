"""Tests de los endpoints basicos de la API: /stats, /personas, /personas/<id>/empleado, /en-tienda
(stats.py), /alertas (alertas.py), /leads (leads.py), la carga de datos (db.py) y el servido del
frontend compilado (__init__.py). La base de datos se simula con BDFalsa (conftest.py)."""
import json
from datetime import date, datetime

import pytest

import api
from api import alertas, db, leads, stats

CSV = "id,entrada,salida,duracion_seg,duracion_min\n1,10:00:00,10:05:00,300,5.0\n2,11:00:00,11:00:20,20,0.33\n"


@pytest.fixture
def cliente():
    return api.app.test_client()


@pytest.fixture
def csv_local(monkeypatch, tmp_path):
    ruta = tmp_path / "permanencia.csv"
    ruta.write_text(CSV, encoding="utf-8")
    monkeypatch.setattr(db, "CSV_PATH", str(ruta))
    return ruta


# ── db.py: conexion y carga de datos ──────────────────────────────────────────

def test_get_conn_sin_database_url_devuelve_none(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db._get_conn() is None


def test_get_conn_con_base_inalcanzable_devuelve_none(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/optifull")   # puerto cerrado
    assert db._get_conn() is None


@pytest.mark.parametrize("ruta, esperado", [
    (None, None),
    ("https://x.supabase.co/heatmaps/a.png", "https://x.supabase.co/heatmaps/a.png"),
    ("heatmaps_pendientes\\camara_1.png", "/api/heatmap/image/heatmaps_pendientes/camara_1.png"),
])
def test_imagen_url(ruta, esperado):
    assert db._imagen_url(ruta) == esperado


def test_cargar_csv_lee_cada_fila_como_un_cliente(csv_local):
    filas = db.cargar_csv()
    assert [f["cliente_id"] for f in filas] == [1, 2]
    assert filas[0]["duracion_min"] == 5.0


@pytest.mark.parametrize("cargar", [db.cargar_db, db.cargar_permanencias_db])
def test_cargar_desde_bd_calcula_minutos_y_pasa_el_rango(monkeypatch, bd, cargar):
    bd.responder("SELECT", [{"cliente_id": 3, "duracion_seg": 150}])
    monkeypatch.setattr(db, "_get_conn", lambda: bd)
    filas = cargar(date(2026, 10, 1), date(2026, 10, 7))
    assert filas == [{"cliente_id": 3, "duracion_seg": 150, "duracion_min": 2.5}]
    assert bd.consultas[0][1]["desde"] == date(2026, 10, 1)
    assert bd.cerrada


@pytest.mark.parametrize("cargar", [db.cargar_db, db.cargar_permanencias_db])
def test_cargar_desde_bd_sin_conexion_o_con_error_devuelve_none(monkeypatch, bd, cargar):
    monkeypatch.setattr(db, "_get_conn", lambda: None)
    assert cargar() is None
    bd.error = RuntimeError("caida")
    monkeypatch.setattr(db, "_get_conn", lambda: bd)
    assert cargar() is None


@pytest.mark.parametrize("vacio_ok, esperado", [(True, []), (False, None)])
def test_cargar_db_rango_sin_personas(monkeypatch, bd, vacio_ok, esperado):
    # vacio_ok distingue "sin datos en el periodo" ([]) de "BD caida" (None)
    monkeypatch.setattr(db, "_get_conn", lambda: bd)
    assert db.cargar_db(vacio_ok=vacio_ok) == esperado


# ── /stats y /personas ────────────────────────────────────────────────────────

def test_stats_desde_la_bd_usa_permanencias_y_devuelve_el_rango(cliente, monkeypatch):
    filas = [{"cliente_id": 1, "duracion_min": 3.0}, {"cliente_id": 1, "duracion_min": 4.0}]
    monkeypatch.setattr(stats, "cargar_db", lambda d, h, vacio_ok: filas)
    monkeypatch.setattr(stats, "cargar_permanencias_db", lambda d, h: [{"cliente_id": 1, "duracion_min": 7.0}])
    datos = cliente.get("/api/stats?desde=2026-10-01&hasta=2026-10-07").get_json()
    assert datos["fuente"] == "db"
    assert (datos["personas_totales"], datos["personas_unicas"]) == (2, 1)
    assert datos["permanencia_promedio_min"] == 7.0
    assert datos["rango"] == {"desde": "2026-10-01", "hasta": "2026-10-07"}


def test_stats_filtra_los_30_s_con_los_segundos_sin_redondear():
    # 30,2 s redondeado a 2 decimales de minuto da 0,50 min = 30 s: con 'duracion_min' quedaba afuera.
    perm = [{"cliente_id": 1, "duracion_seg": 30.2, "duracion_min": 0.5},
            {"cliente_id": 2, "duracion_seg": 30.0, "duracion_min": 0.5},     # 30 s justos: no es > 30
            {"cliente_id": 3, "duracion_seg": 600.0, "duracion_min": 10.0}]
    datos = stats.calcular_stats([], perm)
    assert datos["personas_validas"] == 2
    assert datos["permanencia_promedio_min"] == round((30.2 / 60 + 10) / 2, 1)


def test_stats_sin_bd_cae_al_csv(cliente, monkeypatch, csv_local):
    monkeypatch.setattr(stats, "cargar_db", lambda d, h, vacio_ok: None)
    datos = cliente.get("/api/stats").get_json()
    assert datos["fuente"] == "csv"
    assert datos["personas_totales"] == 2
    assert datos["rango"] == {"desde": None, "hasta": None}


@pytest.mark.parametrize("ruta", ["/api/stats", "/api/personas"])
def test_sin_bd_ni_csv_responde_500(cliente, monkeypatch, tmp_path, ruta):
    monkeypatch.setattr(stats, "cargar_db", lambda *a, **k: None)
    monkeypatch.setattr(db, "CSV_PATH", str(tmp_path / "no_existe.csv"))
    assert cliente.get(ruta).status_code == 500


def test_personas_lista_los_registros_con_su_fuente(cliente, monkeypatch, csv_local):
    monkeypatch.setattr(stats, "cargar_db", lambda **k: [{"id": 1}])
    assert cliente.get("/api/personas").get_json() == {"fuente": "db", "registros": [{"id": 1}]}
    monkeypatch.setattr(stats, "cargar_db", lambda **k: None)
    assert cliente.get("/api/personas").get_json()["fuente"] == "csv"


# ── /personas/<id>/empleado ───────────────────────────────────────────────────

@pytest.mark.parametrize("body, es_empleado, revisado, columna", [
    ({}, True, False, "SET es_empleado = %s WHERE"),
    ({"es_empleado": False, "revisado": True}, False, True, "empleado_revisado = TRUE"),
])
def test_marcar_empleado_actualiza_persona_y_trayectorias(cliente, monkeypatch, bd, body, es_empleado, revisado, columna):
    monkeypatch.setattr(db, "_get_conn", lambda: bd)
    r = cliente.post("/api/personas/7/empleado", json=body)
    assert r.status_code == 200
    assert r.get_json() == {"cliente_id": 7, "es_empleado": es_empleado, "revisado": revisado}
    assert columna in bd.consultas[0][0]
    assert any("UPDATE trayectorias" in sql for sql, _ in bd.consultas)   # copia desnormalizada en trayectorias
    assert any("foto_url = NULL" in sql for sql, _ in bd.consultas) == revisado   # resuelta: se borra la foto
    assert bd.commits == 1


def test_resolver_posible_empleado_borra_sus_fotos(cliente, monkeypatch, bd):
    bd.responder("RETURNING foto_url", [("evidencias/personas/persona_7.jpg",), ("https://x.supabase.co/p_8.jpg",)])
    monkeypatch.setattr(db, "_get_conn", lambda: bd)
    borradas = []
    monkeypatch.setattr(alertas, "borrar_archivos_evidencia",
                        lambda ev: borradas.extend(f["url"] for f in ev["frames"]) or len(ev["frames"]))
    r = cliente.post("/api/personas/7/empleado", json={"es_empleado": True, "revisado": True})
    assert r.get_json()["fotos_borradas"] == 2
    assert borradas == ["evidencias/personas/persona_7.jpg", "https://x.supabase.co/p_8.jpg"]


def test_marcar_empleado_persona_inexistente_responde_404(cliente, monkeypatch, bd):
    bd.rowcount = 0
    monkeypatch.setattr(db, "_get_conn", lambda: bd)
    assert cliente.post("/api/personas/999/empleado", json={}).status_code == 404


@pytest.mark.parametrize("conexion, status", [(None, 503), ("error", 500)])
def test_marcar_empleado_sin_bd_o_con_error(cliente, monkeypatch, bd, conexion, status):
    bd.error = RuntimeError("caida")
    monkeypatch.setattr(db, "_get_conn", lambda: None if conexion is None else bd)
    assert cliente.post("/api/personas/7/empleado", json={}).status_code == status


# ── /en-tienda ────────────────────────────────────────────────────────────────

def test_en_tienda_cuenta_por_camara_total_unico_y_si_hay_analisis_en_vivo(cliente, monkeypatch, bd):
    bd.responder("GROUP BY sv.camara_id", [(2, 3), (4, 1)])
    bd.responder("sv.heartbeat", [(1,)])
    bd.responder("SELECT COUNT(DISTINCT", [(4,)])
    monkeypatch.setattr(stats, "_get_conn", lambda: bd)
    datos = cliente.get("/api/en-tienda").get_json()
    assert datos == {"en_vivo": True, "total": 4, "por_camara": {"2": 3, "4": 1},
                     "ventana_seg": stats.EN_TIENDA_VENTANA_SEG}
    # El total deja afuera las camaras 1 y 3 (miran el mismo mostrador que la 4), como el resto del dashboard.
    sql, params = next(c for c in bd.consultas if "SELECT COUNT(DISTINCT" in c[0] and "GROUP BY" not in c[0])
    assert "sv.camara_id NOT IN" in sql and params[0] == stats.CAMARAS_EXCLUIDAS_DE_CONTEO


def test_en_tienda_sin_bd(cliente, monkeypatch):
    monkeypatch.setattr(stats, "_get_conn", lambda: None)
    assert cliente.get("/api/en-tienda").get_json() == {"en_vivo": False, "total": None, "por_camara": {}}


def test_ahora_local_es_naive_en_hora_de_mendoza():
    assert stats._ahora_local().tzinfo is None


# ── /alertas ──────────────────────────────────────────────────────────────────

ALERTA = {"id": 5, "persona_id": 9, "tipo": "posible_hurto", "timestamp": datetime(2026, 10, 7, 15, 0, 30),
          "descripcion": "Tomó un producto y salió", "resuelta": False, "sesion_id": 3, "camara_id": 2,
          "sesion_inicio": datetime(2026, 10, 7, 15, 0, 0), "secuencia_zonas": ["gondola", "salida"],
          "evidencia": {"video": "clip.mp4", "frames": [{"url": "https://s/1.jpg", "ts": 1}]}}


def test_listar_alertas_arma_la_alerta_para_el_front(cliente, monkeypatch, bd):
    bd.responder("FROM alertas al", [ALERTA, {**ALERTA, "id": 6, "tipo": "nuevo_tipo", "secuencia_zonas": None,
                                             "sesion_inicio": None, "resuelta": True, "descripcion": None,
                                             "evidencia": None, "timestamp": datetime(2026, 10, 6)}])
    monkeypatch.setattr(alertas, "_get_conn", lambda: bd)
    lista = cliente.get("/api/alertas").get_json()
    hurto, otra = lista   # ordenadas de la mas nueva a la mas vieja
    assert (hurto["sev"], hurto["title"], hurto["zone"], hurto["status"]) == (
        "critical", "Actividad sospechosa detectada", "salida", "open")
    assert hurto["offset_seg"] == 22   # 30 s desde el inicio de la sesion - 8 s de margen del clip
    assert hurto["evidencia"]["video"] == "/api/evidencias/clip.mp4"
    assert hurto["video_disponible"] is False and otra["video_disponible"] is False   # sin archivo_path
    assert (otra["sev"], otra["title"], otra["zone"], otra["status"], otra["offset_seg"]) == (
        "info", "Alerta", "Desconocida", "resolved", 0)


def test_listar_alertas_avisa_si_el_video_original_esta_en_el_servidor(cliente, monkeypatch, bd, tmp_path):
    video = tmp_path / "cam1.mp4"
    video.write_bytes(b"mp4")
    bd.responder("FROM alertas al", [{**ALERTA, "archivo_path": str(video)},
                                     {**ALERTA, "id": 6, "archivo_path": r"D:\FACU 2026\Videos\D01.mp4"},
                                     {**ALERTA, "id": 7, "archivo_path": "rtsp://camara_1/20261007_190209"}])
    monkeypatch.setattr(alertas, "_get_conn", lambda: bd)
    disponible = {a["id"]: a["video_disponible"] for a in cliente.get("/api/alertas").get_json()}
    assert disponible == {5: True, 6: False, 7: False}


@pytest.mark.parametrize("conexion, esperado", [(None, 200), ("error", 500)])
def test_listar_alertas_sin_bd_o_con_error(cliente, monkeypatch, bd, conexion, esperado):
    bd.error = RuntimeError("caida")
    monkeypatch.setattr(alertas, "_get_conn", lambda: None if conexion is None else bd)
    assert cliente.get("/api/alertas").status_code == esperado


@pytest.mark.parametrize("rowcount, body, status, resuelta", [
    (1, {}, 200, True), (1, {"resuelta": False}, 200, False), (0, {}, 404, None)])
def test_resolver_alerta(cliente, monkeypatch, bd, rowcount, body, status, resuelta):
    bd.rowcount = rowcount
    monkeypatch.setattr(alertas, "_get_conn", lambda: bd)
    r = cliente.post("/api/alertas/5/resolver", json=body)
    assert r.status_code == status
    if resuelta is not None:
        assert r.get_json() == {"id": 5, "resuelta": resuelta}


def test_resolver_alerta_borra_su_evidencia_y_limpia_la_referencia(cliente, monkeypatch, bd):
    evidencia = {"video": "alerta_5/clip.mp4", "frames": [{"url": "alerta_5/frame_01.jpg"}]}
    bd.responder("SELECT evidencia FROM alertas", [(evidencia,)])
    borradas = []
    monkeypatch.setattr(alertas, "_get_conn", lambda: bd)
    monkeypatch.setattr(alertas, "borrar_archivos_evidencia", lambda ev: borradas.append(ev) or 2)
    r = cliente.post("/api/alertas/5/resolver", json={})
    assert r.get_json() == {"id": 5, "resuelta": True, "evidencia_borrada": 2}
    assert borradas == [evidencia]
    update = next(sql for sql, _ in bd.consultas if sql.startswith("UPDATE"))
    assert "evidencia = NULL" in update and bd.commits == 1   # la base queda sin la referencia


def test_reabrir_una_alerta_no_toca_la_evidencia(cliente, monkeypatch, bd):
    monkeypatch.setattr(alertas, "_get_conn", lambda: bd)
    monkeypatch.setattr(alertas, "borrar_archivos_evidencia", lambda ev: pytest.fail("no deberia borrar"))
    assert cliente.post("/api/alertas/5/resolver", json={"resuelta": False}).get_json() == {"id": 5, "resuelta": False}
    assert all("evidencia" not in sql for sql, _ in bd.consultas)


def test_resolver_alerta_que_no_existe_no_borra_nada(cliente, monkeypatch, bd):
    bd.rowcount = 0
    bd.responder("SELECT evidencia FROM alertas", [({"video": "x.mp4", "frames": []},)])
    monkeypatch.setattr(alertas, "_get_conn", lambda: bd)
    monkeypatch.setattr(alertas, "borrar_archivos_evidencia", lambda ev: pytest.fail("no deberia borrar"))
    assert cliente.post("/api/alertas/5/resolver", json={}).status_code == 404


@pytest.mark.parametrize("conexion, status", [(None, 503), ("error", 500)])
def test_resolver_alerta_sin_bd_o_con_error(cliente, monkeypatch, bd, conexion, status):
    bd.error = RuntimeError("caida")
    monkeypatch.setattr(alertas, "_get_conn", lambda: None if conexion is None else bd)
    assert cliente.post("/api/alertas/5/resolver", json={}).status_code == status


def test_servir_evidencia_local_y_ruta_inexistente(cliente, monkeypatch, tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(alertas, "EVIDENCIAS_DIR", str(tmp_path))
    assert cliente.get("/api/evidencias/a.jpg").data == b"jpg"
    assert cliente.get("/api/evidencias/no.jpg").status_code == 404
    assert cliente.get("/api/evidencias/../secreto.txt").status_code == 404   # no puede salir de la carpeta


# ── /leads ────────────────────────────────────────────────────────────────────

LEAD = {"nombre": "Ana", "contacto": "ana@x.com", "estacion": "YPF Centro", "camaras": "4", "problema": "colas"}


def test_lead_valido_se_guarda_recortado_con_utm(cliente, monkeypatch, tmp_path):
    archivo = tmp_path / "leads.jsonl"
    monkeypatch.setattr(leads, "LEADS_PATH", str(archivo))
    r = cliente.post("/api/leads", json={**LEAD, "nombre": "  " + "A" * 200, "utm_source": "instagram"})
    assert r.status_code == 201
    guardado = json.loads(archivo.read_text(encoding="utf-8"))
    assert len(guardado["nombre"]) == 120          # valor limite: se recorta al maximo
    assert guardado["utm_source"] == "instagram" and guardado["utm_medium"] == ""
    assert guardado["recibido"].endswith("+00:00")


@pytest.mark.parametrize("cambio, faltan", [
    ({"nombre": "   "}, ["nombre"]),
    ({"contacto": None, "camaras": ""}, ["contacto", "camaras"]),
    ({"problema": "precios"}, ["problema"]),    # fuera de las opciones validas
])
def test_lead_invalido_responde_400_con_lo_que_falta(cliente, monkeypatch, tmp_path, cambio, faltan):
    monkeypatch.setattr(leads, "LEADS_PATH", str(tmp_path / "leads.jsonl"))
    r = cliente.post("/api/leads", json={**LEAD, **cambio})
    assert r.status_code == 400
    assert r.get_json() == {"ok": False, "faltan": faltan}


# ── Frontend compilado (__init__.py) ──────────────────────────────────────────

def test_sin_build_del_frontend_responde_503_con_instrucciones(cliente, monkeypatch, tmp_path):
    monkeypatch.setattr(api, "DIST", str(tmp_path))
    for ruta in ("/", "/dashboard"):
        r = cliente.get(ruta)
        assert r.status_code == 503 and b"npm run build" in r.data


def test_con_build_sirve_archivos_y_cae_al_index_en_rutas_del_spa(cliente, monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(api, "DIST", str(tmp_path))
    assert b"root" in cliente.get("/").data
    assert cliente.get("/app.js").data == b"console.log(1)"
    assert b"root" in cliente.get("/reportes/ventas").data   # ruta del SPA: devuelve index.html


# ── Regresion DEF-008: base de datos vacia ───────────────────────────────────
# Con la base vacia (local nuevo, sin datos) cargar_db() devolvia None, que significa "BD caida":
# el endpoint caia al CSV de respaldo, que no existe, y respondia 500.

@pytest.fixture
def bd_vacia_sin_csv(monkeypatch, bd, tmp_path):
    from api import export
    monkeypatch.setattr(db, "_get_conn", lambda: bd)          # conecta, pero no hay filas
    monkeypatch.setattr(db, "CSV_PATH", str(tmp_path / "no_existe.csv"))
    for modulo in (stats, export):                             # usan las funciones reales de db.py
        monkeypatch.setattr(modulo, "cargar_db", db.cargar_db)
        monkeypatch.setattr(modulo, "cargar_csv", db.cargar_csv, raising=False)
    return bd


def test_personas_con_la_base_vacia_devuelve_lista_vacia(cliente, bd_vacia_sin_csv):
    r = cliente.get("/api/personas")
    assert r.status_code == 200
    assert r.get_json() == {"fuente": "db", "registros": []}


@pytest.mark.parametrize("formato, mime", [("csv", "text/csv"), ("pdf", "application/pdf")])
def test_exportar_con_la_base_vacia_genera_el_reporte_sin_filas(cliente, bd_vacia_sin_csv, formato, mime):
    r = cliente.get(f"/api/export/{formato}")
    assert r.status_code == 200 and r.mimetype == mime

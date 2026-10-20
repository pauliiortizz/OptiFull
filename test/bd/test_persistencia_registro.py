"""Persistencia contra Postgres real (1/2): conexion y reconexion, sesiones de video, personas, trayectorias,
visitas, eventos/alertas y mapas de calor -- lo que el pipeline de deteccion guarda mientras analiza."""
import json
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import CAJA, DESC, DESC_EMPLEADO, GONDOLA, HOY, URL
from deteccion.persistencia import Persistencia

pytestmark = pytest.mark.usefixtures("conn")


# ── Conexion ──────────────────────────────────────────────────────────────────

def test_sin_base_de_datos_todo_es_no_op():
    p = Persistencia(None, has_db=False, guardar_trayectorias=True, camara_nombres={})
    assert p.conectar() is False and p.asegurar_conexion() is False
    assert p.cargar_zonas(1) == [] and p.crear_sesion(1, HOY, "a.mp4") is None
    assert p.crear_persona(1, 1, 0, 30, HOY, "nuevo") is None
    assert p.guardar_trayectorias_parcial([{"sid": 1}], 30, HOY) == -1
    assert p.limpiar_trayectorias_fuera_de_zona() == 0 and p.auditar_sesion(1, 1) == {}


def test_url_invalida_no_conecta(capsys):
    p = Persistencia("postgresql://u:p@127.0.0.1:1/x", has_db=True, guardar_trayectorias=True, camara_nombres={})
    assert p.conectar() is False and p.conn is None
    assert "No se pudo conectar" in capsys.readouterr().out


def test_reconexion_automatica_limitada_en_frecuencia(monkeypatch):
    p = Persistencia(URL, has_db=True, guardar_trayectorias=True, camara_nombres={})
    assert p.asegurar_conexion() is False                 # apagada por defecto (modos sin persistencia)
    p.reconectar_automaticamente = True
    assert p.asegurar_conexion() is True                  # primer intento: conecta
    p.cerrar()
    assert p.asegurar_conexion() is False                 # recien se intento: espera el intervalo minimo
    assert p.asegurar_conexion(forzar=True) is True
    p.cerrar()


def test_si_la_conexion_se_cae_a_mitad_del_analisis_reconecta_y_reintenta(db, datos, capsys):
    datos.camara(2)
    datos.zona(2, "caja", CAJA)
    db.conn.close()                                       # corte de red: la conexion queda muerta
    assert len(db.cargar_zonas(2)) == 1
    assert "intentando reconectar" in capsys.readouterr().out


def test_si_no_puede_reconectar_devuelve_el_valor_por_defecto(db, capsys):
    db.conn.close()
    db.database_url = "postgresql://u:p@127.0.0.1:1/x"
    assert db.cargar_zonas(2) == []
    assert "No se pudo reconectar" in capsys.readouterr().out


# ── Sesiones de video ─────────────────────────────────────────────────────────

def test_crear_sesion_da_de_alta_la_camara_si_no_existe(db, datos, tmp_path):
    video = tmp_path / "D02_20261007100000.mp4"
    sid = db.crear_sesion(2, HOY, str(video))
    assert datos.filas("SELECT id, nombre, ubicacion FROM camaras") == [(2, "Salon", "Frente del local")]
    assert datos.valor("SELECT archivo_path FROM sesiones_video WHERE id = %s", (sid,)) == str(video.resolve())
    db.crear_sesion(2, HOY, "rtsp://usuario:clave@camara/1")    # la camara ya existe: no se duplica
    assert datos.valor("SELECT count(*) FROM camaras") == 1
    assert datos.valor("SELECT archivo_path FROM sesiones_video ORDER BY id DESC LIMIT 1").startswith("rtsp://")


def test_camara_sin_nombre_configurado_recibe_uno_generico(db, datos):
    db.crear_sesion(7, HOY, "rtsp://x")
    assert datos.valor("SELECT nombre FROM camaras WHERE id = 7") == "Camara 07"


def test_video_ya_analizado_se_reconoce_por_nombre_de_archivo_aunque_cambie_la_carpeta(db, datos):
    datos.camara(2)
    datos.sesion(2, archivo="D:/videos/D02_20261007100000.mp4")
    encontrada = db.buscar_sesion_por_archivo("E:\\otra\\carpeta\\D02_20261007100000.mp4".replace("\\", "/"))
    assert encontrada["camara_id"] == 2
    assert db.buscar_sesion_por_archivo("D02_otro.mp4") is None


def test_resolucion_heartbeat_y_cierre_de_la_sesion(db, datos):
    datos.camara(2)
    sid = datos.sesion(2)
    db.actualizar_resolucion_sesion(sid, 640, 360)
    db.actualizar_heartbeat(sid)
    db.cerrar_sesion(sid, HOY + timedelta(hours=1))
    w, h, latido, fin = datos.filas("SELECT frame_w, frame_h, heartbeat, fin FROM sesiones_video")[0]
    assert (w, h, fin) == (640, 360, HOY + timedelta(hours=1)) and latido is not None
    db.actualizar_heartbeat(None)   # sin sesion: no hace nada


# ── Personas ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sesion(datos):
    datos.camara(2)
    return datos.sesion(2)


def test_crear_persona_es_su_propio_cliente_y_no_se_duplica(db, datos, sesion):
    pid = db.crear_persona(sesion, sid=1, frame_num=300, fps=30, inicio=HOY, metodo_reid="nuevo")
    assert db.crear_persona(sesion, sid=1, frame_num=600, fps=30, inicio=HOY, metodo_reid="nuevo") == pid
    assert datos.filas("SELECT cliente_id, primera_deteccion FROM personas") == [(pid, HOY + timedelta(seconds=10))]


def test_persona_reconocida_de_otro_video_apunta_a_ese_cliente(db, datos, sesion):
    otro = datos.persona(sesion)
    pid = db.crear_persona(sesion, sid=2, frame_num=0, fps=30, inicio=HOY, metodo_reid="gemini", cliente_id_hint=otro)
    assert datos.persona_campo(pid, "cliente_id") == otro


def test_guardar_descripcion_inserta_o_actualiza(db, datos, sesion):
    pid = db.guardar_descripcion_persona(sesion, sid=1, frame_num=30, fps=30, inicio=HOY, metodo_reid="groq",
                                         descripcion=DESC)
    assert json.loads(datos.persona_campo(pid, "descripcion_visual")) == DESC
    assert datos.persona_campo(pid, "cliente_id") == pid
    otra = {**DESC, "accesorios": "mochila"}
    assert db.guardar_descripcion_persona(sesion, 1, 90, 30, HOY, "groq", otra) == pid
    assert json.loads(datos.persona_campo(pid, "descripcion_visual"))["accesorios"] == "mochila"
    assert datos.persona_campo(pid, "ultima_deteccion") == HOY + timedelta(seconds=3)


def test_al_reconocer_a_un_empleado_la_aparicion_nueva_hereda_el_flag(db, datos, sesion):
    empleado = datos.persona(sesion, desc=DESC_EMPLEADO, es_empleado=True)
    cliente = datos.persona(sesion, desc=DESC)
    pid = db.guardar_descripcion_persona(sesion, 5, 0, 30, HOY, "claude", DESC_EMPLEADO, cliente_id_hint=empleado)
    assert datos.persona_campo(pid, "es_empleado") is True and datos.persona_campo(pid, "cliente_id") == empleado
    pid2 = db.guardar_descripcion_persona(sesion, 6, 0, 30, HOY, "claude", DESC, cliente_id_hint=cliente)
    assert datos.persona_campo(pid2, "es_empleado") is False


def test_candidatos_de_reid_solo_del_mismo_grupo_de_camaras_y_cerca_en_el_tiempo(db, datos):
    for cam in (1, 2, 4):
        datos.camara(cam)
    s1, s2, s4 = datos.sesion(1), datos.sesion(2), datos.sesion(4)
    mismo_grupo = datos.persona(s4, inicio=HOY + timedelta(minutes=10), desc=DESC)
    datos.persona(s2, inicio=HOY, desc=DESC)                           # otra camara, otro espacio fisico
    datos.persona(s1, inicio=HOY + timedelta(hours=3), desc=DESC)      # fuera de la ventana de 1 h
    datos.persona(s1, inicio=HOY, desc=None)                           # sin descripcion
    excluida = datos.persona(s1, inicio=HOY, desc=DESC)                # activa en este momento
    datos.valor("UPDATE personas SET descripcion_visual = 'no es json' WHERE id = "
                "(SELECT max(id) FROM personas WHERE sesion_id = %s AND descripcion_visual IS NULL) RETURNING id", (s1,))
    candidatos = db.candidatos_reid_del_dia(HOY, camara_id=1, excluir_ids={excluida})
    assert [c["persona_id"] for c in candidatos] == [mismo_grupo]
    assert candidatos[0]["descripcion"] == DESC and candidatos[0]["cliente_id"] == mismo_grupo


def test_guardar_personas_al_final_actualiza_las_creadas_y_rescata_las_que_faltaban(db, datos, sesion):
    empleado = datos.persona(sesion, es_empleado=True)
    creada = db.crear_persona(sesion, 1, 0, 30, HOY, "nuevo")
    rows = [
        {"id": 1, "_first_frame": 0, "_last_frame": 900, "metodo_reid": "posicion"},
        {"id": 2, "_first_frame": 30, "_last_frame": 60, "metodo_reid": "gemini", "descripcion": DESC,
         "cliente_id_hint": empleado},
    ]
    db.persona_db_ids[1] = creada
    trayectoria = [{"sid": 1, "frame": 30, "zona_id": None, "cx": 10, "cy": 20, "box": (0, 0, 20, 20)}]
    db.guardar_personas(sesion, rows, trayectoria, 30, HOY, camara_id=2)
    assert datos.persona_campo(creada, "ultima_deteccion") == HOY + timedelta(seconds=30)
    rescatada = db.persona_db_ids[2]
    assert datos.persona_campo(rescatada, "cliente_id") == empleado
    assert datos.persona_campo(rescatada, "es_empleado") is True      # hereda de la persona reconocida
    assert datos.valor("SELECT count(*) FROM trayectorias") == 1      # se vacio el buffer pendiente


# ── Trayectorias, visitas y eventos ───────────────────────────────────────────

def test_trayectorias_en_bloque_con_el_flag_de_empleado_de_toda_la_cadena(db, datos, sesion):
    zona = datos.zona(2, "gondola", GONDOLA)
    empleado = datos.persona(sesion, es_empleado=True)
    db.persona_db_ids = {1: datos.persona(sesion), 2: datos.persona(sesion, cliente_id=empleado)}
    puntos = [{"sid": 1, "frame": 30, "zona_id": zona, "cx": 10.123, "cy": 20, "box": (0, 0, 20, 20)},
              {"sid": 2, "frame": 60, "zona_id": None, "cx": 30, "cy": 40, "box": (20, 20, 40, 40)},
              {"sid": 9, "frame": 90, "zona_id": None, "cx": 0, "cy": 0, "box": (0, 0, 1, 1)}]   # sid sin persona
    assert db.guardar_trayectorias_parcial(puntos, 30, HOY, camara_id=2) == 2
    assert datos.filas("SELECT camara_id, es_empleado, centroide_x, timestamp FROM trayectorias ORDER BY id") == [
        (2, False, 10.12, HOY + timedelta(seconds=1)), (2, True, 30.0, HOY + timedelta(seconds=2))]
    assert db.guardar_trayectorias_parcial([], 30, HOY) == 0
    assert db.guardar_trayectorias_parcial([puntos[2]], 30, HOY) == 0


def test_visita_y_evento_normal(db, datos, sesion):
    pid = datos.persona(sesion)
    vid = db.guardar_visita(pid, frame_inicio=0, frame_fin=300, fps=30, inicio=HOY)
    assert datos.filas("SELECT entrada, salida FROM visitas") == [(HOY, HOY + timedelta(seconds=10))]
    evento = {"accion_detectada": "COMPRA_NORMAL", "tomo_producto": True, "paso_por_caja": True,
              "es_sospechoso": False, "secuencia_zonas_recorridas": ["Góndola", "Caja"]}
    db.guardar_evento(pid, vid, evento, 300, 30, HOY)
    assert datos.filas("SELECT accion_detectada, secuencia_zonas FROM eventos") == [("COMPRA_NORMAL", ["Góndola", "Caja"])]
    assert datos.valor("SELECT count(*) FROM alertas") == 0
    assert db.guardar_visita(None, 0, 1, 30, HOY) is None   # persona nunca confirmada: se descarta
    db.guardar_evento(None, None, evento, 1, 30, HOY)


def test_evento_sospechoso_crea_una_alerta_y_dispara_la_subida_de_evidencia(db, datos, sesion):
    pid = datos.persona(sesion)
    subidas = []
    db.on_alerta_creada = lambda alerta_id, evidencia: subidas.append((alerta_id, evidencia))
    evento = {"accion_detectada": "POSIBLE_HURTO", "tomo_producto": True, "paso_por_caja": False,
              "es_sospechoso": True, "secuencia_zonas_recorridas": ["Góndola", "Salida"]}
    db.guardar_evento(pid, None, evento, 300, 30, HOY, evidencia={"frames": [1]})
    alerta_id, tipo, descripcion = datos.filas("SELECT id, tipo, descripcion FROM alertas")[0]
    assert tipo == "posible_hurto" and descripcion
    assert subidas == [(alerta_id, {"frames": [1]})]


def test_limpiar_eventos_de_empleados_borra_sus_eventos_y_alertas(db, datos, sesion):
    empleado = datos.persona(sesion, es_empleado=True)
    hijo = datos.persona(sesion, cliente_id=empleado)          # la cadena es de un empleado
    cliente = datos.persona(sesion)
    evento = {"accion_detectada": "POSIBLE_HURTO", "tomo_producto": True, "paso_por_caja": False,
              "es_sospechoso": True, "secuencia_zonas_recorridas": []}
    for pid in (hijo, cliente):
        db.guardar_evento(pid, None, evento, 0, 30, HOY)
    assert db.limpiar_eventos_de_empleados(sesion) == 1
    assert datos.filas("SELECT persona_id FROM eventos") == [(cliente,)]
    assert datos.filas("SELECT persona_id FROM alertas") == [(cliente,)]
    assert db.limpiar_eventos_de_empleados(None) == 0


# ── Mapas de calor ────────────────────────────────────────────────────────────

STATS = {"matriz_json": json.dumps([[0.0, 1.0], [0.5, 0.0]]), "resolucion": 2, "punto_max_x": 10, "punto_max_y": 20,
         "valor_maximo": 4.0, "area_activa_pct": 12.5, "concentracion": 0.6, "zona_id_mas_caliente": None}


def test_heatmap_de_sesion_se_actualiza_si_se_reanaliza_el_mismo_periodo(db, datos, sesion):
    id1 = db.guardar_heatmap(2, sesion, HOY, HOY + timedelta(hours=1), STATS, "a.png", 100, 900)
    id2 = db.guardar_heatmap(2, sesion, HOY, HOY + timedelta(hours=1), {**STATS, "valor_maximo": 9.0}, "b.png", 200, 900)
    assert id1 == id2 and datos.valor("SELECT count(*) FROM mapas_calor") == 1
    assert datos.filas("SELECT imagen_path, valor_maximo, total_detecciones FROM mapas_calor") == [("b.png", 9.0, 200)]
    db.guardar_heatmap(2, sesion, HOY + timedelta(days=1), HOY + timedelta(days=1, hours=1), STATS, "c.png", 1, 1)
    matrices = db.obtener_matrices_camara(2)
    assert [m["valor_maximo"] for m in matrices] == [9.0, 4.0] and matrices[0]["resolucion_x"] == 2


def test_heatmap_combinado_de_la_camara_es_un_upsert(db, datos, sesion):
    assert db.guardar_heatmap_camara(2, STATS, "comb.png", 300, 1800, sesiones_combinadas=2) == 2
    db.guardar_heatmap_camara(2, {**STATS, "punto_max_x": 99}, "comb2.png", 400, 2700, sesiones_combinadas=3)
    assert datos.filas("SELECT imagen_path, punto_max_x, sesiones_combinadas FROM mapas_calor_camara") == [
        ("comb2.png", 99, 3)]


def test_cargar_zonas_de_una_camara(db, datos):
    datos.camara(2)
    datos.camara(3)
    z = datos.zona(2, "caja", CAJA, nombre="Caja 1")
    datos.zona(3, "otro", CAJA)
    assert db.cargar_zonas(2) == [{"id": z, "nombre": "Caja 1", "tipo": "caja", "poligono": CAJA}]


def test_el_archivo_de_la_sesion_se_guarda_con_ruta_absoluta(db, datos, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db.crear_sesion(2, HOY, "relativo.mp4")
    assert Path(datos.valor("SELECT archivo_path FROM sesiones_video")).is_absolute()

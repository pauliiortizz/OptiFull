"""Persistencia contra Postgres real (2/2): reglas de empleados y zonas, backfill de compras, fusiones de la
misma persona entre camaras y entre videos consecutivos, y limpiezas -- las correcciones que corren al terminar
cada video (y los scripts de mantenimiento)."""
import json
from datetime import timedelta

import psycopg2
import pytest

from conftest import CAJA, DESC, DESC_EMPLEADO, GONDOLA, HOY, URL
from deteccion.persistencia import Persistencia, _decidir_continuidad_temporal

pytestmark = pytest.mark.usefixtures("conn")

FECHA = HOY.date()


@pytest.fixture
def local(datos):
    """Camara 2 con una zona de caja y una de gondolas, y una sesion de hoy."""
    datos.camara(2)
    caja = datos.zona(2, "caja", CAJA)
    gondola = datos.zona(2, "gondola", GONDOLA)
    return {"caja": caja, "gondola": gondola, "sesion": datos.sesion(2)}


# ── Decision de continuidad entre dos videos ──────────────────────────────────

@pytest.mark.parametrize("nueva, delta, coincide, confianza", [
    (DESC, 5, True, "Alta"),                                       # mismo instante del corte
    (DESC, 40, True, "Media"),                                     # dentro de la ventana
    (DESC, 70, False, None),                                       # fuera de la ventana de 60 s
    ({**DESC, "color_ropa_superior": "verde"}, 5, False, None),    # ropa distinta: otra persona
    ({c: "no visible" for c in DESC}, 5, False, None),             # nada visible en comun: sin evidencia
])
def test_decidir_continuidad_temporal(nueva, delta, coincide, confianza):
    d = _decidir_continuidad_temporal(DESC, nueva, delta, umbral_seg=60, umbral_alta_confianza_seg=15)
    assert (d["es_coincidencia"], d["confianza"]) == (coincide, confianza) and d["justificacion"]


# ── Empleados y zonas ─────────────────────────────────────────────────────────

def test_limpiar_trayectorias_que_contradicen_la_zona(db, datos, local):
    empleado = datos.persona(local["sesion"], es_empleado=True)
    hijo_de_empleado = datos.persona(local["sesion"], cliente_id=empleado)
    cliente = datos.persona(local["sesion"])
    borrar = [datos.punto(cliente, local["caja"]), datos.punto(hijo_de_empleado, local["gondola"])]
    quedan = [datos.punto(cliente, local["gondola"]), datos.punto(empleado, local["caja"]), datos.punto(cliente)]
    assert db.limpiar_trayectorias_fuera_de_zona() == 2
    assert sorted(r[0] for r in datos.filas("SELECT id FROM trayectorias")) == sorted(quedan)
    assert not set(borrar) & {r[0] for r in datos.filas("SELECT id FROM trayectorias")}


def test_completar_camara_de_las_trayectorias(db, datos, local):
    pid = datos.persona(local["sesion"])
    datos.punto(pid)
    datos.punto(pid, camara_id=2)
    assert db.completar_camara_id_trayectorias() == 1
    assert datos.filas("SELECT DISTINCT camara_id FROM trayectorias") == [(2,)]


def test_sincronizar_flag_de_empleado_en_trayectorias(db, datos, local):
    empleado = datos.persona(local["sesion"], es_empleado=True)
    hijo = datos.persona(local["sesion"], cliente_id=empleado)
    otro = datos.persona(local["sesion"])
    for pid in (empleado, hijo, otro):
        datos.punto(pid)
    assert db.sincronizar_es_empleado_trayectorias(cliente_id=otro) == 0
    assert db.sincronizar_es_empleado_trayectorias(sesion_id=local["sesion"]) == 2
    assert db.sincronizar_es_empleado_trayectorias() == 0                   # ya sincronizado
    assert datos.filas("SELECT persona_id FROM trayectorias WHERE es_empleado ORDER BY 1") == [(empleado,), (hijo,)]


def test_poblar_empleados_una_sola_vez_con_sus_descripciones_distintas(db, datos, local):
    a = datos.persona(local["sesion"], desc=DESC_EMPLEADO, es_empleado=True)
    datos.persona(local["sesion"], desc=DESC_EMPLEADO, es_empleado=True, cliente_id=a)          # repetida
    datos.persona(local["sesion"], desc={**DESC_EMPLEADO, "accesorios": "no visible"}, es_empleado=True, cliente_id=a)
    b = datos.persona(local["sesion"], desc=DESC, es_empleado=True)
    assert db.poblar_empleados_desde_personas({a: "Agos"}) == {"empleados": 2, "descripciones": 3}
    assert datos.filas("SELECT nombre FROM empleados ORDER BY id") == [("Agos",), (f"Empleado {b}",)]
    assert db.poblar_empleados_desde_personas({}) == {"ya_poblado": True}


def test_marcar_empleados_en_zona_caja(db, datos, local):
    conocido = datos.persona(local["sesion"], desc=DESC_EMPLEADO, es_empleado=True)
    referencia = {**DESC_EMPLEADO, "color_ropa_superior": "naranja", "color_ropa_inferior": "gris"}
    eid = datos.empleado("Arnon", [referencia])
    como_conocido = datos.persona(local["sesion"], desc=DESC_EMPLEADO)
    como_referencia = datos.persona(local["sesion"], desc=referencia)
    sin_desc = datos.persona(local["sesion"])
    cliente = datos.persona(local["sesion"], desc=DESC)
    for pid in (como_conocido, como_referencia, sin_desc, cliente):
        datos.punto(pid, local["caja"])
    assert db.marcar_empleados_en_zona_caja([local["caja"]]) == {"evaluados": 4, "marcados": 2, "sin_descripcion": 1}
    assert datos.persona_campo(como_conocido, "cliente_id") == conocido          # se fusiona a la cadena real
    assert (datos.persona_campo(como_referencia, "es_empleado"), datos.persona_campo(como_referencia, "empleado_id"),
            datos.persona_campo(como_referencia, "cliente_id")) == (True, eid, como_referencia)
    assert datos.persona_campo(cliente, "es_empleado") is False
    assert db.marcar_empleados_en_zona_caja([999]) == {"evaluados": 0, "marcados": 0, "sin_descripcion": 0}


def test_consolidar_cadenas_de_empleados(db, datos, local):
    eid = datos.empleado("Pau")
    raiz = datos.persona(local["sesion"], es_empleado=True, empleado_id=eid)
    suelta = datos.persona(local["sesion"], es_empleado=True, empleado_id=eid)        # su propia cadena
    sin_id = datos.persona(local["sesion"], es_empleado=True, cliente_id=raiz)
    assert db.consolidar_cadenas_empleados({eid: raiz}) == {"reapuntadas": 1, "empleado_id_completado": 1}
    assert datos.persona_campo(suelta, "cliente_id") == raiz
    assert datos.persona_campo(sin_id, "empleado_id") == eid


def test_forzar_empleado_en_zona_caja_por_match_por_similitud_y_sin_descripcion(db, datos, local):
    eid = datos.empleado("Agos")
    raiz = datos.persona(local["sesion"], desc=DESC_EMPLEADO, es_empleado=True, empleado_id=eid)
    match = datos.persona(local["sesion"], desc=DESC_EMPLEADO)
    parecido = datos.persona(local["sesion"], desc={**DESC_EMPLEADO, "color_ropa_superior": "azul"})
    sin_desc = datos.persona(local["sesion"])
    for pid in (raiz, match, parecido, sin_desc):
        datos.punto(pid, local["caja"])
    resumen = db.forzar_empleado_zona_caja(sesion_id=local["sesion"])
    assert resumen == {"fusionadas_por_match": 1, "fusionadas_por_similitud": 1, "sin_descripcion": 1, "total": 3}
    for pid in (match, parecido, sin_desc):
        assert (datos.persona_campo(pid, "es_empleado"), datos.persona_campo(pid, "cliente_id")) == (True, raiz)
    assert datos.valor("SELECT count(*) FROM empleados_descripciones WHERE empleado_id = %s", (eid,)) == 1


def test_forzar_empleado_sin_zonas_de_caja_o_sin_empleados_no_hace_nada(db, datos, capsys):
    datos.camara(2)
    assert db.forzar_empleado_zona_caja()["total"] == 0                          # no hay zonas de caja
    caja = datos.zona(2, "caja", CAJA)
    datos.punto(datos.persona(datos.sesion(2), desc=DESC), caja)
    assert db.forzar_empleado_zona_caja()["total"] == 0                          # no hay empleados definidos
    assert "no hay ningun 'empleado' definido" in capsys.readouterr().out


def test_reclasificar_por_mayoria_de_puntos(db, datos, local):
    eid = datos.empleado("Agos")
    raiz = datos.persona(local["sesion"], desc=DESC_EMPLEADO, es_empleado=True, empleado_id=eid)
    atiende = datos.persona(local["sesion"], desc=DESC_EMPLEADO)                 # 3 en caja, 1 en gondola
    for _ in range(3):
        datos.punto(atiende, local["caja"])
    datos.punto(atiende, local["gondola"])
    mal_marcado = datos.persona(local["sesion"], desc=DESC, es_empleado=True, empleado_id=eid, cliente_id=raiz)
    datos.punto(mal_marcado, local["caja"])                                      # paso a pagar
    for _ in range(2):
        datos.punto(mal_marcado, local["gondola"])
    empate = datos.persona(local["sesion"], desc=DESC)
    datos.punto(empate, local["caja"])
    datos.punto(empate, local["gondola"])
    resumen = db.reclasificar_por_mayoria_zona(sesion_id=local["sesion"])
    assert resumen == {"a_empleado": 1, "a_cliente": 2, "puntos_borrados": 3}
    assert (datos.persona_campo(atiende, "es_empleado"), datos.persona_campo(atiende, "cliente_id")) == (True, raiz)
    assert (datos.persona_campo(mal_marcado, "es_empleado"), datos.persona_campo(mal_marcado, "cliente_id"),
            datos.persona_campo(mal_marcado, "empleado_id")) == (False, mal_marcado, None)
    assert datos.persona_campo(empate, "es_empleado") is False                  # empate: cliente
    assert db.reclasificar_por_mayoria_zona(sesion_id=9999) == {"a_empleado": 0, "a_cliente": 0, "puntos_borrados": 0}


def test_recalcular_zona_con_la_base_del_box(db, datos, local):
    pid = datos.persona(local["sesion"])
    # centro a la altura del pecho (dentro de la caja), pero los pies en la gondola
    tid = datos.punto(pid, local["caja"], x=200, y=200, bbox=(1100, 200, 1300, 900))
    assert db.recalcular_zonas_por_pie() == {2: 1}
    assert datos.filas("SELECT centroide_x, centroide_y, zona_id FROM trayectorias WHERE id = %s", (tid,)) == [
        (1200.0, 900.0, local["gondola"])]
    assert db.recalcular_zona_dominante_personas() == 1
    assert datos.persona_campo(pid, "zona_id") == local["gondola"]


def test_backfill_de_compras_desde_trayectorias(db, datos, local):
    empleado = datos.persona(local["sesion"], es_empleado=True)
    datos.punto(empleado, local["caja"], ts=HOY, x=200, y=200, es_empleado=True)
    compra = datos.persona(local["sesion"])
    datos.punto(compra, local["gondola"], ts=HOY - timedelta(minutes=2), x=1500, y=500)
    for s in (10, 20):                                                    # 2 muestras seguidas cerca de la caja
        datos.punto(compra, None, ts=HOY + timedelta(seconds=s), x=450, y=200)
    pasa_lejos = datos.persona(local["sesion"])
    datos.punto(pasa_lejos, None, ts=HOY + timedelta(minutes=10), x=450, y=200)   # cerca, pero sin empleado al lado
    datos.punto(pasa_lejos, None, ts=HOY + timedelta(minutes=10, seconds=10), x=450, y=200)
    ya_tenia = datos.persona(local["sesion"])
    datos.punto(ya_tenia, local["gondola"], x=1500, y=500)
    datos.valor("INSERT INTO eventos (persona_id, accion_detectada) VALUES (%s, 'COMPRA_NORMAL') RETURNING id", (ya_tenia,))
    resumen = db.analizar_compras_retroactivo(caja_muestras_minimas=2, ventana_empleado_seg=60)
    assert resumen == {"evaluadas": 2, "compra_normal": 1, "transito_sin_compra": 1, "saltadas_ya_tenian_evento": 1}
    assert datos.filas("SELECT accion_detectada, secuencia_zonas FROM eventos WHERE persona_id = %s", (compra,)) == [
        ("COMPRA_NORMAL", ["gondola"])]
    assert db.analizar_compras_retroactivo()["evaluadas"] == 0                      # idempotente


# ── Fusiones de la misma persona ──────────────────────────────────────────────

def test_continuidad_entre_dos_videos_consecutivos_de_la_misma_camara(db, datos):
    datos.camara(2)
    s1 = datos.sesion(2, inicio=HOY, fin=HOY + timedelta(hours=1))
    s2 = datos.sesion(2, inicio=HOY + timedelta(hours=1), fin=HOY + timedelta(hours=2))
    corte = HOY + timedelta(hours=1)
    sigue = datos.persona(s1, inicio=corte - timedelta(minutes=5), dur_seg=295, desc=DESC)     # hasta 5 s antes
    reaparece = datos.persona(s2, inicio=corte + timedelta(seconds=3), desc=DESC)
    otra = datos.persona(s1, inicio=corte - timedelta(minutes=5), dur_seg=298, desc={**DESC, "color_ropa_superior": "verde"})
    assert db.fusionar_continuidad_sesiones(FECHA + timedelta(days=0), umbral_seg=60) == 1
    assert datos.persona_campo(reaparece, "cliente_id") == sigue
    assert datos.persona_campo(otra, "cliente_id") == otra


@pytest.fixture
def grupo_caja(datos):
    """Camaras 1 y 4 miran el mismo lugar (mismo grupo fisico)."""
    datos.camara(1)
    datos.camara(4)
    return datos.sesion(1), datos.sesion(4)


def test_fusion_cross_camara_del_dia(db, datos, grupo_caja):
    s1, s4 = grupo_caja
    a = datos.persona(s1, inicio=HOY, desc=DESC)
    misma = datos.persona(s4, inicio=HOY + timedelta(seconds=30), desc=DESC)
    datos.persona(s1, inicio=HOY + timedelta(seconds=20), desc=DESC)                        # misma camara: no
    tarde = datos.persona(s4, inicio=HOY + timedelta(minutes=30), desc=DESC)                # fuera de la ventana
    resumen = db.fusionar_cross_camara_dia(FECHA, umbral_mismo_momento_seg=90)
    assert resumen[(1, 3, 4)] == 1 and resumen[(2,)] == 0
    assert datos.persona_campo(misma, "cliente_id") == a
    assert datos.persona_campo(tarde, "cliente_id") == tarde


def test_la_misma_zona_relaja_el_minimo_de_coincidencias(db, datos, grupo_caja):
    s1, s4 = grupo_caja
    zona1, zona4 = datos.zona(1, "gondola", GONDOLA), datos.zona(4, "gondola", GONDOLA)
    a = datos.persona(s1, inicio=HOY, desc=DESC)
    b = datos.persona(s4, inicio=HOY + timedelta(seconds=10),
                      desc={**DESC, "complexion": "robusta", "cabello": "largo claro", "accesorios": "mochila"})
    datos.punto(a, zona1, ts=HOY)
    datos.punto(b, zona4, ts=HOY + timedelta(seconds=10))
    # 2 de 5 coinciden: con el minimo de 3 no alcanza, pero estar en el mismo tipo de zona lo baja a 2
    assert sum(db.fusionar_cross_camara_dia(FECHA, coincidencias_minimas=3).values()) == 1
    assert datos.persona_campo(b, "cliente_id") == a


def test_fusion_en_vivo_respeta_el_candado_entre_pcs(db, datos, grupo_caja):
    s1, s4 = grupo_caja
    datos.persona(s1, inicio=HOY, desc=DESC)
    datos.persona(s4, inicio=HOY + timedelta(seconds=30), desc=DESC)
    otra_pc = psycopg2.connect(URL)
    cur = otra_pc.cursor()
    cur.execute("SELECT pg_advisory_lock(%s)", (Persistencia.LOCK_FUSION_EN_VIVO,))
    assert db.fusionar_en_vivo(FECHA) == 0                     # otra PC esta fusionando: se saltea
    cur.execute("SELECT pg_advisory_unlock(%s)", (Persistencia.LOCK_FUSION_EN_VIVO,))
    otra_pc.close()
    assert db.fusionar_en_vivo(FECHA) == 1


def test_fusionar_el_dia_hasta_que_no_haya_mas_cambios(db, datos, grupo_caja):
    s1, s4 = grupo_caja
    datos.persona(s1, inicio=HOY, desc=DESC)
    datos.persona(s4, inicio=HOY + timedelta(seconds=30), desc=DESC)
    resultado = db.fusionar_dia_hasta_converger(FECHA)
    assert resultado == {"continuidad": 0, "cross_camara": 1, "pasadas": 2}


def test_auditoria_al_terminar_un_video(db, datos, grupo_caja):
    s1, s4 = grupo_caja
    zona = datos.zona(1, "caja", CAJA)
    a = datos.persona(s1, inicio=HOY, desc=DESC)
    b = datos.persona(s4, inicio=HOY + timedelta(seconds=20), desc=DESC)
    for _ in range(2):
        datos.punto(a, zona)
    datos.punto(a)
    assert db.auditar_sesion(s1, camara_id=1) == {"fusiones_cross_camara": 1}
    assert datos.persona_campo(a, "zona_id") == zona
    assert datos.persona_campo(b, "cliente_id") == a
    assert db.auditar_sesion(None, 1) == {}


# ── Limpiezas ─────────────────────────────────────────────────────────────────

def test_borrar_detecciones_espurias(db, datos, local):
    ruido = datos.persona(local["sesion"], dur_seg=1)
    con_dependientes = datos.persona(local["sesion"], dur_seg=1)
    datos.persona(local["sesion"], dur_seg=60, cliente_id=con_dependientes)
    empleado = datos.persona(local["sesion"], dur_seg=1, es_empleado=True)
    real = datos.persona(local["sesion"], dur_seg=60)
    assert db.limpiar_detecciones_espurias(FECHA, duracion_min_seg=2) == 1
    restantes = {r[0] for r in datos.filas("SELECT id FROM personas")}
    assert ruido not in restantes and {con_dependientes, empleado, real} <= restantes


@pytest.mark.parametrize("por_fecha", [True, False])
def test_borrar_sin_descripcion_reapunta_la_cadena_a_un_miembro_descrito(db, datos, local, por_fecha):
    raiz = datos.persona(local["sesion"])                                # sin descripcion, con dependientes
    descrito = datos.persona(local["sesion"], desc=DESC, cliente_id=raiz)
    otro = datos.persona(local["sesion"], desc=DESC, cliente_id=raiz)
    assert db.borrar_sin_descripcion(FECHA if por_fecha else None) == 1
    assert datos.persona_campo(otro, "cliente_id") == descrito
    assert {r[0] for r in datos.filas("SELECT id FROM personas")} == {descrito, otro}
    assert json.loads(datos.persona_campo(descrito, "descripcion_visual")) == DESC

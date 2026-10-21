"""Pool de conexiones de la API (frontend/api/db.py) contra un Postgres real.

Cada pedido usa una conexion prestada en vez de abrir una nueva (abrirla contra Supabase cuesta ~1,3 s y, en Render
gratuito, CPU que necesitan los demas pedidos). Los endpoints siguen llamando a conn.close(): eso la devuelve al pool.
"""
import gc

import pytest

from conftest import URL

from api import db


@pytest.fixture
def pool_nuevo(conn, monkeypatch):
    """Pool vacio apuntando a la base de prueba (conn: la fixture que exige TEST_DATABASE_URL)."""
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "_pool_url", None)
    yield
    if db._pool is not None:
        db._pool.closeall()


def pid(c):
    cur = c.cursor()
    cur.execute("SELECT pg_backend_pid()")
    n = cur.fetchone()[0]
    cur.close()
    return n


def test_close_devuelve_la_conexion_y_el_siguiente_pedido_la_reusa(pool_nuevo):
    a = db._get_conn()
    primera = pid(a)
    a.close()
    b = db._get_conn()
    assert pid(b) == primera            # la misma sesion de Postgres: no se abrio otra
    b.close()


def test_pedidos_simultaneos_usan_conexiones_distintas(pool_nuevo):
    conexiones = [db._get_conn() for _ in range(db.POOL_MAX)]
    assert len({pid(c) for c in conexiones}) == db.POOL_MAX
    for c in conexiones:
        c.close()


def test_lo_que_quedo_sin_commit_no_pasa_al_siguiente_pedido(pool_nuevo, conn):
    a = db._get_conn()
    cur = a.cursor()
    cur.execute("INSERT INTO camaras (id, nombre, rtsp_url) VALUES (99, 'sin commit', 'rtsp://x')")
    a.close()                            # un endpoint que fallo antes del commit
    b = db._get_conn()
    cur = b.cursor()
    cur.execute("SELECT count(*) FROM camaras WHERE id = 99")
    assert cur.fetchone()[0] == 0
    b.close()


def test_lo_commiteado_queda_guardado(pool_nuevo, conn):
    a = db._get_conn()
    cur = a.cursor()
    cur.execute("INSERT INTO camaras (id, nombre, rtsp_url) VALUES (98, 'con commit', 'rtsp://x')")
    a.commit()
    a.close()
    cur = conn.cursor()
    cur.execute("SELECT nombre FROM camaras WHERE id = 98")
    assert cur.fetchone()[0] == "con commit"


def test_una_conexion_rota_se_descarta_y_el_pool_sigue_andando(pool_nuevo):
    a = db._get_conn()
    rota = pid(a)
    a._conn.close()                      # p. ej. Supabase la corto
    a.close()
    b = db._get_conn()
    assert not b.closed and pid(b) != rota
    b.close()


def test_si_el_servidor_la_cerro_mientras_estaba_en_el_pool_se_reemplaza(pool_nuevo):
    a = db._get_conn()
    real = a._conn
    a.close()
    real.close()                         # cerrada estando guardada en el pool
    b = db._get_conn()
    cur = b.cursor()
    cur.execute("SELECT 1")
    assert cur.fetchone() == (1,)
    b.close()


def test_una_conexion_que_nadie_cerro_vuelve_al_pool_al_liberarse(pool_nuevo):
    for _ in range(db.POOL_MAX + 3):     # mas pedidos que conexiones, ninguno llama a close()
        c = db._get_conn()
        pid(c)
        del c
        gc.collect()
    assert len(db._pool._used) == 0


def test_con_el_pool_agotado_atiende_igual_con_una_conexion_propia(pool_nuevo):
    prestadas = [db._get_conn() for _ in range(db.POOL_MAX)]
    extra = db._get_conn()
    assert not isinstance(extra, db._ConexionDelPool)
    assert pid(extra) not in {pid(c) for c in prestadas}
    extra.close()
    for c in prestadas:
        c.close()


def test_with_conn_hace_commit_al_salir(pool_nuevo, conn):
    a = db._get_conn()
    with a:
        cur = a.cursor()
        cur.execute("INSERT INTO camaras (id, nombre, rtsp_url) VALUES (97, 'with', 'rtsp://x')")
    a.close()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM camaras WHERE id = 97")
    assert cur.fetchone()[0] == 1


def test_cambiar_de_base_crea_otro_pool(pool_nuevo, monkeypatch):
    db._get_conn().close()
    anterior = db._pool
    monkeypatch.setenv("DATABASE_URL", URL + "?application_name=otra")
    db._get_conn().close()
    assert db._pool is not anterior

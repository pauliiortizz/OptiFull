"""Tests de integracion contra un Postgres REAL con el schema de OptiFull (db/schema.sql).

Necesitan la variable TEST_DATABASE_URL apuntando a una base de pruebas (NUNCA la de Supabase: cada test
vacia todas las tablas). En el pipeline la crea un contenedor de Postgres temporal (ver pipeline.yml);
localmente se saltean si la variable no esta definida.

  TEST_DATABASE_URL=postgresql://postgres@localhost:5432/optifull_test pytest -c test/pytest.ini test/bd
"""
import json
import os
from datetime import datetime, timedelta

import pytest

psycopg2 = pytest.importorskip("psycopg2")

URL = os.environ.get("TEST_DATABASE_URL")

# Tablas que se vacian antes de cada test (roles queda: lo carga el schema y lo usan los usuarios).
TABLAS = ("alertas", "eventos", "visitas", "trayectorias", "mapas_calor", "mapas_calor_camara", "metricas_flujo",
          "empleados_descripciones", "personas", "empleados", "zonas", "sesiones_video", "camaras")

HOY = datetime(2026, 10, 7, 10, 0, 0)
DESC = {"color_ropa_superior": "rojo", "color_ropa_inferior": "azul", "complexion": "media",
        "cabello": "corto oscuro", "accesorios": "ninguno"}
DESC_EMPLEADO = {"color_ropa_superior": "verde", "color_ropa_inferior": "negro", "complexion": "media",
                 "cabello": "corto oscuro", "accesorios": "gorra"}
CAJA = [[0, 0], [400, 0], [400, 400], [0, 400]]        # esquina superior izquierda del frame 1920x1080
GONDOLA = [[1000, 0], [1900, 0], [1900, 1000], [1000, 1000]]


@pytest.fixture
def conn():
    if not URL:
        pytest.skip("TEST_DATABASE_URL no definida (tests contra Postgres real)")
    c = psycopg2.connect(URL)
    cur = c.cursor()
    cur.execute(f"TRUNCATE {', '.join(TABLAS)} RESTART IDENTITY CASCADE")
    c.commit()
    yield c
    c.rollback()
    c.close()


class Datos:
    """Atajos para cargar datos de prueba con SQL directo (independiente del codigo que se prueba)."""

    def __init__(self, conn):
        self.conn = conn

    def _uno(self, sql, params):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        fila = cur.fetchone()
        self.conn.commit()
        cur.close()
        return fila[0] if fila else None

    def valor(self, sql, params=()):
        return self._uno(sql, params)

    def filas(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        r = cur.fetchall()
        cur.close()
        return r

    def camara(self, id_, nombre=None):
        return self._uno("INSERT INTO camaras (id, nombre, rtsp_url) VALUES (%s, %s, 'rtsp://x') RETURNING id",
                         (id_, nombre or f"Camara {id_}"))

    def zona(self, camara_id, tipo, poligono, nombre=None):
        return self._uno("INSERT INTO zonas (camara_id, nombre, tipo, poligono) VALUES (%s, %s, %s, %s) RETURNING id",
                         (camara_id, nombre or tipo, tipo, json.dumps(poligono)))

    def sesion(self, camara_id, inicio=HOY, fin=None, archivo=None, frame_w=1920):
        return self._uno("INSERT INTO sesiones_video (camara_id, inicio, fin, archivo_path, frame_w, frame_h) "
                         "VALUES (%s, %s, %s, %s, %s, 1080) RETURNING id", (camara_id, inicio, fin, archivo, frame_w))

    def persona(self, sesion_id, inicio=HOY, dur_seg=60, desc=None, cliente_id=None, es_empleado=False,
                empleado_id=None):
        pid = self._uno(
            "INSERT INTO personas (sesion_id, primera_deteccion, ultima_deteccion, descripcion_visual, es_empleado, "
            "empleado_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (sesion_id, inicio, inicio + timedelta(seconds=dur_seg), json.dumps(desc) if desc else None,
             es_empleado, empleado_id))
        self._uno("UPDATE personas SET cliente_id = %s WHERE id = %s RETURNING id",
                  (cliente_id if cliente_id is not None else pid, pid))
        return pid

    def punto(self, persona_id, zona_id=None, ts=HOY, x=100, y=100, es_empleado=False, camara_id=None, bbox=None):
        x1, y1, x2, y2 = bbox or (x - 20, y - 100, x + 20, y)
        return self._uno(
            "INSERT INTO trayectorias (persona_id, zona_id, camara_id, es_empleado, timestamp, centroide_x, "
            "centroide_y, bbox_x1, bbox_y1, bbox_x2, bbox_y2) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (persona_id, zona_id, camara_id, es_empleado, ts, x, y, x1, y1, x2, y2))

    def empleado(self, nombre="Empleado", descripciones=()):
        eid = self._uno("INSERT INTO empleados (nombre) VALUES (%s) RETURNING id", (nombre,))
        for d in descripciones:
            self._uno("INSERT INTO empleados_descripciones (empleado_id, descripcion) VALUES (%s, %s) RETURNING id",
                      (eid, json.dumps(d)))
        return eid

    def persona_campo(self, pid, campo):
        return self.valor(f"SELECT {campo} FROM personas WHERE id = %s", (pid,))


@pytest.fixture
def datos(conn):
    return Datos(conn)


@pytest.fixture
def db(conn):
    from deteccion.persistencia import Persistencia
    p = Persistencia(URL, has_db=True, guardar_trayectorias=True,
                     camara_nombres={2: ("Salon", "Frente del local")},
                     grupos_camara={1: [1, 3, 4], 3: [1, 3, 4], 4: [1, 3, 4], 2: [2]}, reid_ventana_horas=1.0)
    assert p.conectar()
    yield p
    p.cerrar()

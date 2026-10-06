"""
StockAgent
----------
Interfaz con la base de datos de productos y stock.

Usa la base Postgres/Supabase COMPARTIDA por todo el equipo
(DATABASE_URL en .env, ver frontend/api/db.py). Es necesario porque el
mismo dato (stock, catálogo, transacciones) lo tiene que poder leer el
endpoint web (frontend/api/productos.py) sin importar código de este
módulo, solo mirando la base.

cargar_productos() cae a leer directo de data/productos.csv si no hay
DATABASE_URL configurada (mismo patrón que frontend/api/db.py con
personas: sin conexión, se usa el CSV) -- así los tests de matching
(test_matching.py) siguen corriendo offline, sin depender de la base.
obtener_stock()/descontar() SÍ necesitan la base real: no tiene
sentido "descontar stock" contra un archivo de solo lectura.

Estructura (ver db/schema.sql):

  productos (
    sku            TEXT PRIMARY KEY,
    nombre         TEXT,
    marca          TEXT,     -- ej "Coca-Cola"
    variante       TEXT,     -- ej "Zero" (puede ser NULL para "Original")
    tamano_valor   FLOAT,    -- ej 500
    tamano_unidad  TEXT,     -- ej "ml"
    categoria      TEXT,     -- ej "gaseosa"
    cantidad       INTEGER,  -- stock
    precio         NUMERIC
  )

  transacciones (
    id                     BIGSERIAL PRIMARY KEY,
    sku                    TEXT REFERENCES productos(sku),
    cantidad               INTEGER,
    confianza_llm          FLOAT,     -- 0-1, la que devolvió el modelo
    estado_matching        TEXT,      -- "reconocido" o "confirmar"
    confirmado_por_cajera  BOOLEAN,
    datos_llm_json         JSONB,     -- JSON crudo del LLM (auditoría / métricas)
    timestamp              TIMESTAMP  -- default NOW()
  )
"""

import csv
import json
import os

import psycopg2
import psycopg2.extras

from config import CSV_PATH


def _conectar():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    # connect_timeout: mismo motivo que db_cashier_agent.py -- sin esto,
    # un Supabase lento/recien despertando puede colgar esta llamada.
    return psycopg2.connect(database_url, connect_timeout=8)


class StockAgent:
    def __init__(self):
        self.conn = _conectar()

    def _requiere_conexion(self):
        if self.conn is None:
            raise RuntimeError(
                "Falta DATABASE_URL. Ponela en el .env (la misma conexión a "
                "Supabase que usa frontend/api/db.py) -- esta operación "
                "necesita la base real, no alcanza con el CSV."
            )

    def cargar_productos(self):
        if self.conn is None:
            print("[StockAgent] Sin DATABASE_URL, cargando catálogo desde CSV "
                  f"({CSV_PATH}). El stock que se vea NO es el real de Supabase.")
            with open(CSV_PATH, "r", encoding="utf-8") as f:
                return [
                    {
                        "sku": r["sku"], "nombre": r["nombre"], "marca": r["marca"],
                        "variante": r["variante"],
                        "tamano_valor": float(r["tamano_valor"]),
                        "tamano_unidad": r["tamano_unidad"],
                        "categoria": r["categoria"],
                        "cantidad": int(r["cantidad"]),
                    }
                    for r in csv.DictReader(f)
                ]

        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT sku, nombre, marca, variante,
                   tamano_valor, tamano_unidad, categoria, cantidad
            FROM productos
        """)
        productos = [dict(row) for row in cur.fetchall()]
        cur.close()
        return productos

    def obtener_stock(self, sku):
        self._requiere_conexion()
        cur = self.conn.cursor()
        cur.execute("SELECT cantidad FROM productos WHERE sku = %s", (sku,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None

    def descontar(self, sku, cantidad, confianza_llm, estado_matching,
                   datos_llm, confirmado_por_cajera=False):
        self._requiere_conexion()
        # Descontar y leer el stock nuevo en UNA sola consulta (RETURNING),
        # en vez de leer primero y escribir después: cada viaje a Supabase
        # son ~230 ms en los que el detector no mira la cámara. Además es
        # atómico -- no puede pisarse con otra venta simultánea.
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE productos SET cantidad = GREATEST(cantidad - %s, 0)
            WHERE sku = %s RETURNING cantidad
        """, (cantidad, sku))
        row = cur.fetchone()
        if row is None:
            self.conn.rollback()
            cur.close()
            raise ValueError(f"SKU {sku} no existe")
        nuevo = row[0]
        cur.execute("""
            INSERT INTO transacciones
              (sku, cantidad, confianza_llm, estado_matching,
               confirmado_por_cajera, datos_llm_json)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (sku, cantidad, confianza_llm, estado_matching,
              bool(confirmado_por_cajera),
              json.dumps(datos_llm, ensure_ascii=False)))
        self.conn.commit()
        cur.close()
        return nuevo

    def close(self):
        if self.conn is not None:
            self.conn.close()

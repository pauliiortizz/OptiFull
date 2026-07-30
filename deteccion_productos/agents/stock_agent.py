"""
StockAgent
----------
Interfaz con la base de datos de productos y stock.

La BD ahora es MUCHO más simple: solo tiene los campos naturales que
cualquier sistema de gestión ya usa (marca, variante, tamaño). NO hay
'textos_referencia' cargados a mano.

Estructura:

  productos (
    sku            TEXT PRIMARY KEY,
    nombre         TEXT,     -- ej "Coca-Cola Zero 500ml"
    marca          TEXT,     -- ej "Coca-Cola"
    variante       TEXT,     -- ej "Zero" (puede ser NULL para "Original")
    tamano_valor   REAL,     -- ej 500
    tamano_unidad  TEXT,     -- ej "ml"
    categoria      TEXT,     -- ej "gaseosa"
    cantidad       INTEGER,  -- stock
    precio         REAL
  )

  transacciones (
    id                     INTEGER PRIMARY KEY,
    sku                    TEXT,
    cantidad               INTEGER,
    confianza_llm          REAL,      -- 0-1, la que devolvió el modelo
    estado_matching        TEXT,      -- "reconocido" o "confirmar"
    confirmado_por_cajera  INTEGER,   -- 0 o 1
    datos_llm_json         TEXT,      -- JSON crudo del LLM (auditoría / métricas)
    timestamp              TEXT
  )
"""

import json
import sqlite3
from datetime import datetime

from config import DB_PATH


class StockAgent:
    def __init__(self, db_path=DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def cargar_productos(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT sku, nombre, marca, variante,
                    tamano_valor, tamano_unidad, categoria, cantidad
            FROM productos
        """)
        return [dict(row) for row in cur.fetchall()]

    def obtener_stock(self, sku):
        cur = self.conn.cursor()
        cur.execute("SELECT cantidad FROM productos WHERE sku = ?", (sku,))
        row = cur.fetchone()
        return row["cantidad"] if row else None

    def descontar(self, sku, cantidad, confianza_llm, estado_matching,
                   datos_llm, confirmado_por_cajera=False):
        cur = self.conn.cursor()
        stock_actual = self.obtener_stock(sku)
        if stock_actual is None:
            raise ValueError(f"SKU {sku} no existe")

        nuevo = max(stock_actual - cantidad, 0)
        cur.execute("UPDATE productos SET cantidad = ? WHERE sku = ?", (nuevo, sku))
        cur.execute("""
            INSERT INTO transacciones
              (sku, cantidad, confianza_llm, estado_matching,
               confirmado_por_cajera, datos_llm_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sku, cantidad, confianza_llm, estado_matching,
              int(confirmado_por_cajera),
              json.dumps(datos_llm, ensure_ascii=False),
              datetime.now().isoformat()))
        self.conn.commit()
        return nuevo

    def close(self):
        self.conn.close()

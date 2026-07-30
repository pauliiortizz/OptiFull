"""
setup_db.py
-----------
Crea la base SQLite e importa productos desde data/productos.csv.
Se corre UNA vez para inicializar.
"""

import csv
import os
import sqlite3

from config import DB_PATH, CSV_PATH


def main():
    if os.path.exists(DB_PATH):
        r = input(f"La base {DB_PATH} ya existe. Sobrescribir? (s/N): ")
        if r.strip().lower() != "s":
            print("Cancelado.")
            return
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE productos (
            sku            TEXT PRIMARY KEY,
            nombre         TEXT NOT NULL,
            marca          TEXT,
            variante       TEXT,
            tamano_valor   REAL,
            tamano_unidad  TEXT,
            categoria      TEXT,
            cantidad       INTEGER DEFAULT 0,
            precio         REAL
        )
    """)
    cur.execute("""
        CREATE TABLE transacciones (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            sku                   TEXT,
            cantidad              INTEGER,
            confianza_llm         REAL,
            estado_matching       TEXT,
            confirmado_por_cajera INTEGER,
            datos_llm_json        TEXT,
            timestamp             TEXT
        )
    """)

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        productos = list(csv.DictReader(f))

    for p in productos:
        cur.execute("""
            INSERT INTO productos
              (sku, nombre, marca, variante, tamano_valor,
               tamano_unidad, categoria, cantidad, precio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (p["sku"], p["nombre"], p["marca"], p["variante"],
              float(p["tamano_valor"]), p["tamano_unidad"],
              p["categoria"], int(p["cantidad"]), float(p["precio"])))

    conn.commit()
    conn.close()
    print(f"Base creada en {DB_PATH} con {len(productos)} productos.")


if __name__ == "__main__":
    main()

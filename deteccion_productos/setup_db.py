"""
setup_db.py
-----------
Carga (o actualiza) data/productos.csv en la tabla 'productos' de la
base compartida Postgres/Supabase.

El schema (CREATE TABLE) lo aplica el script del equipo, una sola vez
por base: python db/create_db.py (raíz del repo). Este script solo
carga los datos del catálogo -- se puede correr de nuevo cuando cambia
el CSV, sin perder el stock ya descontado por ventas (usa UPSERT: si
el sku ya existe, actualiza sus datos según lo que traiga el CSV).

Uso: python setup_db.py
"""

import csv
import os

import psycopg2
from dotenv import load_dotenv

from config import CSV_PATH

load_dotenv()


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Falta DATABASE_URL en el .env (la misma conexión a Supabase "
            "que usa frontend/api/db.py)."
        )

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        productos = list(csv.DictReader(f))

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()
    for p in productos:
        cur.execute("""
            INSERT INTO productos
              (sku, nombre, marca, variante, tamano_valor,
               tamano_unidad, categoria, cantidad, precio)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sku) DO UPDATE SET
                nombre        = EXCLUDED.nombre,
                marca         = EXCLUDED.marca,
                variante      = EXCLUDED.variante,
                tamano_valor  = EXCLUDED.tamano_valor,
                tamano_unidad = EXCLUDED.tamano_unidad,
                categoria     = EXCLUDED.categoria,
                cantidad      = EXCLUDED.cantidad,
                precio        = EXCLUDED.precio
        """, (p["sku"], p["nombre"], p["marca"], p["variante"],
              float(p["tamano_valor"]), p["tamano_unidad"],
              p["categoria"], int(p["cantidad"]), float(p["precio"])))

    conn.commit()
    cur.close()
    conn.close()
    print(f"{len(productos)} productos cargados/actualizados en Postgres.")


if __name__ == "__main__":
    main()

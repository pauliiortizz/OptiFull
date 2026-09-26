"""
Comprueba que la base de datos de OptiFull (Postgres/Supabase) esta accesible y
tiene el schema esperado. Solo LEE: no crea ni modifica nada.

Uso:  python db/check_connection.py
Lee DATABASE_URL del entorno (o de .env). Sale con codigo 0 si todo esta bien,
1 si no. Lo usa el pipeline (.github/workflows/pipeline.yml) antes de cada deploy.
"""
import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2

TABLAS_REQUERIDAS = (
    "camaras", "sesiones_video", "zonas", "personas", "trayectorias", "visitas",
    "productos", "transacciones", "caja_estado", "alertas", "eventos",
    "metricas_flujo", "mapas_calor",
)
INTENTOS = 5
ESPERA_SEG = 5


def conectar(database_url):
    """Reintenta unos segundos: Supabase puede tardar en despertar un proyecto pausado."""
    ultimo_error = None
    for intento in range(1, INTENTOS + 1):
        try:
            return psycopg2.connect(database_url, connect_timeout=10)
        except psycopg2.OperationalError as e:
            ultimo_error = e
            print(f"[DB] intento {intento}/{INTENTOS} fallido: {str(e).strip()}")
            if intento < INTENTOS:
                time.sleep(ESPERA_SEG)
    raise ultimo_error


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("[DB] ERROR: DATABASE_URL no esta definida.")
        return 1

    try:
        conn = conectar(database_url)
    except psycopg2.Error:
        print("[DB] ERROR: no se pudo conectar a la base de datos.")
        return 1

    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.execute("SELECT current_database(), version()")
        nombre, version = cur.fetchone()
        print(f"[DB] Conexion OK -> base '{nombre}' ({version.split(',')[0]})")

        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        existentes = {r[0] for r in cur.fetchall()}
        faltantes = [t for t in TABLAS_REQUERIDAS if t not in existentes]
        if faltantes:
            print(f"[DB] ERROR: faltan tablas del schema: {', '.join(faltantes)}")
            print("[DB] Aplicalo con: python db/create_db.py")
            return 1
        print(f"[DB] Schema OK ({len(TABLAS_REQUERIDAS)} tablas requeridas presentes)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

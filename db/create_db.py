"""
Aplica el schema de OptiFull (db/schema.sql) contra la base de datos Postgres
de Supabase.
Uso: python db/create_db.py
"""
import sys
import os

try:
    from dotenv import load_dotenv
except ImportError:
    print("Instalando python-dotenv...")
    os.system(f"{sys.executable} -m pip install python-dotenv -q")
    from dotenv import load_dotenv

try:
    import psycopg2
except ImportError:
    print("Instalando psycopg2-binary...")
    os.system(f"{sys.executable} -m pip install psycopg2-binary -q")
    import psycopg2

def main():
    print("=== Aplicar schema OptiFull en Supabase ===\n")
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        database_url = input(
            "DATABASE_URL no encontrada en .env.\n"
            "Pegá la connection string de Supabase "
            "(Project Settings > Database > Connection string > Transaction pooler): "
        ).strip()

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    conn = None
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        print("\nConectado a Supabase correctamente.")

        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()

        cur.execute(sql)
        conn.commit()
        cur.close()
        conn.close()

        print("\nSchema aplicado exitosamente.")
        print("Tablas: camaras, sesiones_video, zonas, personas,")
        print("        trayectorias, productos, transacciones, caja_estado,")
        print("        alertas, metricas_flujo, mapas_calor")
        print("\nDatos iniciales cargados: 3 camaras, 4 zonas.")

    except psycopg2.Error as e:
        if conn is not None:
            conn.rollback()
        print(f"\n[!] Error aplicando el schema: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

"""
Crea la base de datos optifull en MySQL ejecutando db/schema.sql.
Uso: python db/create_db.py
"""
import sys
import os
import getpass

try:
    import mysql.connector
except ImportError:
    print("Instalando mysql-connector-python...")
    os.system(f"{sys.executable} -m pip install mysql-connector-python -q")
    import mysql.connector

def main():
    print("=== Crear base de datos OptiFull ===\n")
    host     = input("Host     [localhost]: ").strip() or "localhost"
    port     = input("Puerto   [3306]:      ").strip() or "3306"
    user     = input("Usuario  [root]:      ").strip() or "root"
    password = getpass.getpass("Contrasena:           ")

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    try:
        conn = mysql.connector.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            allow_local_infile=True
        )
        cursor = conn.cursor()
        print("\nConectado a MySQL correctamente.")

        # Paso 1: crear la base de datos
        cursor.execute("CREATE DATABASE IF NOT EXISTS optifull CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
        cursor.close()
        conn.close()
        print("Base de datos 'optifull' creada (o ya existia).")

        # Paso 2: reconectar directamente sobre optifull
        conn = mysql.connector.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database="optifull",
            allow_local_infile=True
        )
        cursor = conn.cursor()

        # Leer schema, quitar comentarios y separar statements
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()

        def limpiar(stmt):
            lineas = [l for l in stmt.splitlines() if not l.strip().startswith("--")]
            return "\n".join(lineas).strip()

        statements = [
            limpiar(s) for s in sql.split(";")
            if limpiar(s)
            and not limpiar(s).upper().startswith("CREATE DATABASE")
            and not limpiar(s).upper().startswith("USE ")
        ]

        errores = 0
        for stmt in statements:
            try:
                cursor.execute(stmt)
                conn.commit()
            except mysql.connector.Error as e:
                # Ignorar "ya existe" (idempotente)
                if e.errno in (1007, 1050, 1060, 1061, 1062):
                    pass
                else:
                    print(f"  [!] Error: {e}\n      SQL: {stmt[:80]}...")
                    errores += 1

        cursor.close()
        conn.close()

        if errores == 0:
            print("\nBase de datos 'optifull' creada exitosamente.")
            print("Tablas: camaras, sesiones_video, zonas, personas,")
            print("        trayectorias, productos, detecciones_producto,")
            print("        alertas, metricas_flujo, mapas_calor")
            print("\nDatos iniciales cargados: 3 camaras, 4 zonas.")
        else:
            print(f"\nFinalizado con {errores} error(es). Revisa los mensajes de arriba.")

    except mysql.connector.Error as e:
        print(f"\nNo se pudo conectar a MySQL: {e}")
        print("Verifica que MySQL este corriendo y que las credenciales sean correctas.")
        sys.exit(1)

if __name__ == "__main__":
    main()

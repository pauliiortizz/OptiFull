"""Crea (o actualiza la clave de) una cuenta para iniciar sesion en OptiFull.

La clave se guarda hasheada (pbkdf2-sha256 con sal, el mismo metodo que usa /api/login): nunca en texto plano.
Se pide por teclado sin mostrarla; tambien se puede pasar en la variable de entorno OPTIFULL_CLAVE (util para
crear el usuario del pipeline).

Uso:
  python db/crear_usuario.py --usuario pipeline_qa --nombre "Pipeline QA" --rol usuario --cargo empleado
Lee DATABASE_URL del entorno (o de .env).
"""
import argparse
import getpass
import os
import sys

import psycopg2
from werkzeug.security import generate_password_hash

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CLAVE_MINIMA = 8   # mismo minimo que frontend/api/login.py


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--usuario", required=True)
    p.add_argument("--nombre", required=True)
    p.add_argument("--email")
    p.add_argument("--rol", choices=("administrador", "usuario"), default="usuario")
    p.add_argument("--cargo", choices=("dueno", "gerente", "empleado"), default="empleado")
    args = p.parse_args()

    clave = os.environ.get("OPTIFULL_CLAVE") or getpass.getpass("Clave: ")
    if len(clave) < CLAVE_MINIMA:
        sys.exit(f"La clave tiene que tener al menos {CLAVE_MINIMA} caracteres.")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("Falta DATABASE_URL (en el entorno o en .env).")

    with psycopg2.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO usuarios (usuario, email, nombre, clave_hash, rol_id, cargo)
            VALUES (%(usuario)s, %(email)s, %(nombre)s, %(hash)s,
                    (SELECT id FROM roles WHERE nombre = %(rol)s), %(cargo)s)
            ON CONFLICT (LOWER(usuario)) DO UPDATE
               SET clave_hash = EXCLUDED.clave_hash, activo = TRUE
            RETURNING id, (xmax = 0) AS creado
        """, {"usuario": args.usuario, "email": args.email, "nombre": args.nombre, "rol": args.rol,
              "cargo": args.cargo, "hash": generate_password_hash(clave, method="pbkdf2:sha256")})
        usuario_id, creado = cur.fetchone()
    print(f"Usuario '{args.usuario}' {'creado' if creado else 'actualizado (clave nueva)'} con id {usuario_id}.")


if __name__ == "__main__":
    main()

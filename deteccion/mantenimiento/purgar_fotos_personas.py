"""Retencion de las fotos de personas (personas.foto_url).

La foto de cada persona se guarda para que el usuario decida, desde la alerta "Persona posiblemente empleada", si es
empleado o no; al resolverla la API la borra. Si nadie la revisa, la foto (un dato personal) quedaria para siempre:
este script borra las de personas NO revisadas (empleado_revisado = FALSE) cuya ultima deteccion tiene mas de N dias,
tanto de Supabase Storage como del respaldo local (carpeta evidencias/), y pone foto_url = NULL.

Por defecto solo SIMULA (muestra que borraria). Con --aplicar borra de verdad.

Uso: python -m deteccion.mantenimiento.purgar_fotos_personas [--dias 30] [--aplicar]
"""
import argparse
import os
import urllib.parse

import psycopg2

from deteccion import config
from deteccion.pipeline.evidencia import CARPETA_LOCAL
from deteccion.pipeline.storage import SupabaseStorage

DIAS_POR_DEFECTO = 30


def _borrar_archivo(storage: SupabaseStorage, foto_url: str) -> bool:
    """Borra el archivo de una foto (URL de Storage o ruta relativa a evidencias/). True si ya no existe."""
    if foto_url.startswith(("http://", "https://")):
        prefijo = f"{storage.url}/storage/v1/object/public/{storage.bucket}/"
        if not foto_url.startswith(prefijo):
            return False                     # no es de nuestro bucket: no se toca
        return storage.borrar(urllib.parse.unquote(foto_url[len(prefijo):].split("?")[0]))
    base = os.path.abspath(CARPETA_LOCAL)
    local = os.path.abspath(os.path.join(base, foto_url.replace("\\", "/")))
    if os.path.commonpath([base, local]) != base:
        return False                         # ruta fuera de evidencias/
    if os.path.isfile(local):
        os.remove(local)
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dias", type=int, default=DIAS_POR_DEFECTO, help="antiguedad minima en dias (default 30)")
    ap.add_argument("--aplicar", action="store_true", help="borra de verdad (sin esto solo simula)")
    args = ap.parse_args()

    if not config.DATABASE_URL:
        print("[AVISO] DATABASE_URL no configurada.")
        return
    storage = SupabaseStorage(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, config.SUPABASE_BUCKET,
                              config.HAS_SUPABASE_STORAGE)
    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, foto_url FROM personas WHERE foto_url IS NOT NULL AND NOT empleado_revisado "
                    "AND ultima_deteccion < NOW() - make_interval(days => %s) ORDER BY id", (args.dias,))
        filas = cur.fetchall()
        print(f"Fotos sin revisar con mas de {args.dias} dias: {len(filas)}")
        borradas = 0
        for persona_id, foto_url in filas:
            if not args.aplicar:
                print(f"  [simulacion] persona #{persona_id}: {foto_url}")
                continue
            if _borrar_archivo(storage, foto_url):
                cur.execute("UPDATE personas SET foto_url = NULL WHERE id = %s", (persona_id,))
                borradas += 1
            else:
                print(f"  [AVISO] persona #{persona_id}: no se pudo borrar {foto_url}; se deja para la proxima corrida")
        conn.commit()
        print(f"Fotos borradas: {borradas}" if args.aplicar else "Simulacion: nada se borro (usar --aplicar).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

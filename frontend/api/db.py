"""Carga de datos desde la BD Supabase (Postgres) o fallback a CSV."""
import csv
from datetime import date

from .paths import CSV_PATH

# Camaras que miran el MISMO lugar fisico que otra camara del grupo (ver
# GRUPOS_CAMARA en deteccion/config.py: 1, 3 y 4 apuntan todas a la zona de
# cajas) pero NO son la elegida como fuente de verdad para CONTAR personas.
# Probamos fusionar sus conteos via Re-ID por descripcion de texto (color de
# ropa, etc. -- ver deteccion/persistencia.py) y nunca converge del todo:
# Gemini describe la misma prenda distinto segun el angulo/luz de cada
# camara, asi que sumar los "unicos" de las 3 camaras infla el total en vez
# de mantenerlo igual (que es lo que deberia pasar si ven a la misma gente).
# En vez de perseguir una fusion perfecta, se cuenta la gente de ese grupo
# UNA sola vez, desde la camara con mejor cobertura (camara 4: angulo lateral
# izquierdo, menos oclusion que camara 3 -- frontal -- o camara 1 -- derecha).
# Las camaras excluidas siguen totalmente analizadas y guardadas en la BD
# (heatmap, trayectorias, ocupacion de zona) -- solo se excluyen de los
# reportes que CUENTAN personas, para no duplicar/inflar el numero.
CAMARAS_EXCLUIDAS_DE_CONTEO = (1, 3)


def parse_rango(desde, hasta):
    """Rango de fechas (date, date) a partir de 'YYYY-MM-DD'. Un valor vacio o invalido queda en None
    (= sin limite de ese lado); si vienen al reves se intercambian. Los filtros del dashboard (Hoy,
    7 dias, 30 dias, Personalizado) mandan siempre las dos fechas ya calculadas en el navegador."""
    def uno(v):
        try:
            return date.fromisoformat(v) if v else None
        except (TypeError, ValueError):
            return None
    d, h = uno(desde), uno(hasta)
    if d and h and d > h:
        d, h = h, d
    return d, h


def rango_de_request():
    """(desde, hasta) segun los parametros ?desde= y ?hasta= del pedido actual."""
    from flask import request
    return parse_rango(request.args.get('desde'), request.args.get('hasta'))


# Fragmento SQL para filtrar por rango de fechas sobre la columna 'col' (cast a date): parametros
# %(desde)s y %(hasta)s, ambos opcionales (NULL = sin limite).
def sql_rango(col: str) -> str:
    return (f"(%(desde)s::date IS NULL OR {col}::date >= %(desde)s::date) "
            f"AND (%(hasta)s::date IS NULL OR {col}::date <= %(hasta)s::date)")


def _imagen_url(imagen_path):
    """'imagen_path' puede ser una URL completa de Supabase Storage (subida
    nueva) o un nombre de archivo local (fallback de cuando Storage no estaba
    configurado). Devuelve la URL lista para usar en el frontend."""
    import os
    if not imagen_path:
        return None
    if imagen_path.startswith('http://') or imagen_path.startswith('https://'):
        return imagen_path
    # Ruta relativa a la raiz del proyecto (ej. 'heatmaps_pendientes/camara_1_x.png'); los
    # archivos viejos guardados en la raiz son un nombre suelto y siguen funcionando igual.
    return f"/api/heatmap/image/{imagen_path.replace(chr(92), '/')}"


def _get_conn():
    """Abre una conexion a Supabase si DATABASE_URL esta configurada en .env.
    Retorna None si no hay URL o si la conexion falla (permite fallback a CSV)."""
    import os
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(database_url, connect_timeout=3)
    except Exception:
        return None


def cargar_csv():
    rows = []
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append({
                'id':           int(r['id']),
                'entrada':      r['entrada'],
                'salida':       r['salida'],
                'duracion_seg': float(r['duracion_seg']),
                'duracion_min': float(r['duracion_min']),
                'cliente_id':   int(r['id']),  # CSV no tiene ReID: cada fila es un cliente distinto
            })
    return rows


def cargar_db(desde=None, hasta=None, vacio_ok=False):
    """Personas (clientes) de la BD, opcionalmente acotadas a un rango de fechas de su primera deteccion.
    Devuelve None si la BD no responde (el llamador cae al CSV); con 'vacio_ok' un rango sin personas
    devuelve [] en vez de None, para no confundir 'sin datos en el periodo' con 'BD caida'."""
    conn = _get_conn()
    if conn is None:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT p.id,
                   TO_CHAR(p.primera_deteccion, 'HH24:MI:SS') AS entrada,
                   TO_CHAR(p.ultima_deteccion,  'HH24:MI:SS') AS salida,
                   p.duracion_total_seg                       AS duracion_seg,
                   COALESCE(p.cliente_id, p.id)                AS cliente_id
            FROM personas p
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
            WHERE raiz.es_empleado = FALSE AND sv.camara_id NOT IN %(excl)s
              AND """ + sql_rango('p.primera_deteccion') + """
            ORDER BY p.id
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta})
        rows = cur.fetchall()
        for r in rows:
            r['duracion_min'] = round(r['duracion_seg'] / 60, 2)
        cur.close(); conn.close()
        return rows if vacio_ok else (rows or None)
    except Exception:
        return None


def cargar_permanencias_db(desde=None, hasta=None):
    """Permanencia REAL por cliente: suma 'visitas' (segmentos de presencia
    continua ante camara, sin huecos -- ver comentario en la tabla 'visitas'
    de schema.sql) agrupando por cliente_id real, entre TODAS las sesiones o
    videos donde ese cliente fue detectado (los candidatos de Re-ID ya estan
    restringidos al mismo dia calendario, asi que la suma nunca mezcla dias
    distintos). A diferencia de 'personas.duracion_total_seg', esto no cuenta
    como permanencia el tiempo que la persona estuvo fuera de camara entre
    apariciones, y suma correctamente a alguien detectado en varios videos
    (ej. una empleada con 20 min en el video 1 y 1h en el video 5 del mismo
    dia -> 1h20 de permanencia total)."""
    conn = _get_conn()
    if conn is None:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                COALESCE(p.cliente_id, p.id)           AS cliente_id,
                TO_CHAR(MIN(v.entrada), 'HH24:MI:SS')  AS entrada,
                TO_CHAR(MAX(v.salida),  'HH24:MI:SS')  AS salida,
                SUM(v.duracion_seg)                    AS duracion_seg
            FROM personas p
            JOIN visitas  v    ON v.persona_id = p.id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
            WHERE raiz.es_empleado = FALSE AND sv.camara_id NOT IN %(excl)s
              AND """ + sql_rango('p.primera_deteccion') + """
            GROUP BY COALESCE(p.cliente_id, p.id)
            ORDER BY cliente_id
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta})
        rows = cur.fetchall()
        for r in rows:
            r['duracion_min'] = round(r['duracion_seg'] / 60, 2)
        cur.close(); conn.close()
        return rows or None
    except Exception:
        return None

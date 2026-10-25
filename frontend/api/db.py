"""Carga de datos desde la BD Supabase (Postgres) o fallback a CSV."""
import csv
import os
import threading
from datetime import date

import psycopg2
from psycopg2 import pool

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
    if not imagen_path:
        return None
    if imagen_path.startswith('http://') or imagen_path.startswith('https://'):
        return imagen_path
    # Ruta relativa a la raiz del proyecto (ej. 'heatmaps_pendientes/camara_1_x.png'); los
    # archivos viejos guardados en la raiz son un nombre suelto y siguen funcionando igual.
    return f"/api/heatmap/image/{imagen_path.replace(chr(92), '/')}"


# ── Pool de conexiones ───────────────────────────────────────────────────────
# Abrir una conexion a Supabase (TCP + TLS + autenticacion) cuesta ~1,3-1,5 s medido en vivo (ver
# productos.py) y, en el plan gratuito de Render (0,1 CPU), el TLS ademas compite por la CPU con los demas
# pedidos: en el stress de 40 usuarios hasta /api/health llegaba a 8 s de p95. Con el pool, unas pocas
# conexiones quedan abiertas y cada pedido usa una prestada. Para no tocar los endpoints, _get_conn() devuelve
# la conexion envuelta: su close() la devuelve al pool en vez de cerrarla.
POOL_MAX = 5          # gunicorn corre 4 hilos (docker/Dockerfile-optifull): uno de margen
_pool = None
_pool_url = None
_pool_lock = threading.Lock()


class _ConexionDelPool:
    """La conexion de psycopg2 tal cual, salvo close(): deshace lo que haya quedado sin commit y la devuelve al
    pool (o la descarta si se rompio). Si un endpoint se olvida de cerrarla, se devuelve al liberarse el objeto."""

    def __init__(self, pool, conn):
        self._pool, self._conn = pool, conn

    def __getattr__(self, nombre):
        return getattr(self._conn, nombre)

    # 'with conn:' (commit o rollback al salir, como psycopg2): Python no los busca con __getattr__
    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)

    def close(self):
        conn, self._conn = self._conn, None
        if conn is None:
            return
        rota = bool(conn.closed)
        if not rota:
            try:
                conn.rollback()      # la proxima que la use la recibe sin una transaccion a medias
            except Exception:
                rota = True
        try:
            self._pool.putconn(conn, close=rota)
        except Exception:
            pass

    def __del__(self):
        self.close()


def _obtener_pool(database_url):
    global _pool, _pool_url
    with _pool_lock:
        if _pool is None or _pool_url != database_url:
            if _pool is not None:
                _pool.closeall()
            # keepalives: una conexion ociosa en el pool no queda muerta por la red sin que nadie se entere.
            _pool = pool.ThreadedConnectionPool(0, POOL_MAX, database_url, connect_timeout=3,
                                                keepalives=1, keepalives_idle=60, keepalives_interval=10,
                                                keepalives_count=3)
            # psycopg2 abre 'minconn' conexiones al crear el pool y al devolver una solo la guarda si hay menos
            # de 'minconn' libres (si no, la cierra). Se crea con 0 (no conecta hasta el primer pedido) y despues
            # se sube a POOL_MAX para que las guarde todas.
            _pool.minconn = POOL_MAX
            _pool_url = database_url
        return _pool


def _get_conn():
    """Conexion a Supabase si DATABASE_URL esta configurada en .env, prestada del pool (ver arriba).
    Retorna None si no hay URL o si la conexion falla (permite fallback a CSV)."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    try:
        p = _obtener_pool(database_url)
        conn = p.getconn()
        if conn.closed:                      # la cerro el servidor mientras estaba en el pool
            p.putconn(conn, close=True)
            conn = p.getconn()
        return _ConexionDelPool(p, conn)
    except pool.PoolError:
        # Pool agotado (no deberia pasar con 4 hilos): se atiende igual con una conexion propia, como antes.
        try:
            return psycopg2.connect(database_url, connect_timeout=3)
        except Exception:
            return None
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


# Permanencia = tiempo VISTO (ver cargar_permanencias_db). El pipeline guarda un punto de trayectoria cada
# TRAYECTORIA_INTERVALO_SEG mientras la persona esta a la vista; un hueco entre dos puntos seguidos de hasta
# HUECO_MAX_SEG (una oclusion breve, alguien que pasa por delante) se cuenta como presencia, uno mayor no.
TRAYECTORIA_INTERVALO_SEG = 10.0   # debe coincidir con deteccion/config.py
HUECO_MAX_SEG             = 60.0
# Un cliente con menos de esto de tiempo visto en el periodo/dia es ruido de deteccion (alguien que cruzo el borde
# del cuadro): no entra en los promedios de permanencia (KPI, permanencia semanal, reportes exportados).
PERMANENCIA_MINIMA_SEG    = 30
PARAMS_TIEMPO_VISTO       = {'hueco': HUECO_MAX_SEG, 'intervalo': TRAYECTORIA_INTERVALO_SEG,
                             'minima': PERMANENCIA_MINIMA_SEG}


def sql_tiempo_visto(filtro: str, personas: str = "raiz.es_empleado = FALSE") -> str:
    """Subconsulta compartida por TODAS las metricas de tiempo (KPI de permanencia, zonas, permanencia
    semanal, hora pico y los reportes exportados), para que midan lo mismo: una fila por punto de
    trayectoria de un cliente (sin empleados) con 'segundos' = el tiempo que aporta ese punto. Es el hueco
    hasta el siguiente punto del MISMO cliente si es <= HUECO_MAX_SEG, y si no (o si es el ultimo)
    TRAYECTORIA_INTERVALO_SEG. Al ordenar juntos los puntos de todas sus camaras y sesiones, dos camaras que
    lo ven a la vez no duplican el tiempo (el hueco entre sus puntos es ~0).

    'filtro': condicion SQL de camaras y fechas sobre 'sv' y 't' (p. ej. filtro_conteo()). 'personas': a quien
    incluir, sobre la fila raiz del cliente ('raiz'); por defecto solo clientes (la alerta de posible empleado
    suma tambien a los ya revisados, para mostrarlos como resueltos). Necesita los
    parametros de PARAMS_TIEMPO_VISTO. Columnas: cliente_id, persona_id (la aparicion en un video), ts,
    camara_id, zona_tipo (NULL fuera de zona), segundos."""
    return f"""(
        SELECT cliente_id, persona_id, ts, camara_id, zona_tipo,
               CASE WHEN hueco_seg <= %(hueco)s THEN hueco_seg ELSE %(intervalo)s END AS segundos
        FROM (
            SELECT COALESCE(p.cliente_id, p.id) AS cliente_id, t.persona_id, t.timestamp AS ts, sv.camara_id,
                   z.tipo AS zona_tipo,
                   EXTRACT(EPOCH FROM LEAD(t.timestamp) OVER (
                       PARTITION BY COALESCE(p.cliente_id, p.id) ORDER BY t.timestamp
                   ) - t.timestamp) AS hueco_seg
            FROM trayectorias t
            JOIN personas p        ON p.id = t.persona_id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            JOIN personas raiz     ON raiz.id = COALESCE(p.cliente_id, p.id)
            LEFT JOIN zonas z      ON z.id = t.zona_id
            WHERE ({personas}) AND {filtro}
        ) puntos_cliente
    )"""


def filtro_conteo() -> str:
    """Filtro del dashboard para sql_tiempo_visto: sin CAMARAS_EXCLUIDAS_DE_CONTEO (las que miran el mismo
    lugar que otra ya contada) y con el rango ?desde=&hasta= aplicado a la hora de cada punto."""
    return "sv.camara_id NOT IN %(excl)s AND " + sql_rango('t.timestamp')


def cargar_permanencias_db(desde=None, hasta=None):
    """Permanencia REAL por cliente: el tiempo que se lo VIO, a partir de sus puntos de 'trayectorias' (la
    misma fuente que la analitica de zonas, /reportes/permanencia-por-zona). Antes se sumaba 'visitas'
    (entrada -> salida), pero una visita sigue abierta mientras la persona no se ve (solo se cierra al
    reconectarla por apariencia), asi que contaba como permanencia minutos en los que nadie la estaba viendo:
    medido en oct-2026, solo ~21% del tiempo de las visitas tenia a la persona a la vista.

    Usa sql_tiempo_visto (huecos de hasta HUECO_MAX_SEG cubiertos), sin CAMARAS_EXCLUIDAS_DE_CONTEO y con el
    rango aplicado a la hora de cada punto, igual que las zonas.
    Devuelve [] si el periodo no tiene puntos y None solo si la BD no responde."""
    conn = _get_conn()
    if conn is None:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                cliente_id,
                TO_CHAR(MIN(ts), 'HH24:MI:SS') AS entrada,
                TO_CHAR(MAX(ts), 'HH24:MI:SS') AS salida,
                SUM(segundos)::float           AS duracion_seg
            FROM """ + sql_tiempo_visto(filtro_conteo()) + """ pv
            GROUP BY cliente_id
            ORDER BY cliente_id
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta, **PARAMS_TIEMPO_VISTO})
        rows = cur.fetchall()
        for r in rows:
            r['duracion_min'] = round(r['duracion_seg'] / 60, 2)
        cur.close(); conn.close()
        return rows
    except Exception:
        return None

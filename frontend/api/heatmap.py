"""Endpoints de mapas de calor (por sesion y acumulado por camara)."""
import json
import os

from flask import Response, jsonify, request, send_from_directory

from .blueprint import api_bp
from .db import _get_conn as _db_connect, _imagen_url
from .paths import BASE, FONDOS_DIR


@api_bp.route('/heatmap/latest')
def heatmap_latest():
    try:
        import psycopg2.extras
        conn = _db_connect()
        if conn is None:
            return jsonify({'error': 'sin conexion a la BD'}), 503
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT mc.*,
                   c.nombre  AS camara_nombre,
                   z.nombre  AS zona_mas_caliente_nombre
            FROM   mapas_calor mc
            LEFT JOIN camaras c ON c.id = mc.camara_id
            LEFT JOIN zonas   z ON z.id = mc.zona_id_mas_caliente
            ORDER  BY mc.periodo_inicio DESC
            LIMIT  1
        """)
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            return jsonify(None)

        # Ranking de zonas desde trayectorias de esa sesion
        zonas_ranking = []
        if row.get('sesion_id'):
            cur.execute("""
                SELECT z.nombre, COUNT(*) AS detecciones
                FROM   trayectorias t
                JOIN   zonas z ON z.id = t.zona_id
                WHERE  t.persona_id IN (
                    SELECT id FROM personas WHERE sesion_id = %s
                )
                GROUP  BY z.id, z.nombre
                ORDER  BY detecciones DESC
            """, (row['sesion_id'],))
            zona_rows = cur.fetchall()
            total = sum(r['detecciones'] for r in zona_rows) or 1
            zonas_ranking = [
                {'nombre': r['nombre'],
                 'detecciones': r['detecciones'],
                 'pct': round(r['detecciones'] / total * 100)}
                for r in zona_rows
            ]

        cur.close(); conn.close()

        return jsonify({
            'id':                row['id'],
            'camara_id':         row['camara_id'],
            'camara_nombre':     row['camara_nombre'],
            'periodo_inicio':    row['periodo_inicio'].isoformat() if row['periodo_inicio'] else None,
            'periodo_fin':       row['periodo_fin'].isoformat()    if row['periodo_fin']    else None,
            'imagen_url':        _imagen_url(row.get('imagen_path')),
            'punto_max_x':       row['punto_max_x'],
            'punto_max_y':       row['punto_max_y'],
            'valor_maximo':      row['valor_maximo'],
            'area_activa_pct':   row['area_activa_pct'],
            'concentracion':     row['concentracion'],
            'total_detecciones': row['total_detecciones'],
            'frames_procesados': row['frames_procesados'],
            'zona_mas_caliente': row['zona_mas_caliente_nombre'],
            'zonas_ranking':     zonas_ranking,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/heatmap/camara/<int:camara_id>')
def heatmap_camara(camara_id):
    """Mapa de calor acumulado (todas las sesiones combinadas) de una camara."""
    try:
        import psycopg2.extras
        conn = _db_connect()
        if conn is None:
            return jsonify({'error': 'sin conexion a la BD'}), 503
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT mcc.*,
                   c.nombre AS camara_nombre,
                   z.nombre AS zona_mas_caliente_nombre
            FROM   mapas_calor_camara mcc
            LEFT JOIN camaras c ON c.id = mcc.camara_id
            LEFT JOIN zonas   z ON z.id = mcc.zona_id_mas_caliente
            WHERE  mcc.camara_id = %s
        """, (camara_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return jsonify(None)

        return jsonify({
            'camara_id':           row['camara_id'],
            'camara_nombre':       row['camara_nombre'],
            'imagen_url':          _imagen_url(row.get('imagen_path')),
            'punto_max_x':         row['punto_max_x'],
            'punto_max_y':         row['punto_max_y'],
            'valor_maximo':        row['valor_maximo'],
            'area_activa_pct':     row['area_activa_pct'],
            'concentracion':       row['concentracion'],
            'total_detecciones':   row['total_detecciones'],
            'frames_procesados':   row['frames_procesados'],
            'sesiones_combinadas': row['sesiones_combinadas'],
            'zona_mas_caliente':   row['zona_mas_caliente_nombre'],
            'actualizado_en':      row['actualizado_en'].isoformat() if row['actualizado_en'] else None,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _fuentes_de_request():
    """Camara fuente de cada tipo de zona: FUENTES_POR_DEFECTO, cambiable con ?fuentes=gondola:4,otro:2,caja:3
    (los tipos desconocidos y las camaras que no son un numero se ignoran)."""
    from .plano_calor import FUENTES_POR_DEFECTO
    fuentes = dict(FUENTES_POR_DEFECTO)
    for par in (request.args.get('fuentes') or '').split(','):
        tipo, _, cam = par.partition(':')
        if tipo.strip() in fuentes and cam.strip().isdigit():
            fuentes[tipo.strip()] = int(cam)
    return fuentes


def _poligono(valor):
    return json.loads(valor) if isinstance(valor, str) else valor


# Matriz de calor de cada camara fuente ya traida, con el 'actualizado_en' de esa version: el croquis pide
# /heatmap/plano cada minuto y la matriz (decenas de KB por camara) solo cambia cuando el pipeline guarda
# un mapa nuevo, asi que se vuelve a traer solo entonces.
_CACHE_MATRICES = {}


@api_bp.route('/heatmap/plano')
def heatmap_plano():
    """Calor DENTRO de cada tipo de zona (caja / gondola / otro), tomado de UNA camara
    fuente por tipo -- alimenta el croquis de la tienda del dashboard. Por defecto
    gondola=4, otro=2, caja=4; se puede cambiar con ?fuentes=gondola:4,otro:2,caja:3.
    Ver plano_calor.py para como se mide."""
    from .plano_calor import calor_por_zona
    try:
        import psycopg2.extras
        fuentes = _fuentes_de_request()
        camaras_fuente = sorted(set(fuentes.values()))
        conn = _db_connect()
        if conn is None:
            return jsonify({'error': 'sin conexion a la BD'}), 503
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Solo las camaras fuente, y sin la matriz: se trae aparte y solo si cambio (ver _CACHE_MATRICES).
        cur.execute("""SELECT mcc.camara_id, mcc.valor_maximo, mcc.total_detecciones, mcc.actualizado_en, c.nombre
                       FROM mapas_calor_camara mcc LEFT JOIN camaras c ON c.id = mcc.camara_id
                       WHERE mcc.camara_id = ANY(%s)""", (camaras_fuente,))
        filas = cur.fetchall()
        faltan = [r['camara_id'] for r in filas
                  if r['actualizado_en'] is None or _CACHE_MATRICES.get(r['camara_id'], (None,))[0] != r['actualizado_en']]
        matrices = {r['camara_id']: _CACHE_MATRICES[r['camara_id']][1] for r in filas if r['camara_id'] not in faltan}
        if faltan:
            cur.execute("SELECT camara_id, matriz FROM mapas_calor_camara WHERE camara_id = ANY(%s)", (faltan,))
            for m in cur.fetchall():
                matrices[m['camara_id']] = _poligono(m['matriz'])
            for r in filas:
                if r['camara_id'] in faltan and r['actualizado_en'] is not None and r['camara_id'] in matrices:
                    _CACHE_MATRICES[r['camara_id']] = (r['actualizado_en'], matrices[r['camara_id']])
        cur.execute("SELECT camara_id, nombre, tipo, poligono FROM zonas WHERE camara_id = ANY(%s) ORDER BY camara_id, id",
                    (camaras_fuente,))
        zonas = cur.fetchall()
        cur.close(); conn.close()

        camaras, info = {}, {}
        for r in filas:
            matriz = matrices.get(r['camara_id'])
            zs = [{'tipo': z['tipo'], 'poligono': _poligono(z['poligono'])}
                  for z in zonas if z['camara_id'] == r['camara_id']]
            if not matriz or not zs:
                continue
            camaras[r['camara_id']] = {'matriz': matriz, 'valor_maximo': r['valor_maximo'], 'zonas': zs}
            info[str(r['camara_id'])] = {
                'nombre': r['nombre'], 'total_detecciones': r['total_detecciones'],
                'actualizado_en': r['actualizado_en'].isoformat() if r['actualizado_en'] else None,
            }
        return jsonify({'zonas': calor_por_zona(camaras, fuentes), 'camaras': info})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── /heatmap/plano/tiempo y /plano/flujo ─────────────────────────────────────
# Las dos miran TODO el historial de trayectorias de las camaras fuente, que crece con cada video analizado.
# Antes traian cada punto a Python y lo agrupaban aca; ahora la base hace el filtro por zona y el agrupado
# (mismas reglas que celdas_por_zona y tramos_por_zona de plano_calor.py) y solo viaja el resultado, que es
# lo que se paga como egress de Supabase. La pertenencia a la zona usa el tipo 'polygon' de Postgres.

# Posiciones de trayectoria de las camaras fuente (%(camaras)s), en fraccion 0-1 del cuadro de su camara.
_SQL_PUNTOS = """SELECT sv.camara_id, t.persona_id, t.id, t.timestamp AS ts, t.timestamp::date AS dia,
                        EXTRACT(EPOCH FROM t.timestamp::time)::int AS seg,
                        t.centroide_x / COALESCE(sv.frame_w, 1920) AS xn,
                        t.centroide_y / COALESCE(sv.frame_h, 1080) AS yn
                 FROM trayectorias t
                 JOIN personas p ON p.id = t.persona_id
                 JOIN sesiones_video sv ON sv.id = p.sesion_id
                 WHERE sv.camara_id = ANY(%(camaras)s)
                   AND t.centroide_x IS NOT NULL AND t.centroide_y IS NOT NULL {extra}"""

# La zona de cada tipo de su camara fuente, en el orden de 'fuentes' (en /flujo, si dos zonas de la misma
# camara se pisan, gana la primera).
_SQL_ZONAS_FUENTE = """SELECT * FROM unnest(%(tipos)s::text[], %(cams)s::int[], %(polys)s::polygon[], %(diags)s::float8[])
                       WITH ORDINALITY AS f(tipo, camara_id, poly, diag, orden)"""

_SQL_DENTRO = "f.poly @> point(p.xn * 1920, p.yn * 1080)"   # 1920x1080 = ZONAS_REF


def _zonas_fuente(cur, fuentes):
    """(zonas_por_camara, parametros de _SQL_ZONAS_FUENTE) de las camaras fuente."""
    from .plano_calor import diagonal_zona, zona_fuente
    camaras = sorted(set(fuentes.values()))
    cur.execute("SELECT camara_id, tipo, poligono FROM zonas WHERE camara_id = ANY(%s) ORDER BY id", (camaras,))
    zonas_por_camara = {}
    for z in cur.fetchall():
        zonas_por_camara.setdefault(z['camara_id'], []).append({'tipo': z['tipo'], 'poligono': _poligono(z['poligono'])})
    params = {'camaras': camaras, 'tipos': [], 'cams': [], 'polys': [], 'diags': []}
    for tipo, cam in fuentes.items():
        zona = zona_fuente(zonas_por_camara, tipo, cam)
        if zona is not None:
            params['tipos'].append(tipo)
            params['cams'].append(cam)
            params['polys'].append('(' + ','.join(f'({float(x)},{float(y)})' for x, y in zona['poligono']) + ')')
            params['diags'].append(diagonal_zona(zona['poligono']))
    return zonas_por_camara, params


def _posiciones_por_dia(cur, params, extra=""):
    """{camara_id: {dia: posiciones}} de las camaras fuente (para contar los dias con actividad)."""
    cur.execute(f"SELECT camara_id, dia, COUNT(*) AS n FROM ({_SQL_PUNTOS.format(extra=extra)}) p GROUP BY camara_id, dia",
                params)
    por_dia = {}
    for r in cur.fetchall():
        por_dia.setdefault(r['camara_id'], {})[r['dia']] = r['n']
    return por_dia


def _version_trayectorias(cur):
    """Cuantas filas se agregaron, cambiaron o borraron en las tablas que leen /plano/tiempo y /plano/flujo,
    segun las estadisticas de Postgres. Si no cambio desde la ultima respuesta, los datos tampoco: se reusa
    la cacheada sin volver a consultarlos. None si no se puede leer (entonces se consulta igual)."""
    cur.execute("""SELECT SUM(n_tup_ins + n_tup_upd + n_tup_del) AS cambios FROM pg_stat_user_tables
                   WHERE relname IN ('trayectorias', 'personas', 'sesiones_video', 'zonas')""")
    fila = cur.fetchone()
    return fila['cambios'] if fila else None


def _respuesta_cacheada(cache, fuentes, calcular):
    """Respuesta de /plano/tiempo o /plano/flujo: la cacheada si es de hace menos de 2 minutos (y no se pidio
    ?refrescar=1) o si los datos no cambiaron desde entonces (ver _version_trayectorias); si no, la de
    calcular(cur, fuentes), que queda cacheada."""
    import time
    import psycopg2.extras
    clave = tuple(sorted(fuentes.items()))
    if request.args.get('refrescar') != '1' and cache['clave'] == clave and time.time() - cache['t'] < 120:
        return jsonify(cache['resp'])
    conn = _db_connect()
    if conn is None:
        return jsonify({'error': 'sin conexion a la BD'}), 503
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    version = _version_trayectorias(cur)
    if version is not None and cache['clave'] == clave and cache['version'] == version:
        resp = cache['resp']
    else:
        resp = calcular(cur, fuentes)
    cur.close(); conn.close()
    cache.update(t=time.time(), clave=clave, version=version, resp=resp)
    return jsonify(resp)


_CACHE_PLANO_TIEMPO = {"t": 0.0, "clave": None, "version": None, "resp": None}


@api_bp.route('/heatmap/plano/tiempo')
def heatmap_plano_tiempo():
    """Posiciones de trayectoria agrupadas por celda y bloque horario de 5 min, de TODOS los dias
    juntos, para cada tipo de zona y de su camara fuente (la misma que /heatmap/plano). El
    frontend reproduce con eso como se mueve el calor a lo largo de un dia tipico (promedio de
    todos los dias). ?fuentes= igual que /heatmap/plano. Se cachea 2 minutos: la consulta recorre
    todo el historial de las camaras fuente."""
    from .plano_calor import BLOQUE_SEG, armar_celdas, rango_horario

    def calcular(cur, fuentes):
        zonas_por_camara, params = _zonas_fuente(cur, fuentes)
        por_dia = _posiciones_por_dia(cur, params)
        # Las posiciones de cada camara fuente que caen en la zona de cada tipo, contadas por bloque de 5 min
        # y celda de la grilla de 64x64 (mismas cuentas que celdas_por_zona).
        cur.execute(f"""SELECT f.tipo, p.seg / %(bloque)s AS bloque,
                               LEAST(63, GREATEST(0, trunc(p.xn * 64)::int)) AS col,
                               LEAST(63, GREATEST(0, trunc(p.yn * 64)::int)) AS fila,
                               COUNT(*) AS n
                        FROM ({_SQL_PUNTOS.format(extra='')}) p
                        JOIN ({_SQL_ZONAS_FUENTE}) f ON f.camara_id = p.camara_id
                        WHERE {_SQL_DENTRO}
                        GROUP BY 1, 2, 3, 4""", {**params, 'bloque': BLOQUE_SEG})
        cuentas = {}
        for r in cur.fetchall():
            cuentas.setdefault(r['tipo'], {})[(r['bloque'], r['col'], r['fila'])] = r['n']
        zonas = armar_celdas(por_dia, cuentas, zonas_por_camara, fuentes)
        return {'rango': rango_horario(zonas), 'zonas': zonas}

    try:
        return _respuesta_cacheada(_CACHE_PLANO_TIEMPO, _fuentes_de_request(), calcular)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


_CACHE_PLANO_FLUJO = {"t": 0.0, "clave": None, "version": None, "resp": None}

# Parametros de tramos_por_zona que tambien usa la consulta de /plano/flujo.
HUECO_MAX_FLUJO_SEG, MIN_PUNTOS_FLUJO, DESPLAZAMIENTO_MIN_FLUJO = 60, 3, 0.15


@api_bp.route('/heatmap/plano/flujo')
def heatmap_plano_flujo():
    """Recorridos de CLIENTES (sin empleados) de las camaras fuente, de TODOS los dias juntos, partidos en
    tramos por zona y simplificados a pocos puntos -- el frontend los agrupa por ventana de tiempo y
    dibuja las rutas mas frecuentes en el croquis. Misma convencion de ?fuentes= que /heatmap/plano.
    Se cachea 2 minutos."""
    from .plano_calor import armar_tramos

    def calcular(cur, fuentes):
        zonas_por_camara, params = _zonas_fuente(cur, fuentes)
        por_dia = _posiciones_por_dia(cur, params, "AND NOT t.es_empleado")
        # Mismo corte que tramos_por_zona: cada posicion toma el tipo de la primera zona que la contiene; una
        # corrida nueva empieza al cambiar de tipo, al salir de las zonas o tras un hueco de mas de
        # HUECO_MAX_FLUJO_SEG. Solo viajan las corridas con chance de ser tramo (bastantes puntos y
        # desplazamiento); armar_tramos repite esos filtros y las simplifica. El 0.999 deja que el limite
        # exacto lo decida Python.
        cur.execute(f"""
            WITH f AS ({_SQL_ZONAS_FUENTE}),
            asignadas AS (
                SELECT p.camara_id, p.persona_id, p.id, p.ts, p.seg, p.xn, p.yn,
                       (SELECT f.tipo FROM f WHERE f.camara_id = p.camara_id AND {_SQL_DENTRO}
                        ORDER BY f.orden LIMIT 1) AS tipo
                FROM ({_SQL_PUNTOS.format(extra='AND NOT t.es_empleado')}) p
                WHERE p.camara_id = ANY(%(cams)s)
            ),
            marcadas AS (
                SELECT a.*, CASE WHEN a.tipo IS NOT NULL
                                  AND (LAG(a.tipo) OVER w IS DISTINCT FROM a.tipo OR a.seg - LAG(a.seg) OVER w > %(hueco)s)
                                 THEN 1 ELSE 0 END AS nueva
                FROM asignadas a
                WINDOW w AS (PARTITION BY a.camara_id, a.persona_id ORDER BY a.seg, a.ts, a.id)
            ),
            corridas AS (
                SELECT m.*, SUM(m.nueva) OVER (PARTITION BY m.camara_id, m.persona_id ORDER BY m.seg, m.ts, m.id
                                               ROWS UNBOUNDED PRECEDING) AS corrida
                FROM marcadas m
            ),
            medidas AS (
                SELECT c.*, COUNT(*) OVER r AS n,
                       FIRST_VALUE(c.xn) OVER r AS x0, FIRST_VALUE(c.yn) OVER r AS y0,
                       LAST_VALUE(c.xn) OVER r AS x1, LAST_VALUE(c.yn) OVER r AS y1
                FROM corridas c
                WHERE c.tipo IS NOT NULL
                WINDOW r AS (PARTITION BY c.camara_id, c.persona_id, c.corrida ORDER BY c.seg, c.ts, c.id
                             ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
            )
            SELECT m.camara_id, m.persona_id, m.corrida, m.tipo, m.seg, m.xn, m.yn
            FROM medidas m JOIN f ON f.tipo = m.tipo AND f.camara_id = m.camara_id
            WHERE m.n >= %(min_puntos)s AND f.diag > 0
              AND sqrt((m.x1 - m.x0) ^ 2 + (m.y1 - m.y0) ^ 2) >= %(desplazamiento)s * 0.999 * f.diag
            ORDER BY m.camara_id, m.persona_id, m.corrida, m.seg, m.ts, m.id""",
                    {**params, 'hueco': HUECO_MAX_FLUJO_SEG, 'min_puntos': MIN_PUNTOS_FLUJO,
                     'desplazamiento': DESPLAZAMIENTO_MIN_FLUJO})
        corridas, actual = [], None
        for r in cur.fetchall():
            clave = (r['camara_id'], r['persona_id'], r['corrida'])
            if clave != actual:
                corridas.append((r['tipo'], []))
                actual = clave
            corridas[-1][1].append((r['seg'], r['xn'], r['yn']))
        return {'zonas': armar_tramos(corridas, por_dia, zonas_por_camara, fuentes, desplazamiento_min=DESPLAZAMIENTO_MIN_FLUJO,
                                      min_puntos=MIN_PUNTOS_FLUJO)}

    try:
        return _respuesta_cacheada(_CACHE_PLANO_FLUJO, _fuentes_de_request(), calcular)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/cameras/<int:camara_id>/heatmaps')
def camera_heatmaps(camara_id):
    """Todos los heatmaps INDIVIDUALES (uno por sesion/video analizado, ver
    guardar_heatmap() en deteccion/persistencia.py) de una camara que caigan
    en un mismo dia calendario, ordenados cronologicamente -- para poder
    reproducir la evolucion del mapa de calor a lo largo del dia (analogo a
    /api/cameras/<id>/tracking para el mapa de trayectorias). 'fecha' (query
    param, YYYY-MM-DD) es opcional -- sin ella, se usa el dia mas reciente
    con heatmaps de esa camara. Tambien devuelve las fechas disponibles para
    armar el selector de dia en el frontend. Como esto consulta la BD en
    cada pedido, a medida que deteccion/main.py analiza mas videos y guarda
    mas heatmaps, aparecen solos en la respuesta -- no hace falta ningun
    paso manual para "sumarlos" a la camara/momento que corresponde."""
    try:
        import psycopg2.extras
        conn = _db_connect()
        if conn is None:
            return jsonify(None)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT DISTINCT periodo_inicio::date AS fecha
            FROM mapas_calor WHERE camara_id = %s
            ORDER BY fecha DESC
        """, (camara_id,))
        fechas = [r['fecha'].isoformat() for r in cur.fetchall()]
        if not fechas:
            cur.close(); conn.close()
            return jsonify(None)

        fecha_param = request.args.get('fecha')
        fecha = fecha_param if fecha_param in fechas else fechas[0]

        cur.execute("""
            SELECT mc.*, z.nombre AS zona_mas_caliente_nombre
            FROM mapas_calor mc
            LEFT JOIN zonas z ON z.id = mc.zona_id_mas_caliente
            WHERE mc.camara_id = %s AND mc.periodo_inicio::date = %s
            ORDER BY mc.periodo_inicio ASC
        """, (camara_id, fecha))
        rows = cur.fetchall()

        cur.execute("SELECT nombre FROM camaras WHERE id = %s", (camara_id,))
        cam_row = cur.fetchone()

        cur.close(); conn.close()

        def _iso(v):
            return v.isoformat() if v else None

        return jsonify({
            'camara_id':          camara_id,
            'camara_nombre':      cam_row['nombre'] if cam_row else None,
            'fecha':              fecha,
            'fechas_disponibles': fechas,
            'heatmaps': [{
                'id':                r['id'],
                'sesion_id':         r['sesion_id'],
                'periodo_inicio':    _iso(r['periodo_inicio']),
                'periodo_fin':       _iso(r['periodo_fin']),
                'imagen_url':        _imagen_url(r.get('imagen_path')),
                'punto_max_x':       r['punto_max_x'],
                'punto_max_y':       r['punto_max_y'],
                'valor_maximo':      r['valor_maximo'],
                'area_activa_pct':   r['area_activa_pct'],
                'concentracion':     r['concentracion'],
                'total_detecciones': r['total_detecciones'],
                'frames_procesados': r['frames_procesados'],
                'zona_mas_caliente': r['zona_mas_caliente_nombre'],
            } for r in rows],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Imagenes de heatmap guardadas en disco cuando Supabase Storage no respondio (ver
# _subir_o_guardar_local en deteccion/main.py): van en heatmaps_pendientes/, y las mas
# viejas quedaron sueltas en la raiz del proyecto. Solo se sirven esas: antes el endpoint
# entregaba cualquier archivo del proyecto, incluido el .env (DEF-002).
_HEATMAP_CARPETAS    = ('', 'heatmaps_pendientes')
_HEATMAP_EXTENSIONES = ('.png', '.jpg', '.jpeg', '.webp')


@api_bp.route('/heatmap/image/<path:filename>')
def serve_heatmap_image(filename):
    root    = os.path.dirname(BASE)   # proyecto raiz (un nivel arriba de frontend/)
    carpeta, nombre = os.path.split(os.path.normpath(filename).replace(os.sep, '/'))
    if carpeta not in _HEATMAP_CARPETAS or not nombre.lower().endswith(_HEATMAP_EXTENSIONES):
        return Response('Not Found', status=404)
    if not os.path.isfile(os.path.join(root, carpeta, nombre)):
        return Response('Not Found', status=404)
    return send_from_directory(os.path.join(root, carpeta), nombre)


@api_bp.route('/heatmap/fondo/<int:camara_id>')
def heatmap_fondo(camara_id):
    """Foto fija del local (fondo vacio) para esa camara, subida una unica vez
    a mano en frontend/fondos/camara_<id>.<ext> -- el frontend superpone el
    heatmap combinado (con canal alfa) arriba de esta imagen via CSS."""
    if not os.path.isdir(FONDOS_DIR):
        return Response('Not Found', status=404)
    for ext in ('jpg', 'jpeg', 'png', 'webp'):
        filename = f'camara_{camara_id}.{ext}'
        if os.path.isfile(os.path.join(FONDOS_DIR, filename)):
            return send_from_directory(FONDOS_DIR, filename)
    return Response('Not Found', status=404)

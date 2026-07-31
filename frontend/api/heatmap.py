"""Endpoints de mapas de calor (por sesion y acumulado por camara)."""
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


@api_bp.route('/heatmap/image/<path:filename>')
def serve_heatmap_image(filename):
    root     = os.path.dirname(BASE)   # proyecto raiz (un nivel arriba de frontend/)
    img_path = os.path.join(root, filename)
    if not os.path.isfile(img_path):
        return Response('Not Found', status=404)
    return send_from_directory(root, filename)


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

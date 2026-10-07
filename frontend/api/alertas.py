"""Endpoints de 'alertas' reales (tabla 'alertas', ver db/schema.sql y
deteccion/pipeline/eventos.py) -- reemplaza los datos mock de AlertsPage."""
import os

from flask import Response, jsonify, request, send_from_directory

from .blueprint import api_bp
from .db import CAMARAS_EXCLUIDAS_DE_CONTEO, _get_conn
from .paths import BASE
from .reportes import UMBRAL_HORAS_POSIBLE_EMPLEADO

# Solo 'posible_hurto' se genera hoy (ver Persistencia.guardar_evento) -- los
# demas tipos existen en el schema para alertas futuras (stock, colas, etc.)
# que todavia no tiene ningun modulo que las inserte.
_TITULOS = {
    'posible_hurto':        'Posible hurto detectado',
    'salida_sin_pagar':     'Salida sin pagar',
    'permanencia_excesiva': 'Permanencia excesiva',
    'zona_restringida':     'Zona restringida',
    'posible_empleado':     'Persona posiblemente empleada',
    'otro':                 'Alerta',
}
_SEVERIDADES = {
    'posible_hurto':        'critical',
    'salida_sin_pagar':     'critical',
    'permanencia_excesiva': 'warn',
    'zona_restringida':     'warn',
    'posible_empleado':     'warn',
    'otro':                 'info',
}

# Segundos de margen ANTES del momento exacto de la alerta para que el clip
# (ver /api/sessions/<id>/clip en video.py) arranque con un poco de contexto,
# no justo en el instante detectado -- mismo criterio que usa list_sessions()
# en video.py ("5 s antes del evento").
_MARGEN_CLIP_SEG = 8

# Carpeta (en la raiz del proyecto) donde deteccion/pipeline/evidencia.py guarda la evidencia cuando Supabase Storage
# no responde; sus rutas relativas se sirven bajo /api/evidencias/.
EVIDENCIAS_DIR = os.path.join(os.path.dirname(BASE), 'evidencias')


def _url_evidencia(ruta):
    """URL de un archivo de evidencia: las de Storage ya son URLs completas; las del respaldo local son rutas
    relativas a la carpeta 'evidencias/' y se sirven por /api/evidencias/."""
    if not ruta:
        return None
    return ruta if ruta.startswith(('http://', 'https://')) else f"/api/evidencias/{ruta.replace(chr(92), '/')}"


def _evidencia_para_front(evidencia):
    """Evidencia guardada (JSON) -> {video, frames:[{url, etiqueta, ts}]} con las URLs listas para el navegador,
    o None si la alerta no tiene evidencia (alertas viejas, de videos grabados, o la subida todavia no termino)."""
    if not evidencia or not evidencia.get('frames'):
        return None
    return {
        'video':  _url_evidencia(evidencia.get('video')),
        'frames': [{'url': _url_evidencia(f.get('url')), 'etiqueta': f.get('etiqueta', ''), 'ts': f.get('ts')}
                   for f in evidencia['frames']],
    }


def _alertas_posible_empleado(cur):
    """Alertas 'Persona posiblemente empleada': personas (por cliente_id real) con mas de UMBRAL_HORAS_POSIBLE_EMPLEADO
    detectadas en un mismo dia. No se guardan en 'alertas': se arman al consultar, a partir de las mismas visitas que
    usan los reportes, y el usuario las resuelve diciendo si es empleado o no (POST /personas/<id>/empleado). Las que
    ya resolvio quedan en la lista como 'resueltas'. Necesita personas.foto_url y personas.empleado_revisado (ver
    db/schema.sql); si todavia no existen, devuelve [] para no romper el resto de las alertas."""
    try:
        cur.execute("""
            SELECT raiz.id                                     AS cliente_id,
                   p.primera_deteccion::date                   AS fecha,
                   ROUND(SUM(v.duracion_seg) / 60)::int        AS minutos,
                   MIN(v.entrada)                              AS primera_hora,
                   MAX(v.salida)                               AS ultima_hora,
                   (ARRAY_AGG(sv.camara_id ORDER BY v.duracion_seg DESC))[1] AS camara_id,
                   COALESCE(raiz.foto_url,
                            (ARRAY_AGG(p.foto_url) FILTER (WHERE p.foto_url IS NOT NULL))[1]) AS foto_url,
                   raiz.empleado_revisado                      AS revisado,
                   raiz.es_empleado                            AS es_empleado
            FROM personas p
            JOIN visitas  v        ON v.persona_id = p.id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            JOIN personas raiz     ON raiz.id = COALESCE(p.cliente_id, p.id)
            WHERE sv.camara_id NOT IN %(excl)s
              AND (raiz.empleado_revisado = TRUE OR raiz.es_empleado = FALSE)
            GROUP BY raiz.id, p.primera_deteccion::date
            HAVING SUM(v.duracion_seg) >= %(umbral)s
            ORDER BY MAX(v.salida) DESC
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'umbral': UMBRAL_HORAS_POSIBLE_EMPLEADO * 3600})
        rows = cur.fetchall()
    except Exception:
        cur.connection.rollback()
        return []

    alertas = []
    for r in rows:
        horas, minutos = divmod(r['minutos'], 60)
        desc = (f"Estuvo {horas} h {minutos:02d} min en la tienda el {r['fecha']:%d/%m} "
                f"({r['primera_hora']:%H:%M}–{r['ultima_hora']:%H:%M}). Un cliente no suele quedarse tanto: "
                f"confirmá si es empleado para excluirlo de las métricas.")
        if r['revisado']:
            desc = "Marcada como empleada: excluida de las métricas." if r['es_empleado']                 else "Confirmada como cliente: sigue contando en las métricas."
        alertas.append({
            'id':          f"emp-{r['cliente_id']}-{r['fecha']:%Y%m%d}",
            'tipo':        'posible_empleado',
            'persona_id':  r['cliente_id'],
            'sev':         _SEVERIDADES['posible_empleado'],
            'title':       _TITULOS['posible_empleado'],
            'desc':        desc,
            'zone':        'Tienda',
            'secuencia':   [],
            'cam':         r['camara_id'],
            'ts':          int(r['ultima_hora'].timestamp() * 1000),
            'status':      'resolved' if r['revisado'] else 'open',
            'sesion_id':   None,
            'offset_seg':  0,
            'evidencia':   None,
            'foto':        _url_evidencia(r['foto_url']),
            'es_empleado': bool(r['es_empleado']),
            'minutos':     r['minutos'],
        })
    return alertas


@api_bp.route('/alertas')
def listar_alertas():
    """Alertas reales generadas por el pipeline (ver
    Persistencia.guardar_evento) -- hoy solo 'posible_hurto', insertado
    cuando eventos.clasificar_evento() da POSIBLE_HURTO. Se hace JOIN con
    'eventos' por (persona_id, timestamp) -- ambas filas se insertan en la
    MISMA llamada con el mismo timestamp calculado, asi que ese par identifica
    sin ambiguedad el evento que genero esta alerta puntual (una persona
    puede tener mas de una fila en 'eventos' si tuvo varias visitas)."""
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify([])

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT al.id, al.persona_id, al.tipo, al.timestamp, al.descripcion, al.resuelta,
                   p.sesion_id, sv.camara_id, sv.inicio AS sesion_inicio,
                   e.secuencia_zonas, al.evidencia
            FROM alertas al
            JOIN personas p ON p.id = al.persona_id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            LEFT JOIN eventos e ON e.persona_id = al.persona_id AND e.timestamp = al.timestamp
            ORDER BY al.timestamp DESC
        """)
        rows = cur.fetchall()
        extra = _alertas_posible_empleado(cur)
        cur.close(); conn.close()

        alertas = []
        for r in rows:
            zonas = r['secuencia_zonas'] or []
            zona = zonas[-1] if zonas else 'Desconocida'
            offset_seg = 0
            if r['sesion_inicio']:
                offset_seg = max(0, int((r['timestamp'] - r['sesion_inicio']).total_seconds()) - _MARGEN_CLIP_SEG)
            alertas.append({
                'id':          r['id'],
                'persona_id':  r['persona_id'],
                'sev':         _SEVERIDADES.get(r['tipo'], 'info'),
                'title':       _TITULOS.get(r['tipo'], 'Alerta'),
                'desc':        r['descripcion'] or '',
                'zone':        zona,
                'secuencia':   zonas,
                'cam':         r['camara_id'],
                'ts':          int(r['timestamp'].timestamp() * 1000),
                'status':      'resolved' if r['resuelta'] else 'open',
                'sesion_id':   r['sesion_id'],
                'offset_seg':  offset_seg,
                'evidencia':   _evidencia_para_front(r['evidencia']),
            })
        alertas.extend(extra)
        alertas.sort(key=lambda a: a['ts'], reverse=True)
        return jsonify(alertas)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/alertas/<int:alerta_id>/resolver', methods=['POST'])
def resolver_alerta(alerta_id):
    """Marca (o revierte) 'alertas.resuelta'. body opcional {"resuelta": bool},
    default true -- mismo patron que POST /personas/<id>/empleado."""
    body     = request.get_json(silent=True) or {}
    resuelta = bool(body.get('resuelta', True))
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'error': 'sin conexion a la base de datos'}), 503

        cur = conn.cursor()
        cur.execute("UPDATE alertas SET resuelta = %s WHERE id = %s", (resuelta, alerta_id))
        actualizado = cur.rowcount > 0
        conn.commit()
        cur.close(); conn.close()

        if not actualizado:
            return jsonify({'error': f'no existe alerta con id {alerta_id}'}), 404
        return jsonify({'id': alerta_id, 'resuelta': resuelta})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/evidencias/<path:filename>')
def servir_evidencia(filename):
    """Archivos de evidencia guardados en disco (respaldo cuando Storage no respondio). send_from_directory
    rechaza cualquier ruta que intente salir de la carpeta."""
    if not os.path.isfile(os.path.join(EVIDENCIAS_DIR, filename)):
        return Response('Not Found', status=404)
    return send_from_directory(EVIDENCIAS_DIR, filename)

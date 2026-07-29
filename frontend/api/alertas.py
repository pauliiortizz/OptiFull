"""Endpoints de 'alertas' reales (tabla 'alertas', ver db/schema.sql y
deteccion/pipeline/eventos.py) -- reemplaza los datos mock de AlertsPage."""
from flask import jsonify, request

from .blueprint import api_bp
from .db import _get_conn

# Solo 'posible_hurto' se genera hoy (ver Persistencia.guardar_evento) -- los
# demas tipos existen en el schema para alertas futuras (stock, colas, etc.)
# que todavia no tiene ningun modulo que las inserte.
_TITULOS = {
    'posible_hurto':        'Posible hurto detectado',
    'salida_sin_pagar':     'Salida sin pagar',
    'permanencia_excesiva': 'Permanencia excesiva',
    'zona_restringida':     'Zona restringida',
    'otro':                 'Alerta',
}
_SEVERIDADES = {
    'posible_hurto':        'critical',
    'salida_sin_pagar':     'critical',
    'permanencia_excesiva': 'warn',
    'zona_restringida':     'warn',
    'otro':                 'info',
}

# Segundos de margen ANTES del momento exacto de la alerta para que el clip
# (ver /api/sessions/<id>/clip en video.py) arranque con un poco de contexto,
# no justo en el instante detectado -- mismo criterio que usa list_sessions()
# en video.py ("5 s antes del evento").
_MARGEN_CLIP_SEG = 8


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
                   e.secuencia_zonas
            FROM alertas al
            JOIN personas p ON p.id = al.persona_id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            LEFT JOIN eventos e ON e.persona_id = al.persona_id AND e.timestamp = al.timestamp
            ORDER BY al.timestamp DESC
        """)
        rows = cur.fetchall()
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
            })
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

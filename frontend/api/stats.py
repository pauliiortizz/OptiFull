"""Calculo de KPIs de permanencia y endpoints basicos de personas."""
from flask import jsonify, request

from .blueprint import api_bp
from .db import cargar_csv, cargar_db, cargar_permanencias_db


def calcular_stats(rows, permanencias=None):
    """'rows' (una fila por aparicion/sesion) se usa para los conteos brutos
    (personas_totales/personas_unicas). 'permanencias' (una fila por cliente
    real, con la duracion YA sumada entre sesiones/huecos -- ver
    cargar_permanencias_db) se usa para las metricas de tiempo. Si no viene
    (fallback CSV, sin tabla 'visitas'), se recalcula sobre 'rows' tal cual,
    que en modo CSV ya es 1 fila = 1 persona."""
    base_permanencia = permanencias if permanencias is not None else rows
    duraciones = [r['duracion_min'] for r in base_permanencia]
    validas    = [d for d in duraciones if d > 0.5]   # filtra detecciones ruido

    ORDEN = ['< 1 min', '1-5 min', '5-15 min', '15-60 min', '> 1 hora']

    def bucket(d):
        s = d * 60
        if s < 60:  return '< 1 min'
        if d < 5:   return '1-5 min'
        if d < 15:  return '5-15 min'
        if d < 60:  return '15-60 min'
        return '> 1 hora'

    conteo = {b: 0 for b in ORDEN}
    for d in duraciones:
        conteo[bucket(d)] += 1

    return {
        'personas_totales':             len(rows),
        'personas_unicas':              len({r['cliente_id'] for r in rows}),
        'personas_validas':             len(validas),
        'permanencia_promedio_min':     round(sum(validas) / len(validas), 1) if validas else 0,
        'permanencia_maxima_min':       round(max(duraciones), 1) if duraciones else 0,
        'permanencia_minima_valida_min':round(min(validas), 1) if validas else 0,
        'distribucion': [{'rango': b, 'count': conteo[b]} for b in ORDEN],
    }


@api_bp.route('/stats')
def api_stats():
    rows   = cargar_db()
    fuente = 'db' if rows is not None else 'csv'
    if rows is None:
        try:
            rows = cargar_csv()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    permanencias = cargar_permanencias_db() if fuente == 'db' else None
    stats = calcular_stats(rows, permanencias)
    stats['fuente']                = fuente
    stats['tiempo_real_disponible'] = False
    return jsonify(stats)


@api_bp.route('/personas')
def api_personas():
    rows   = cargar_db()
    fuente = 'db' if rows is not None else 'csv'
    if rows is None:
        try:
            rows = cargar_csv()
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'fuente': fuente, 'registros': rows})


@api_bp.route('/personas/<int:cliente_id>/empleado', methods=['POST'])
def marcar_empleado(cliente_id):
    """Confirma (o revierte) manualmente que un cliente_id es personal del
    local. Se marca solo en la fila raiz de la cadena (id = cliente_id) --
    todas las consultas de estadisticas excluyen via esa fila, sin importar
    cuantas apariciones/sesiones tenga esa persona."""
    from .db import _get_conn

    body        = request.get_json(silent=True) or {}
    es_empleado = bool(body.get('es_empleado', True))
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'error': 'sin conexion a la base de datos'}), 503

        cur = conn.cursor()
        cur.execute("UPDATE personas SET es_empleado = %s WHERE id = %s", (es_empleado, cliente_id))
        actualizado = cur.rowcount > 0
        # trayectorias.es_empleado es una copia desnormalizada de esta misma
        # fila raiz (ver comentario en db/schema.sql) -- sin esto quedaria
        # desactualizada hasta la proxima corrida manual de
        # deteccion/mantenimiento/completar_es_empleado_trayectorias.py.
        cur.execute(
            "UPDATE trayectorias t SET es_empleado = %s "
            "FROM personas p WHERE t.persona_id = p.id "
            "AND COALESCE(p.cliente_id, p.id) = %s AND t.es_empleado != %s",
            (es_empleado, cliente_id, es_empleado)
        )
        conn.commit()
        cur.close(); conn.close()

        if not actualizado:
            return jsonify({'error': f'no existe persona con id {cliente_id}'}), 404
        return jsonify({'cliente_id': cliente_id, 'es_empleado': es_empleado})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

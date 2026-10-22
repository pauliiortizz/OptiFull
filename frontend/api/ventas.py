"""Endpoint GET /ventas: los tickets vendidos en caja (seccion Ventas del panel).

Un ticket es una fila de 'ventas' con sus productos en 'transacciones' (ver
db/schema.sql y POST /productos/venta). Las transacciones anteriores a la
tabla 'ventas' no tienen ticket: se muestran como un ticket de un solo
producto, sin numero y con el precio actual del producto (el de ese momento
no se guardaba).

Query params opcionales:
  desde, hasta  YYYY-MM-DD, inclusive, en hora de Argentina
  limite        cantidad maxima de tickets (los mas recientes), default 200
"""
from datetime import date

import psycopg2.extras
from flask import jsonify, request

from .blueprint import api_bp
from .productos import _get_conn, _release_conn

ZONA = 'America/Argentina/Cordoba'
LIMITE_DEFAULT, LIMITE_MAXIMO = 200, 1000


def _fecha(nombre):
    valor = request.args.get(nombre)
    return date.fromisoformat(valor) if valor else None


@api_bp.route('/ventas')
def ventas():
    try:
        desde, hasta = _fecha('desde'), _fecha('hasta')
        limite = min(max(int(request.args.get('limite', LIMITE_DEFAULT)), 1), LIMITE_MAXIMO)
    except ValueError:
        return jsonify({'error': 'parametros invalidos (fechas YYYY-MM-DD, limite numerico)'}), 400

    conn = _get_conn()
    if conn is None:
        return jsonify({'error': 'sin conexion a la base de datos'}), 503
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # t.timestamp es TIMESTAMP en UTC (NOW() de Supabase): AT TIME ZONE
        # 'UTC' lo pasa a TIMESTAMPTZ para compararlo con ventas.timestamp.
        cur.execute("""
            SELECT * FROM (
                SELECT COALESCE(t.venta_id, -t.id) AS ticket, t.venta_id, v.total,
                       COALESCE(v.timestamp, t.timestamp AT TIME ZONE 'UTC') AS fecha,
                       t.id AS linea, t.sku, p.nombre, t.cantidad,
                       COALESCE(t.precio_unitario, p.precio) AS precio_unitario
                FROM transacciones t
                LEFT JOIN ventas v ON v.id = t.venta_id
                LEFT JOIN productos p ON p.sku = t.sku
            ) x
            WHERE (%(desde)s::date IS NULL OR (fecha AT TIME ZONE %(zona)s)::date >= %(desde)s::date)
              AND (%(hasta)s::date IS NULL OR (fecha AT TIME ZONE %(zona)s)::date <= %(hasta)s::date)
            ORDER BY fecha DESC, ticket DESC, linea
        """, {'desde': desde, 'hasta': hasta, 'zona': ZONA})
        filas = cur.fetchall()
        cur.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        _release_conn(conn)

    tickets = {}
    for f in filas:
        t = tickets.get(f['ticket'])
        if t is None:
            if len(tickets) == limite:
                break
            t = tickets[f['ticket']] = {
                'id': f['venta_id'], 'fecha': f['fecha'].isoformat(),
                'total': None if f['total'] is None else float(f['total']), 'items': [],
            }
        precio = None if f['precio_unitario'] is None else float(f['precio_unitario'])
        t['items'].append({
            'sku': f['sku'], 'nombre': f['nombre'] or f['sku'], 'cantidad': f['cantidad'],
            'precio_unitario': precio,
            'subtotal': None if precio is None else round(precio * f['cantidad'], 2),
        })

    lista = list(tickets.values())
    for t in lista:
        if t['total'] is None:   # transaccion sin ticket: total con el precio actual
            t['total'] = round(sum(it['subtotal'] or 0 for it in t['items']), 2)
    facturado = round(sum(t['total'] for t in lista), 2)
    return jsonify({
        'ventas': lista,
        'resumen': {
            'tickets': len(lista),
            'total': facturado,
            'unidades': sum(it['cantidad'] for t in lista for it in t['items']),
            'ticket_promedio': round(facturado / len(lista), 2) if lista else 0,
        },
    })

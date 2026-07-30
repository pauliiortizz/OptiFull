"""
Endpoints del módulo de productos/caja.

Este proceso (Flask) y deteccion_productos/main.py (cámara + LLM) NO
se importan entre sí -- corren separados y se comunican solo a través
de la base de datos compartida (tabla caja_estado para la interacción
en vivo con la cajera; productos/transacciones para catálogo y
métricas). Mismo patrón que el resto de este paquete (ver db.py).

  GET  /productos/estado     -> qué está pasando ahora (nada / esperando
                                 decisión + qué mostrarle a la cajera)
  POST /productos/accion     -> la cajera confirma/elige/corrige/cancela
  GET  /productos/stock      -> catálogo + stock actual
  GET  /productos/metricas   -> KPIs para la tesis (ver README del módulo)
  POST /productos/iniciar    -> arranca deteccion_productos/main.py --web
  POST /productos/detener    -> pide que se detenga en un punto seguro
"""
import os
import subprocess
import sys

import psycopg2
import psycopg2.extras
from flask import jsonify, request

from .blueprint import api_bp
from .paths import BASE

DETECCION_PRODUCTOS_DIR = os.path.join(BASE, '..', 'deteccion_productos')

# Referencia al subproceso de deteccion_productos/main.py mientras está
# corriendo. Vive en memoria del proceso de Flask -- alcanza porque
# serve_dashboard.py corre con use_reloader=False (un solo proceso).
_proceso_caja = None


def _get_conn():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return psycopg2.connect(database_url, connect_timeout=3)


@api_bp.route('/productos/estado')
def estado():
    conn = _get_conn()
    if conn is None:
        return jsonify({'error': 'sin conexion a la base de datos'}), 503
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT estado, pendiente, actualizado_en FROM caja_estado WHERE id = 1")
        fila = cur.fetchone()
        cur.close(); conn.close()
        corriendo = _proceso_caja is not None and _proceso_caja.poll() is None
        return jsonify({
            'corriendo': corriendo,
            'estado': fila['estado'] if fila else 'inactivo',
            'pendiente': fila['pendiente'] if fila else None,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/productos/accion', methods=['POST'])
def accion():
    """Body esperado segun 'tipo' de lo que estaba pendiente:
      confirmar: {"accion": "confirmar", "cantidad": N} | {"accion": "cancelar"} | {"accion": "manual"}
      elegir:    {"accion": "elegir", "indice": I, "cantidad": N} | "cancelar" | "manual"
      manual:    {"accion": "cargar", "sku": "SKU010", "cantidad": N} | {"accion": "cancelar"}
    """
    respuesta = request.get_json(silent=True)
    if not respuesta:
        return jsonify({'error': 'body vacio o invalido'}), 400

    conn = _get_conn()
    if conn is None:
        return jsonify({'error': 'sin conexion a la base de datos'}), 503
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE caja_estado SET respuesta = %s, actualizado_en = NOW()
            WHERE id = 1 AND estado = 'esperando_decision'
        """, (psycopg2.extras.Json(respuesta),))
        aplicado = cur.rowcount > 0
        conn.commit()
        cur.close(); conn.close()
        if not aplicado:
            return jsonify({'error': 'no hay ninguna decision pendiente ahora mismo'}), 409
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/productos/stock')
def stock():
    conn = _get_conn()
    if conn is None:
        return jsonify({'error': 'sin conexion a la base de datos'}), 503
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT sku, nombre, marca, variante, tamano_valor, tamano_unidad,
                   categoria, cantidad, precio
            FROM productos ORDER BY nombre
        """)
        productos = cur.fetchall()
        cur.close(); conn.close()
        return jsonify({'productos': productos})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/productos/metricas')
def metricas():
    conn = _get_conn()
    if conn is None:
        return jsonify({'error': 'sin conexion a la base de datos'}), 503
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("SELECT COUNT(*) AS total FROM transacciones")
        total = cur.fetchone()['total']

        cur.execute("SELECT COALESCE(AVG(confianza_llm), 0) AS promedio FROM transacciones")
        confianza_promedio = round(float(cur.fetchone()['promedio']), 3)

        # Desglose por estado de matching: 'reconocido' = el LLM+matching
        # identifico solo, sin ambiguedad; 'confirmar' = hubo que elegir
        # entre candidatos. confirmado_por_cajera queda True siempre (ver
        # main.py: nunca se descuenta sin que la cajera confirme), asi que
        # esto es la senal real de "que tan solo" resolvio el sistema.
        cur.execute("""
            SELECT estado_matching, COUNT(*) AS cantidad
            FROM transacciones GROUP BY estado_matching
        """)
        por_estado = cur.fetchall()

        cur.execute("""
            SELECT sku, AVG(confianza_llm) AS confianza_promedio, COUNT(*) AS apariciones
            FROM transacciones
            GROUP BY sku
            ORDER BY confianza_promedio ASC
            LIMIT 10
        """)
        productos_problematicos = cur.fetchall()

        cur.close(); conn.close()
        return jsonify({
            'total_transacciones': total,
            'confianza_promedio': confianza_promedio,
            'por_estado_matching': por_estado,
            'productos_con_mas_problemas': productos_problematicos,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/productos/iniciar', methods=['POST'])
def iniciar():
    global _proceso_caja
    if _proceso_caja is not None and _proceso_caja.poll() is None:
        return jsonify({'error': 'la caja ya esta corriendo'}), 409

    body = request.get_json(silent=True) or {}
    source = body.get('source')
    if not source:
        # Default: la camara registrada como "Camara Caja" (ver
        # db/schema.sql, tabla camaras) -- en desarrollo se puede pasar
        # {"source": "data/videos/prueba.mp4"} en el body para probar con
        # un video en vez de la camara real.
        conn = _get_conn()
        if conn is None:
            return jsonify({'error': 'sin conexion a la base de datos'}), 503
        cur = conn.cursor()
        cur.execute("SELECT rtsp_url FROM camaras WHERE nombre = 'Camara Caja'")
        fila = cur.fetchone()
        cur.close(); conn.close()
        if not fila:
            return jsonify({'error': "no se especifico 'source' y no existe la camara 'Camara Caja'"}), 400
        source = fila[0]

    roi = body.get('roi')
    comando = [sys.executable, 'main.py', '--source', source, '--web']
    if roi:
        comando += ['--roi', roi]

    _proceso_caja = subprocess.Popen(comando, cwd=DETECCION_PRODUCTOS_DIR)
    return jsonify({'ok': True, 'pid': _proceso_caja.pid, 'source': source})


@api_bp.route('/productos/detener', methods=['POST'])
def detener():
    conn = _get_conn()
    if conn is None:
        return jsonify({'error': 'sin conexion a la base de datos'}), 503
    try:
        cur = conn.cursor()
        cur.execute("UPDATE caja_estado SET estado = 'detener', actualizado_en = NOW() WHERE id = 1")
        conn.commit()
        cur.close(); conn.close()
        return jsonify({'ok': True, 'aviso': 'se va a detener en el proximo punto seguro (hasta ~1-2s)'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

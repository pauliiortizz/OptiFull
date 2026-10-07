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
  GET  /productos/camara     -> reenvía al navegador el video de la cámara
                                 del celular (IP Camera Lite)
"""
import atexit
import base64
import ipaddress
import os
import subprocess
import sys
import urllib.parse
import urllib.request

import psycopg2
import psycopg2.extras
import psycopg2.pool
from flask import Response, jsonify, request

from .blueprint import api_bp
from .paths import BASE

DETECCION_PRODUCTOS_DIR = os.path.join(BASE, '..', 'deteccion_productos')

# Referencia al subproceso de deteccion_productos/main.py mientras está
# corriendo. Vive en memoria del proceso de Flask -- alcanza porque
# serve_dashboard.py corre con use_reloader=False (un solo proceso).
_proceso_caja = None


@atexit.register
def _matar_proceso_caja_al_salir():
    """Sin esto, si Flask se corta (Ctrl+C, crash, reinicio) mientras la
    caja esta corriendo, el subproceso de deteccion_productos/main.py queda
    HUERFANO: sigue vivo, sigue leyendo el video en loop y sigue escribiendo
    en caja_estado sin que nadie lo controle ni sepa que existe -- la
    proxima vez que se arranque Flask, _proceso_caja vuelve a None y no hay
    forma de detectar que ya hay uno corriendo por su cuenta. Terminarlo acá
    cierra ese agujero."""
    if _proceso_caja is not None and _proceso_caja.poll() is None:
        _proceso_caja.terminate()


_pool = None


def _get_pool():
    """Pool de conexiones a Postgres, creado una sola vez.

    Sin esto, cada request abria una conexion NUEVA a Supabase con
    psycopg2.connect() y la cerraba al terminar -- medido en vivo, ese
    handshake solo (TLS + auth, contra un Postgres en la nube) tarda
    ~1.3-1.5s, SIEMPRE, sin importar lo simple que sea la consulta.
    Para un sistema que se sondea cada 1-2s (ver ProductosPage.jsx) eso
    es inviable: cada poll pagaba de nuevo ese costo entero.
    Con el pool, unas pocas conexiones quedan abiertas de entrada y cada
    request pide prestada una (~0.3s, la query en si) en vez de abrir una
    nueva -- ver también threaded=True en serve_dashboard.py, necesario
    para que varias requests puedan usar el pool en paralelo."""
    global _pool
    if _pool is not None:
        return _pool
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    try:
        # 8s: el free tier de Supabase pausa el proyecto por inactividad y
        # el primer connect tras "despertarlo" puede tardar unos segundos.
        _pool = psycopg2.pool.ThreadedConnectionPool(
            1, 5, database_url, connect_timeout=8)
    except Exception:
        _pool = None
    return _pool


def _get_conn():
    pool = _get_pool()
    if pool is None:
        return None
    try:
        return pool.getconn()
    except Exception:
        # Si la conexion falla (timeout, credenciales, red), que devuelva
        # None en vez de dejar propagar la excepcion: cada endpoint ya
        # convierte 'conn is None' en un 503 con JSON {"error": "..."} --
        # sin este try/except, Flask respondia su pagina HTML generica de
        # error 500, que rompe cualquier fetch().then(r => r.json()) del
        # frontend (ver ProductosPage.jsx).
        return None


def _release_conn(conn):
    """Devuelve la conexion al pool en vez de cerrarla -- ver _get_pool."""
    pool = _get_pool()
    if pool is not None and conn is not None:
        try:
            pool.putconn(conn)
        except Exception:
            pass


@api_bp.route('/productos/estado')
def estado():
    conn = _get_conn()
    if conn is None:
        return jsonify({'error': 'sin conexion a la base de datos'}), 503
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT estado, pendiente, actualizado_en FROM caja_estado WHERE id = 1")
        fila = cur.fetchone()
        cur.close()
        corriendo = _proceso_caja is not None and _proceso_caja.poll() is None
        return jsonify({
            'corriendo': corriendo,
            'estado': fila['estado'] if fila else 'inactivo',
            'pendiente': fila['pendiente'] if fila else None,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Siempre devolver la conexion al pool, incluso si algo de arriba
        # tiro una excepcion -- si no, con solo 5 conexiones en el pool
        # (ver _get_pool), un puñado de errores lo dejaban agotado.
        _release_conn(conn)


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
        cur.close()
        if not aplicado:
            return jsonify({'error': 'no hay ninguna decision pendiente ahora mismo'}), 409
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        _release_conn(conn)


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
        cur.close()
        return jsonify({'productos': productos})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        _release_conn(conn)


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

        cur.close()
        return jsonify({
            'total_transacciones': total,
            'confianza_promedio': confianza_promedio,
            'por_estado_matching': por_estado,
            'productos_con_mas_problemas': productos_problematicos,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        _release_conn(conn)


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
        try:
            cur = conn.cursor()
            cur.execute("SELECT rtsp_url FROM camaras WHERE nombre = 'Camara Caja'")
            fila = cur.fetchone()
            cur.close()
        finally:
            _release_conn(conn)
        if not fila:
            return jsonify({'error': "no se especifico 'source' y no existe la camara 'Camara Caja'"}), 400
        source = fila[0]

    roi = body.get('roi')
    # -u: sin esto, al redirigir stdout a un archivo (ver log_file mas
    # abajo) Python bufferea todo y los prints no se ven hasta que el
    # buffer se llena o el proceso termina -- inutil para debuggear.
    comando = [sys.executable, '-u', 'main.py', '--source', source, '--web']
    if roi:
        comando += ['--roi', roi]

    # Log a archivo: sin esto, la salida de este subproceso (prints de
    # main.py, errores del VisionAgent/Claude, tracebacks) se pierde --
    # depende de donde y como se haya arrancado Flask, puede no ir a
    # ningun lado visible. caja.log queda en deteccion_productos/, al lado
    # de main.py, y se sobreescribe en cada arranque.
    log_path = os.path.join(DETECCION_PRODUCTOS_DIR, 'caja.log')
    log_file = open(log_path, 'w', encoding='utf-8')
    _proceso_caja = subprocess.Popen(
        comando, cwd=DETECCION_PRODUCTOS_DIR,
        stdout=log_file, stderr=subprocess.STDOUT)
    log_file.close()  # el hijo ya se quedo con su propia copia del handle
    return jsonify({'ok': True, 'pid': _proceso_caja.pid, 'source': source, 'log': log_path})


@api_bp.route('/productos/camara')
def camara():
    """Reenvía al navegador el video en vivo (MJPEG) de la cámara del celular.

    Hace falta pasar por acá porque la cámara pide usuario y contraseña
    (http://usuario:clave@IP:8081/video) y los navegadores bloquean las
    imágenes con credenciales dentro de la URL. Solo se aceptan IPs de red
    local: si no, este endpoint serviría para pedirle a nuestro servidor
    cualquier URL de internet."""
    partes = urllib.parse.urlsplit(request.args.get('url', ''))
    try:
        es_local = ipaddress.ip_address(partes.hostname or '').is_private
    except ValueError:
        es_local = False
    if partes.scheme != 'http' or not es_local:
        return jsonify({'error': 'solo se aceptan camaras de la red local (http://IP-local:puerto/...)'}), 400

    host = partes.hostname + (f':{partes.port}' if partes.port else '')
    pedido = urllib.request.Request(urllib.parse.urlunsplit(
        ('http', host, partes.path or '/', partes.query, '')))
    if partes.username:
        credenciales = f'{urllib.parse.unquote(partes.username)}:{urllib.parse.unquote(partes.password or "")}'
        pedido.add_header('Authorization', 'Basic ' + base64.b64encode(credenciales.encode()).decode())
    try:
        respuesta = urllib.request.urlopen(pedido, timeout=5)
    except Exception as e:
        return jsonify({'error': f'no se pudo conectar a la camara: {e}'}), 502

    def reenviar():
        try:
            while True:
                # read1: devuelve lo que ya llegó, sin esperar a juntar 64KB
                # (si no, cada cuadro se mostraría con retraso).
                bloque = respuesta.read1(64 * 1024)
                if not bloque:
                    break
                yield bloque
        finally:
            respuesta.close()

    return Response(reenviar(), content_type=respuesta.headers.get('Content-Type'))


@api_bp.route('/productos/detener', methods=['POST'])
def detener():
    conn = _get_conn()
    if conn is None:
        return jsonify({'error': 'sin conexion a la base de datos'}), 503
    try:
        cur = conn.cursor()
        cur.execute("UPDATE caja_estado SET estado = 'detener', actualizado_en = NOW() WHERE id = 1")
        conn.commit()
        cur.close()
        return jsonify({'ok': True, 'aviso': 'se va a detener en el proximo punto seguro (hasta ~1-2s)'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        _release_conn(conn)

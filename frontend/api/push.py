"""Notificaciones push (Web Push): las alertas llegan como notificacion del sistema operativo aunque el dashboard
este cerrado o el usuario este en otra pestana, como los mensajes de WhatsApp Web.

Como funciona:
  1. En Configuracion -> Notificaciones, cada navegador se suscribe (frontend/src/push.js): registra el service
     worker (frontend/public/sw.js), pide permiso y le manda a este backend su suscripcion (POST /push/suscripcion).
     Se guardan en la tabla 'push_suscripciones'.
  2. Cuando el detector en vivo guarda una alerta, avisa a POST /push/alerta (deteccion/pipeline/aviso_push.py).
     Este backend lee esa alerta de la base y se la manda a todas las suscripciones con pywebpush. El servicio de
     push del navegador (Google, Mozilla, Apple) la entrega y el service worker la muestra.
  3. El aviso sale del detector y no de una tarea periodica de este servidor: en el plan gratuito de Render el
     backend se duerme sin visitas, justo cuando hace falta avisar. El pedido del detector lo despierta.

Variables de entorno (ver db/generar_claves_push.py para crear las claves):
  VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY  par de claves del servidor (base64url). Sin ellas el push queda apagado.
  VAPID_SUBJECT                         contacto que piden los servicios de push (mailto:... o https://...)
  PUSH_TOKEN                            secreto compartido con el detector para POST /push/alerta

El switch "Notificaciones push" de Configuracion (configuracion.push) apaga o prende el envio para todos.
"""
import hmac
import json
import logging
import os

from flask import g, jsonify, request

from .blueprint import api_bp
from .configuracion import leer_configuracion
from .db import _get_conn

_log = logging.getLogger(__name__)

_CREAR_TABLA = """
    CREATE TABLE IF NOT EXISTS push_suscripciones (
        id          SERIAL     PRIMARY KEY,
        endpoint    TEXT       NOT NULL UNIQUE,
        p256dh      TEXT       NOT NULL,
        auth        TEXT       NOT NULL,
        usuario     TEXT,
        creado_en   TIMESTAMP  NOT NULL DEFAULT NOW()
    )"""

# Lo que se muestra en la notificacion para cada tipo de alerta guardada (los mismos titulos que alertas.py).
_TITULOS = {
    'posible_hurto':        'Posible hurto detectado',
    'salida_sin_pagar':     'Salida sin pagar',
    'permanencia_excesiva': 'Permanencia excesiva',
    'zona_restringida':     'Zona restringida',
}
_TTL_SEG = 3600   # si el navegador esta apagado, el servicio de push guarda la notificacion hasta 1 h
_LARGO_MAX_CAMPO = 1000


def _claves():
    publica, privada = os.environ.get('VAPID_PUBLIC_KEY'), os.environ.get('VAPID_PRIVATE_KEY')
    return (publica, privada) if publica and privada else (None, None)


def _crear_tabla(cur):
    cur.execute(_CREAR_TABLA)


def _suscripcion_valida(datos):
    """{endpoint, keys: {p256dh, auth}} tal como lo da PushSubscription.toJSON() en el navegador, o None."""
    if not isinstance(datos, dict):
        return None
    endpoint, claves = datos.get('endpoint'), datos.get('keys') or {}
    campos = (endpoint, claves.get('p256dh'), claves.get('auth'))
    if not all(isinstance(c, str) and 0 < len(c) <= _LARGO_MAX_CAMPO for c in campos):
        return None
    if not endpoint.startswith('https://'):
        return None
    return {'endpoint': endpoint, 'p256dh': claves['p256dh'], 'auth': claves['auth']}


def _enviar(suscripcion, mensaje):
    """Manda 'mensaje' (dict) a una suscripcion. Devuelve 'ok', 'vencida' (el navegador la dio de baja: hay que
    borrarla) o 'error'."""
    from pywebpush import WebPushException, webpush
    _, privada = _claves()
    try:
        webpush(
            subscription_info={'endpoint': suscripcion['endpoint'],
                               'keys': {'p256dh': suscripcion['p256dh'], 'auth': suscripcion['auth']}},
            data=json.dumps(mensaje, ensure_ascii=False),
            vapid_private_key=privada,
            vapid_claims={'sub': os.environ.get('VAPID_SUBJECT', 'https://optifull.onrender.com')},
            ttl=_TTL_SEG, timeout=10,
        )
        return 'ok'
    except WebPushException as e:
        estado = getattr(e.response, 'status_code', None)
        if estado in (404, 410):
            return 'vencida'
        _log.warning('No se pudo enviar el push (%s): %s', estado, e)
        return 'error'
    except Exception as e:   # red caida, clave mal cargada, etc.: no tiene que romper el endpoint
        _log.warning('No se pudo enviar el push: %s', e)
        return 'error'


def _enviar_a(cur, suscripciones, mensaje):
    """Envia a cada suscripcion y borra las vencidas. Devuelve cuantas recibieron el mensaje."""
    enviadas, vencidas = 0, []
    for s in suscripciones:
        resultado = _enviar(s, mensaje)
        enviadas += resultado == 'ok'
        if resultado == 'vencida':
            vencidas.append(s['endpoint'])
    if vencidas:
        cur.execute("DELETE FROM push_suscripciones WHERE endpoint = ANY(%s)", (vencidas,))
    return enviadas


def _filas(cur):
    return [{'endpoint': f[0], 'p256dh': f[1], 'auth': f[2]} if not isinstance(f, dict) else f
            for f in cur.fetchall()]


def _con_base(trabajo):
    """Corre trabajo(cur) con una conexion propia (crea la tabla si falta) y responde 503 si no hay base."""
    conn = _get_conn()
    if conn is None:
        return jsonify({'error': 'sin conexion a la BD'}), 503
    try:
        cur = conn.cursor()
        _crear_tabla(cur)
        respuesta = trabajo(cur)
        conn.commit()
        cur.close()
        return respuesta
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@api_bp.route('/push/clave')
def push_clave():
    """Clave publica VAPID que el navegador necesita para suscribirse."""
    publica, _ = _claves()
    if not publica:
        return jsonify({'error': 'Las notificaciones push no están configuradas en el servidor.'}), 503
    return jsonify({'clave': publica})


@api_bp.route('/push/suscripcion', methods=['POST'])
def push_suscribir():
    suscripcion = _suscripcion_valida(request.get_json(silent=True))
    if suscripcion is None:
        return jsonify({'error': 'suscripción inválida'}), 400
    usuario = (getattr(g, 'usuario', None) or {}).get('usuario')

    def guardar(cur):
        cur.execute("""
            INSERT INTO push_suscripciones (endpoint, p256dh, auth, usuario) VALUES (%s, %s, %s, %s)
            ON CONFLICT (endpoint) DO UPDATE SET p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth,
                                                 usuario = EXCLUDED.usuario""",
                    (suscripcion['endpoint'], suscripcion['p256dh'], suscripcion['auth'], usuario))
        return jsonify({'ok': True}), 201
    return _con_base(guardar)


@api_bp.route('/push/suscripcion', methods=['DELETE'])
def push_desuscribir():
    endpoint = (request.get_json(silent=True) or {}).get('endpoint')
    if not isinstance(endpoint, str) or not endpoint:
        return jsonify({'error': 'falta el endpoint'}), 400

    def borrar(cur):
        cur.execute("DELETE FROM push_suscripciones WHERE endpoint = %s", (endpoint,))
        return jsonify({'ok': True})
    return _con_base(borrar)


@api_bp.route('/push/prueba', methods=['POST'])
def push_prueba():
    """Manda una notificacion de prueba solo al navegador que la pide (su endpoint ya tiene que estar guardado)."""
    if not _claves()[0]:
        return jsonify({'error': 'Las notificaciones push no están configuradas en el servidor.'}), 503
    endpoint = (request.get_json(silent=True) or {}).get('endpoint')
    if not isinstance(endpoint, str) or not endpoint:
        return jsonify({'error': 'falta el endpoint'}), 400

    def probar(cur):
        cur.execute("SELECT endpoint, p256dh, auth FROM push_suscripciones WHERE endpoint = %s", (endpoint,))
        suscripciones = _filas(cur)
        if not suscripciones:
            return jsonify({'error': 'Este navegador no está suscripto.'}), 404
        enviadas = _enviar_a(cur, suscripciones, {
            'titulo': 'Notificaciones de OptiFull activadas',
            'cuerpo': 'Así vas a ver las alertas de la tienda, aunque tengas el dashboard cerrado.',
            'url': '/alertas', 'tag': 'optifull-prueba',
        })
        if not enviadas:
            return jsonify({'error': 'El servicio de notificaciones del navegador no aceptó el envío.'}), 502
        return jsonify({'ok': True})
    return _con_base(probar)


@api_bp.route('/push/alerta', methods=['POST'])
def push_alerta():
    """Lo llama el detector al guardar una alerta (deteccion/pipeline/aviso_push.py). Publico para la sesion
    (sesion.PUBLICOS) pero exige PUSH_TOKEN; ademas el texto sale de la base, no del pedido."""
    token = os.environ.get('PUSH_TOKEN')
    recibido = request.headers.get('X-Push-Token', '')
    if not token or not hmac.compare_digest(recibido.encode(), token.encode()):
        return jsonify({'error': 'no autorizado'}), 403
    alerta_id = (request.get_json(silent=True) or {}).get('alerta_id')
    if not isinstance(alerta_id, int) or isinstance(alerta_id, bool):
        return jsonify({'error': 'falta alerta_id'}), 400
    if not _claves()[0]:
        return jsonify({'enviadas': 0, 'motivo': 'push sin configurar'})

    def avisar(cur):
        if not leer_configuracion(cur).get('push', True):
            return jsonify({'enviadas': 0, 'motivo': 'push desactivado en Configuración'})
        cur.execute("SELECT tipo, descripcion FROM alertas WHERE id = %s", (alerta_id,))
        fila = cur.fetchone()
        if not fila:
            return jsonify({'error': 'alerta inexistente'}), 404
        tipo, descripcion = (fila['tipo'], fila['descripcion']) if isinstance(fila, dict) else fila
        cur.execute("SELECT endpoint, p256dh, auth FROM push_suscripciones")
        enviadas = _enviar_a(cur, _filas(cur), {
            'titulo': _TITULOS.get(tipo, 'Nueva alerta en la tienda'),
            'cuerpo': (descripcion or 'Abrí OptiFull para ver el detalle.')[:200],
            'url': '/alertas', 'tag': f'optifull-alerta-{alerta_id}',
        })
        return jsonify({'enviadas': enviadas})
    return _con_base(avisar)

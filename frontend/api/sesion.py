"""Sesion del lado del servidor: todos los endpoints de la API piden una sesion iniciada (DEF-004).

Antes el login existia solo en el frontend (guardaba el usuario en el navegador) y el backend no verificaba
nada: cualquiera con la URL podia leer estadisticas, personas y alertas, o descontar stock.

Al iniciar sesion (POST /api/login) el servidor deja una cookie 'optifull_sesion' firmada con SECRET_KEY:
  - HttpOnly: el JavaScript de la pagina no la puede leer (no se la lleva un XSS).
  - SameSite=Lax: el navegador no la manda en POST desde otros sitios (protege contra CSRF).
  - Secure en QA y produccion (solo viaja por HTTPS).
El navegador la manda solo en cada pedido, incluidas las imagenes y videos (<img>/<video src="/api/...">),
que no pueden mandar un header Authorization.

  GET  /api/sesion  -> usuario de la sesion actual (401 si no hay o vencio)
  POST /api/logout  -> borra la cookie
"""
import logging
import os
import secrets

from flask import g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .blueprint import api_bp

COOKIE = 'optifull_sesion'
DURACION_SEG = 12 * 3600                 # sesion normal: 12 h (una jornada)
DURACION_MANTENER_SEG = 30 * 24 * 3600   # "Mantener sesion iniciada": 30 dias

# Endpoints que no piden sesion (nombre de la funcion de Flask, sin el prefijo 'api.'):
#   login/logout/sesion -> para poder entrar y salir
#   health              -> lo consultan Render y el pipeline
#   crear_lead          -> formulario de la landing (visitantes sin cuenta)
#   api_stats, heatmap_camara, serve_heatmap_image -> los numeros y el mapa de calor que muestra la landing
PUBLICOS = {'login', 'logout', 'sesion_actual', 'health', 'crear_lead',
            'api_stats', 'heatmap_camara', 'serve_heatmap_image'}

_log = logging.getLogger(__name__)


def _clave_secreta():
    clave = os.environ.get('SECRET_KEY')
    if clave:
        return clave
    # Sin SECRET_KEY se usa una clave al azar: funciona, pero las sesiones se pierden cada vez que el
    # servidor se reinicia (y no se comparten entre procesos). En QA/produccion hay que configurarla.
    _log.warning('SECRET_KEY no configurada: se usa una clave temporal (las sesiones se pierden al reiniciar)')
    return secrets.token_hex(32)


_firmador = URLSafeTimedSerializer(_clave_secreta(), salt='optifull-sesion')


def _cookie_segura():
    return os.environ.get('APP_ENV') in ('qa', 'production')


def iniciar(respuesta, usuario: dict, mantener: bool):
    """Agrega la cookie de sesion a 'respuesta'. 'usuario' trae id, usuario y rol."""
    datos = {'id': usuario['id'], 'usuario': usuario['usuario'], 'rol': usuario['rol'],
             'dur': DURACION_MANTENER_SEG if mantener else DURACION_SEG}
    respuesta.set_cookie(
        COOKIE, _firmador.dumps(datos),
        max_age=DURACION_MANTENER_SEG if mantener else None,   # sin max_age: se borra al cerrar el navegador
        httponly=True, samesite='Lax', secure=_cookie_segura(), path='/')
    return respuesta


def usuario_de_request():
    """Usuario de la cookie del pedido actual, o None si no hay, esta adulterada o vencio."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        datos = _firmador.loads(token, max_age=DURACION_MANTENER_SEG)
        _firmador.loads(token, max_age=datos.get('dur', DURACION_SEG))   # cada sesion vence segun como se inicio
    except (BadSignature, SignatureExpired):
        return None
    return datos


@api_bp.before_request
def exigir_sesion():
    nombre = (request.endpoint or '').rpartition('.')[2]
    if nombre in PUBLICOS:
        return None
    usuario = usuario_de_request()
    if usuario is None:
        return jsonify({'error': 'Iniciá sesión para continuar.'}), 401
    g.usuario = usuario
    return None


@api_bp.route('/sesion')
def sesion_actual():
    usuario = usuario_de_request()
    if usuario is None:
        return jsonify({'error': 'Iniciá sesión para continuar.'}), 401
    return jsonify({'usuario': usuario['usuario'], 'rol': usuario['rol']})


@api_bp.route('/logout', methods=['POST'])
def logout():
    respuesta = jsonify({'ok': True})
    respuesta.delete_cookie(COOKIE, path='/', httponly=True, samesite='Lax', secure=_cookie_segura())
    return respuesta

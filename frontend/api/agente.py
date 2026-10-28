"""Agente local: deja usar la camara del celular desde el panel de produccion (Render).

El panel de produccion corre en internet y la camara del celular esta en la red local de la caja: Render no la
puede alcanzar (por eso /api/productos/camara no existe en la nube, DEF-023). Pero el panel se abre en la compu
de la caja, la misma que esta conectada al celular. Ese navegador si puede hablar con esta compu en
http://127.0.0.1:8080, asi que el backend local (serve_dashboard.py) le ofrece al panel de produccion lo que
necesita del local:

  GET  /agente/estado           -> {"agente": true, "corriendo": bool}  (el panel lo usa para saber si esta)
  GET  /agente/camara?url=...   -> video del celular (el mismo proxy que /api/productos/camara)
  POST /agente/iniciar          -> lanza el detector de productos (el mismo de /api/productos/iniciar)
  POST /agente/detener          -> lo detiene
  GET  /agente/videos           -> videos de prueba de esta compu
  GET  /agente/video/<archivo>  -> uno de esos videos

El video va del celular a esta compu y de aca a la pantalla, sin pasar por internet: se ve igual de fluido que
en local. Las decisiones (producto detectado, confirmar, venta) siguen yendo por Supabase, que es la misma base
que lee produccion.

No pide sesion: la cookie de produccion no viaja a 127.0.0.1. En su lugar:
  - no existe en la nube (APP_ENV qa/production);
  - solo atiende pedidos de esta misma compu (no de otros equipos de la red, como el celular del hotspot);
  - solo con Host 127.0.0.1/localhost (un sitio que apunte su dominio a 127.0.0.1 no lo puede usar);
  - las ordenes (POST) solo pueden venir de las paginas de AGENTE_ORIGENES (produccion y QA): el navegador
    manda el Origin y CORS no deja leer la respuesta a ningun otro sitio.
"""
import os
import urllib.parse

from flask import Blueprint, jsonify, request

from . import productos, video
from .seguridad import en_la_nube

agente_bp = Blueprint('agente', __name__, url_prefix='/agente')

ORIGENES_DEFAULT = 'https://optifull.onrender.com,https://optifull-qa.onrender.com'
HOSTS_LOCALES = {'127.0.0.1', 'localhost', '::1'}
IPS_LOCALES = {'127.0.0.1', '::1'}


def origenes_permitidos():
    valor = os.environ.get('AGENTE_ORIGENES', ORIGENES_DEFAULT)
    return {o.strip().rstrip('/') for o in valor.split(',') if o.strip()}


def _host_local():
    return urllib.parse.urlsplit('//' + (request.host or '')).hostname in HOSTS_LOCALES


@agente_bp.before_request
def proteger():
    if en_la_nube():
        return jsonify({'error': 'no disponible'}), 404
    if request.remote_addr not in IPS_LOCALES or not _host_local():
        return jsonify({'error': 'el agente solo atiende pedidos de esta compu'}), 403
    origen = request.headers.get('Origin')
    if request.method in ('POST', 'OPTIONS') and origen not in origenes_permitidos():
        return jsonify({'error': 'origen no permitido'}), 403
    if request.method == 'OPTIONS':        # preflight de CORS (POST con JSON): las cabeceras van en after_request
        return '', 204
    return None


@agente_bp.after_request
def cors(respuesta):
    origen = request.headers.get('Origin')
    if origen in origenes_permitidos():
        respuesta.headers['Access-Control-Allow-Origin'] = origen
        respuesta.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        respuesta.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        # Chrome pide este permiso para que una pagina publica hable con la red local (Private Network Access)
        respuesta.headers['Access-Control-Allow-Private-Network'] = 'true'
        respuesta.headers['Access-Control-Max-Age'] = '600'
        respuesta.headers['Vary'] = 'Origin'
    return respuesta


@agente_bp.route('/estado', methods=['GET', 'OPTIONS'])
def estado():
    proceso = productos._proceso_caja
    return jsonify({'agente': True, 'corriendo': proceso is not None and proceso.poll() is None})


@agente_bp.route('/iniciar', methods=['POST', 'OPTIONS'])
def iniciar():
    return productos.iniciar()


@agente_bp.route('/detener', methods=['POST', 'OPTIONS'])
def detener():
    return productos.detener()


@agente_bp.route('/camara', methods=['GET', 'OPTIONS'])
def camara():
    return productos.camara()


@agente_bp.route('/videos', methods=['GET', 'OPTIONS'])
def videos():
    return video.list_videos()


@agente_bp.route('/video/<path:filename>', methods=['GET', 'OPTIONS'])
def un_video(filename):
    return video.serve_video(filename)

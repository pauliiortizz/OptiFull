"""Endpoint POST /api/login: inicio de sesion contra la tabla 'usuarios' (ver db/schema.sql).

Reglas:
  - El usuario puede ingresar con su 'usuario' o con su 'email' (no distingue mayusculas).
  - Campo vacio -> 400 con un mensaje por campo ({'campos': {'usuario': ..., 'clave': ...}}).
  - Usuario inexistente, clave incorrecta o cuenta desactivada -> el MISMO 401 y el MISMO mensaje, para que nadie
    pueda averiguar que usuarios existen. Cuando el usuario no existe igual se verifica una clave contra un hash de
    relleno, asi el tiempo de respuesta tampoco delata nada.
  - Tras LIMITE_FALLOS intentos fallidos seguidos de un mismo usuario se bloquea durante BLOQUEO_SEG (429), incluso
    con la clave correcta. El contador vive en memoria del proceso (si hay varios procesos, cada uno cuenta aparte).
  - Sin conexion a la base -> 503. Nunca se devuelve el hash de la clave.
"""
import math
import threading
import time

from flask import jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from .blueprint import api_bp
from .db import _get_conn

LIMITE_FALLOS = 5
BLOQUEO_SEG = 300
CLAVE_MINIMA = 8          # largo minimo al CREAR una clave (el registro de usuarios lo va a exigir)
_MAX_USUARIO = 120
_MAX_CLAVE = 200
_MAX_REGISTROS = 5000     # tope de usuarios distintos recordados por el limitador (evita crecer sin limite)

MSG_USUARIO_VACIO = 'Completá el usuario o el email.'
MSG_CLAVE_VACIA = 'Completá la contraseña.'
MSG_INVALIDO = 'El email, el usuario o la contraseña son incorrectos.'
MSG_SIN_SERVIDOR = 'No se pudo conectar con el servidor. Probá de nuevo en un momento.'

_ahora = time.monotonic
_lock = threading.Lock()
_intentos: dict = {}      # usuario en minusculas -> {'fallos': int, 'hasta': float}


def hashear_clave(clave: str) -> str:
    """Hash con sal (pbkdf2-sha256) para guardar en usuarios.clave_hash. La clave nunca se guarda en texto plano."""
    return generate_password_hash(clave, method='pbkdf2:sha256')


def verificar_clave(clave: str, clave_hash: str) -> bool:
    return check_password_hash(clave_hash, clave)


# Hash de relleno: se usa para gastar el mismo tiempo cuando el usuario no existe.
_HASH_RELLENO = hashear_clave('relleno-sin-usuario')


def _segundos_bloqueado(clave_usuario: str) -> int:
    with _lock:
        reg = _intentos.get(clave_usuario)
        if not reg:
            return 0
        resto = reg['hasta'] - _ahora()
        if resto <= 0:
            if reg['hasta']:
                _intentos.pop(clave_usuario, None)   # el bloqueo ya vencio: se empieza de cero
            return 0
        return math.ceil(resto)


def _registrar_fallo(clave_usuario: str) -> None:
    with _lock:
        if len(_intentos) >= _MAX_REGISTROS:
            ahora = _ahora()
            for k in [k for k, v in _intentos.items() if v['hasta'] and v['hasta'] <= ahora]:
                _intentos.pop(k, None)
        reg = _intentos.setdefault(clave_usuario, {'fallos': 0, 'hasta': 0.0})
        reg['fallos'] += 1
        if reg['fallos'] >= LIMITE_FALLOS:
            reg['hasta'] = _ahora() + BLOQUEO_SEG


def _limpiar_fallos(clave_usuario: str) -> None:
    with _lock:
        _intentos.pop(clave_usuario, None)


def reiniciar_limitador() -> None:
    """Solo para las pruebas automaticas."""
    with _lock:
        _intentos.clear()


def _invalido():
    return jsonify({'ok': False, 'error': MSG_INVALIDO}), 401


@api_bp.route('/login', methods=['POST'])
def login():
    d = request.get_json(silent=True) or {}
    usuario = str(d.get('usuario') or '').strip()
    clave = str(d.get('clave') or '')

    campos = {}
    if not usuario:
        campos['usuario'] = MSG_USUARIO_VACIO
    if not clave:
        campos['clave'] = MSG_CLAVE_VACIA
    if campos:
        return jsonify({'ok': False, 'error': next(iter(campos.values())), 'campos': campos}), 400

    clave_usuario = usuario.lower()
    resto = _segundos_bloqueado(clave_usuario)
    if resto:
        minutos = max(1, -(-resto // 60))
        return jsonify({
            'ok': False, 'bloqueado': True, 'reintentar_en': resto,
            'error': f"Demasiados intentos fallidos. Probá de nuevo en {minutos} minuto{'s' if minutos != 1 else ''}.",
        }), 429

    if len(usuario) > _MAX_USUARIO or len(clave) > _MAX_CLAVE:
        _registrar_fallo(clave_usuario)
        return _invalido()

    conn = None
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'ok': False, 'error': MSG_SIN_SERVIDOR}), 503
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT u.id, u.usuario, u.email, u.nombre, u.clave_hash, u.activo, u.cargo, r.nombre AS rol
            FROM usuarios u JOIN roles r ON r.id = u.rol_id
            WHERE LOWER(u.usuario) = LOWER(%(u)s) OR LOWER(u.email) = LOWER(%(u)s)
            ORDER BY (LOWER(u.usuario) = LOWER(%(u)s)) DESC
            LIMIT 1
        """, {'u': usuario})
        fila = cur.fetchone()

        # Siempre se verifica una clave (la real o la de relleno): mismo tiempo exista o no el usuario.
        clave_ok = verificar_clave(clave, fila['clave_hash'] if fila else _HASH_RELLENO)
        if not (fila and clave_ok and fila['activo']):
            _registrar_fallo(clave_usuario)
            cur.close()
            return _invalido()

        cur.execute("""
            SELECT s.id, s.nombre, s.localidad
            FROM usuarios_sucursales us JOIN sucursales s ON s.id = us.sucursal_id
            WHERE us.usuario_id = %s AND s.activa
            ORDER BY s.nombre
        """, (fila['id'],))
        sucursales = [dict(s) for s in cur.fetchall()]
        cur.execute("UPDATE usuarios SET ultimo_acceso = NOW() WHERE id = %s", (fila['id'],))
        conn.commit()
        cur.close()
    except Exception:
        return jsonify({'ok': False, 'error': MSG_SIN_SERVIDOR}), 503
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    _limpiar_fallos(clave_usuario)
    return jsonify({
        'ok': True,
        'usuario': fila['usuario'],
        'nombre': fila['nombre'],
        'email': fila['email'],
        'rol': fila['rol'],
        'cargo': fila['cargo'],
        'sucursales': sucursales,
    })

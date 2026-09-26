"""Endpoint de salud (/api/health) usado por Render (healthCheckPath) y por el
pipeline de CI/CD para saber que version esta corriendo y si llega a la BD."""
import os

from flask import jsonify

from .blueprint import api_bp
from .db import _get_conn


def _db_ok():
    conn = _get_conn()
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        return True
    except Exception:
        return False
    finally:
        conn.close()


@api_bp.route('/health')
def health():
    """Liveness: siempre 200 mientras el proceso responda (asi Render no
    reinicia el servicio por un corte puntual de la BD). El estado de la BD
    va en el body ('db': 'ok' | 'error') y lo verifican los tests de
    integracion. 'commit' lo inyecta Render (RENDER_GIT_COMMIT) y el
    pipeline lo compara contra el SHA desplegado."""
    return jsonify({
        'status': 'ok',
        'db':     'ok' if _db_ok() else 'error',
        'commit': os.environ.get('RENDER_GIT_COMMIT') or os.environ.get('GIT_COMMIT'),
        'env':    os.environ.get('APP_ENV', 'local'),
    })

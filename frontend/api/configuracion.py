"""Endpoint /api/configuracion: lo que se guarda desde la pagina Configuracion del dashboard.

Hoy son el umbral de alertas (espera maxima en caja, en minutos), los datos de la
sucursal y si estan activadas las notificaciones push. Se guardan en la tabla 'configuracion' (una sola fila, ver
db/schema.sql); si la base no responde se usan los valores por defecto. Las alertas de espera en caja de
/api/alertas (alertas.py) leen el umbral de aca.
"""
import json

from flask import jsonify, request

from .blueprint import api_bp
from .db import _get_conn

# Rangos validos -- los mismos que LIMITES_UMBRALES en frontend/src/pages/PagesHeatmapCameras.jsx
LIMITES_UMBRALES = {
    'wait':  (1, 15, 0.5),    # minutos de espera en caja
}
POR_DEFECTO = {
    'umbrales': {'wait': 4},
    'sucursal': {'nombre': 'Strumia — Mendoza', 'direccion': 'Av. San Martín 1234', 'horario': '06:00 – 22:00'},
    'push': True,
}
_LARGO_MAX_TEXTO = 120

_CREAR_TABLA = """
    CREATE TABLE IF NOT EXISTS configuracion (
        id              SMALLINT   PRIMARY KEY DEFAULT 1,
        datos           JSONB      NOT NULL,
        actualizado_en  TIMESTAMP  NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_configuracion_singleton CHECK (id = 1)
    )"""


def _umbral_valido(clave, v):
    lo, hi, paso = LIMITES_UMBRALES[clave]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
        return False
    pasos = (v - lo) / paso
    return abs(pasos - round(pasos)) < 1e-9


def _combinar(guardado):
    """Valores guardados sobre los por defecto (una clave nueva o faltante toma su valor por defecto)."""
    guardado = guardado or {}
    return {
        # solo los umbrales vigentes: uno que se dejo de usar (p. ej. la cola maxima) se descarta
        'umbrales': {k: (guardado.get('umbrales') or {}).get(k, v) for k, v in POR_DEFECTO['umbrales'].items()},
        'sucursal': {**POR_DEFECTO['sucursal'], **(guardado.get('sucursal') or {})},
        'push': guardado.get('push', POR_DEFECTO['push']),
    }


def leer_configuracion(cur=None):
    """Configuracion vigente. Con 'cur' usa esa conexion (alertas.py); sin ella abre una propia. Nunca falla: si
    la tabla no existe o la base no responde devuelve los valores por defecto."""
    conn = None
    try:
        if cur is None:
            conn = _get_conn()
            if conn is None:
                return _combinar(None)
            cur = conn.cursor()
        cur.execute("SELECT datos FROM configuracion WHERE id = 1")
        fila = cur.fetchone()
        datos = (fila['datos'] if isinstance(fila, dict) else fila[0]) if fila else None
        return _combinar(datos)
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return _combinar(None)
    finally:
        if conn is not None:
            conn.close()


def validar(d):
    """body del PUT -> (configuracion completa, None) o (None, mensaje de error)."""
    if not isinstance(d, dict):
        return None, 'cuerpo invalido'
    actual = _combinar(d)
    for clave in LIMITES_UMBRALES:
        if not _umbral_valido(clave, actual['umbrales'].get(clave)):
            lo, hi, _ = LIMITES_UMBRALES[clave]
            return None, f'umbral {clave} fuera de rango ({lo} a {hi})'
    sucursal = {}
    for k in POR_DEFECTO['sucursal']:
        v = actual['sucursal'].get(k)
        if not isinstance(v, str) or not v.strip():
            return None, f'el campo {k} de la sucursal no puede quedar vacio'
        sucursal[k] = v.strip()[:_LARGO_MAX_TEXTO]
    actual['sucursal'] = sucursal
    if not isinstance(actual['push'], bool):
        return None, 'push debe ser true o false'
    return actual, None


@api_bp.route('/configuracion')
def obtener_configuracion():
    return jsonify(leer_configuracion())


@api_bp.route('/configuracion', methods=['PUT'])
def guardar_configuracion():
    datos, error = validar(request.get_json(silent=True))
    if error:
        return jsonify({'error': error}), 400
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'error': 'sin conexion a la base de datos'}), 503
        cur = conn.cursor()
        cur.execute(_CREAR_TABLA)
        cur.execute("""
            INSERT INTO configuracion (id, datos, actualizado_en) VALUES (1, %s::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE SET datos = EXCLUDED.datos, actualizado_en = NOW()""",
                    (json.dumps(datos, ensure_ascii=False),))
        conn.commit()
        cur.close(); conn.close()
        return jsonify(datos)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

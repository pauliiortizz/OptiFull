"""Reportes 2.0: opciones del formulario y exportacion configurable.

  GET  /reportes/opciones   -> catalogo de metricas, camaras, rango de fechas con datos y formatos
  POST /reportes/exportar   -> genera y devuelve el archivo (PDF / XLSX / CSV / PNG, o ZIP si son varios)

Body de /reportes/exportar:
  {"metricas": ["personas_flujo", ...], "formato": "pdf|xlsx|csv|png",
   "desde": "YYYY-MM-DD" | null, "hasta": "YYYY-MM-DD" | null, "camaras": [1, 2] | []}
"""
from datetime import date, datetime

from flask import Response, jsonify, request

from .blueprint import api_bp
from .db import _get_conn
from .reportes_datos import METRICAS, Filtros, catalogo, recolectar
from .reportes_formatos import GENERADORES

FORMATOS = [
    {'id': 'pdf',  'titulo': 'PDF',           'descripcion': 'Resumen ejecutivo con estadísticas y gráficos.'},
    {'id': 'xlsx', 'titulo': 'Excel (.xlsx)', 'descripcion': 'Una hoja por tabla, listo para analizar.'},
    {'id': 'csv',  'titulo': 'CSV',           'descripcion': 'Datos tabulares crudos (ZIP si hay varias tablas).'},
    {'id': 'png',  'titulo': 'Imágenes',      'descripcion': 'PNG de los gráficos estadísticos (ZIP si hay varios).'},
]


def _error(msg, status=400):
    return jsonify({'error': msg}), status


def _fecha(valor, campo):
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ValueError(f"'{campo}' debe tener formato YYYY-MM-DD")


@api_bp.route('/reportes/opciones')
def reportes_opciones():
    conn = _get_conn()
    if conn is None:
        return _error('sin conexión a la base de datos', 503)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM camaras ORDER BY id")
        camaras = [{'id': r[0], 'nombre': r[1]} for r in cur.fetchall()]
        cur.execute("SELECT MIN(inicio)::date, MAX(inicio)::date FROM sesiones_video")
        fmin, fmax = cur.fetchone()
        cur.close()
        return jsonify({
            'metricas': catalogo(), 'formatos': FORMATOS, 'camaras': camaras,
            'fecha_min': fmin.isoformat() if fmin else None,
            'fecha_max': fmax.isoformat() if fmax else None,
        })
    except Exception as e:
        return _error(str(e), 500)
    finally:
        conn.close()


@api_bp.route('/reportes/exportar', methods=['POST'])
def reportes_exportar():
    body = request.get_json(silent=True) or {}

    ids = body.get('metricas')
    if not isinstance(ids, list) or not ids:
        return _error('Elegí al menos una métrica para el reporte.')
    desconocidas = [i for i in ids if i not in METRICAS]
    if desconocidas:
        return _error(f"Métricas desconocidas: {', '.join(map(str, desconocidas))}")

    formato = body.get('formato')
    if formato not in GENERADORES:
        return _error(f"Formato inválido. Usá: {', '.join(GENERADORES)}")

    try:
        desde, hasta = _fecha(body.get('desde'), 'desde'), _fecha(body.get('hasta'), 'hasta')
    except ValueError as e:
        return _error(str(e))
    try:
        camaras = [int(c) for c in body.get('camaras') or []]
    except (ValueError, TypeError):
        return _error("'camaras' debe ser una lista de ids numéricos.")
    if desde and hasta and desde > hasta:
        return _error("'desde' no puede ser posterior a 'hasta'.")

    filtros = Filtros(desde=desde, hasta=hasta, camaras=camaras)

    conn = _get_conn()
    if conn is None:
        return _error('sin conexión a la base de datos', 503)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM camaras ORDER BY id")
        nombres = {r[0]: r[1] for r in cur.fetchall()}
        cur.close()
        camaras_txt = ', '.join(nombres.get(c, f'Cámara {c}') for c in camaras) if camaras else 'Todas'

        metricas = recolectar(conn, set(ids), filtros)
    except Exception as e:
        return _error(f'No se pudieron consultar los datos: {e}', 500)
    finally:
        conn.close()

    try:
        resultado = GENERADORES[formato](metricas, filtros, camaras_txt)
    except Exception as e:
        return _error(f'No se pudo generar el archivo {formato.upper()}: {e}', 500)
    if resultado is None:
        if formato == 'csv':
            return _error('Las métricas elegidas no tienen tablas de datos para el CSV (p. ej. "Picos de congestión" '
                          'se exporta como gráfico). Sumá otra métrica, ampliá el período o elegí PDF/Imágenes.', 422)
        return _error('No hay gráficos para exportar con los filtros elegidos. Probá ampliar el período o las cámaras.', 422)

    contenido, mimetype, ext = resultado
    nombre = f'optifull_reporte_{datetime.now():%Y%m%d_%H%M}.{ext}'
    return Response(contenido, mimetype=mimetype, headers={
        'Content-Disposition': f'attachment; filename="{nombre}"',
        'Cache-Control': 'no-store',
    })

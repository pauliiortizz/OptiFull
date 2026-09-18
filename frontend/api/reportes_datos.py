"""Recoleccion de datos de Reportes 2.0.

Cada metrica seleccionable en el front tiene un recolector que consulta SOLO lo
que hace falta, filtrado por rango de fechas y camaras, y devuelve un dict:

    {'id', 'titulo', 'categoria',
     'resumen':  [(etiqueta, valor), ...]      # KPIs para el resumen ejecutivo
     'tablas':   [{'nombre', 'columnas', 'filas'}]   # datos tabulares crudos
     'graficos': [spec]                        # ver reportes_graficos.grafico_png
     'imagenes': [{'nombre', 'png'}]           # heatmaps / trayectorias
     'notas':    [str]}

Los formatos (PDF/XLSX/CSV/PNG) se generan a partir de ese dict en
reportes_formatos.py, asi todos muestran exactamente los mismos numeros.

Criterios de exclusion identicos a /reportes/* (reportes.py): empleados afuera
y, en las metricas que CUENTAN personas, CAMARAS_EXCLUIDAS_DE_CONTEO.
"""
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import numpy as np
import psycopg2.extras

from .db import CAMARAS_EXCLUIDAS_DE_CONTEO
from .reportes import detectar_picos
from .reportes_graficos import heatmap_png, trayectorias_png

DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
INTERVALO_SEG = 10.0     # debe coincidir con TRAYECTORIA_INTERVALO_SEG en deteccion/config.py
UMBRAL_STOCK_BAJO = 5    # unidades: por debajo de esto un producto se informa como "stock bajo"
TOP_N = 10               # productos en los graficos de ranking
MAX_PUNTOS_TRAYECTORIA = 200_000


@dataclass
class Filtros:
    desde: date | None = None
    hasta: date | None = None
    camaras: list = field(default_factory=list)   # vacia = todas

    def params(self):
        return {
            'desde': self.desde, 'hasta': self.hasta,
            'cams': list(self.camaras),
            'cams_conteo': [c for c in self.camaras if c not in CAMARAS_EXCLUIDAS_DE_CONTEO],
            'excl': list(CAMARAS_EXCLUIDAS_DE_CONTEO),
        }

    def texto_periodo(self):
        if self.desde and self.hasta:
            return f'{self.desde:%d/%m/%Y} al {self.hasta:%d/%m/%Y}'
        if self.desde:
            return f'desde el {self.desde:%d/%m/%Y}'
        if self.hasta:
            return f'hasta el {self.hasta:%d/%m/%Y}'
        return 'todo el período con datos'


# ── Fragmentos SQL ─────────────────────────────────────────────────────────

def _cam(col, conteo):
    """Filtro de camara. Sin seleccion (cams vacia) -> todas las camaras (menos
    las excluidas del conteo si 'conteo'); con seleccion -> solo esas (y, si
    'conteo', sin las excluidas del conteo)."""
    if conteo:
        return (f'((cardinality(%(cams)s::int[]) = 0 AND {col} <> ALL(%(excl)s::int[])) '
                f'OR {col} = ANY(%(cams_conteo)s::int[]))')
    return f'(cardinality(%(cams)s::int[]) = 0 OR {col} = ANY(%(cams)s::int[]))'


def _fecha(col):
    return (f"({col})::date BETWEEN COALESCE(%(desde)s::date, DATE '0001-01-01') "
            f"AND COALESCE(%(hasta)s::date, DATE '9999-12-31')")


def _fetch(cur, sql, params):
    cur.execute(sql, params)
    filas = cur.fetchall()
    for fila in filas:
        for k, v in fila.items():
            if isinstance(v, Decimal):
                fila[k] = float(v)
    return filas


def _iso(d):
    return d.isoformat() if hasattr(d, 'isoformat') else d


def _r(v, n=1):
    return None if v is None else round(float(v), n)


def _base(id_, titulo, categoria):
    return {'id': id_, 'titulo': titulo, 'categoria': categoria,
            'resumen': [], 'tablas': [], 'graficos': [], 'imagenes': [], 'notas': []}


def _tabla(nombre, columnas, filas):
    return {'nombre': nombre, 'columnas': columnas, 'filas': filas}


# ── Personas: conteo y flujo ───────────────────────────────────────────────

_PERSONAS_VALIDAS = """
    FROM sesiones_video s
    JOIN personas p    ON p.sesion_id = s.id
    JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
    JOIN camaras c     ON c.id = s.camara_id
    WHERE raiz.es_empleado = FALSE AND {cam} AND {fecha}
"""


def _flujo(cur, f):
    p = f.params()
    donde = _PERSONAS_VALIDAS.format(cam=_cam('s.camara_id', True), fecha=_fecha('s.inicio'))

    por_dia = _fetch(cur, f"""
        SELECT s.inicio::date AS fecha, COUNT(DISTINCT COALESCE(p.cliente_id, p.id)) AS personas
        {donde} GROUP BY s.inicio::date ORDER BY fecha""", p)
    total = _fetch(cur, f"SELECT COUNT(DISTINCT COALESCE(p.cliente_id, p.id)) AS n {donde}", p)[0]['n']
    por_camara = _fetch(cur, f"""
        SELECT c.nombre AS camara, COUNT(DISTINCT COALESCE(p.cliente_id, p.id)) AS personas
        {donde} GROUP BY c.id, c.nombre ORDER BY c.id""", p)

    m = _base('personas_flujo', 'Conteo y flujo de personas', 'Personas / Afluencia')
    if not por_dia:
        m['notas'].append('Sin personas detectadas en el período y las cámaras seleccionadas.')
        return m

    por_dow = {}
    for r in por_dia:
        por_dow.setdefault(r['fecha'].weekday(), []).append(r['personas'])
    dow_rows = [[DIAS[i], round(sum(v) / len(v)), len(v)] for i, v in sorted(por_dow.items())]
    pico = max(por_dia, key=lambda r: r['personas'])

    m['resumen'] = [
        ('Personas únicas (período)', total),
        ('Promedio diario', round(sum(r['personas'] for r in por_dia) / len(por_dia))),
        ('Día de mayor afluencia', f"{pico['fecha']:%d/%m/%Y} ({pico['personas']})"),
        ('Días con datos', len(por_dia)),
    ]
    m['tablas'] = [
        _tabla('Flujo diario', ['Fecha', 'Día', 'Personas únicas'],
               [[_iso(r['fecha']), DIAS[r['fecha'].weekday()], r['personas']] for r in por_dia]),
        _tabla('Flujo por día de semana', ['Día', 'Promedio de personas', 'Días con datos'], dow_rows),
        _tabla('Flujo por cámara', ['Cámara', 'Personas únicas'], [[r['camara'], r['personas']] for r in por_camara]),
    ]
    if len(por_dia) > 1:
        m['graficos'].append({
            'id': 'flujo_diario', 'tipo': 'line', 'titulo': 'Personas únicas por día',
            'labels': [f"{r['fecha']:%d/%m}" for r in por_dia], 'valores': [r['personas'] for r in por_dia],
            'ylabel': 'personas'})
    m['graficos'].append({
        'id': 'flujo_semana', 'tipo': 'bar', 'titulo': 'Promedio de personas por día de semana',
        'labels': [r[0] for r in dow_rows], 'valores': [r[1] for r in dow_rows], 'ylabel': 'personas'})
    if not f.camaras and CAMARAS_EXCLUIDAS_DE_CONTEO:
        m['notas'].append('Sin cámaras seleccionadas se omiten las que miran el mismo lugar que otra ya contada '
                          f'(cámaras {", ".join(map(str, CAMARAS_EXCLUIDAS_DE_CONTEO))}) para no duplicar personas.')
    return m


# ── Personas: permanencia ──────────────────────────────────────────────────

def _permanencia(cur, f):
    p = f.params()
    por_dia = _fetch(cur, f"""
        WITH pc AS (
            SELECT v.entrada::date AS fecha, COALESCE(p.cliente_id, p.id) AS cid, SUM(v.duracion_seg) AS seg
            FROM visitas v
            JOIN personas p        ON p.id = v.persona_id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            JOIN personas raiz     ON raiz.id = COALESCE(p.cliente_id, p.id)
            WHERE raiz.es_empleado = FALSE AND {_cam('sv.camara_id', True)} AND {_fecha('v.entrada')}
            GROUP BY v.entrada::date, COALESCE(p.cliente_id, p.id)
        )
        SELECT fecha, AVG(seg) / 60.0 AS prom_min, MAX(seg) / 60.0 AS max_min,
               COUNT(*) AS clientes, SUM(seg) / 60.0 AS total_min
        FROM pc GROUP BY fecha ORDER BY fecha""", p)
    por_zona = _fetch(cur, f"""
        SELECT z.tipo, COALESCE(p.cliente_id, p.id) AS cid, COUNT(*) AS puntos
        FROM trayectorias t
        JOIN zonas z       ON z.id = t.zona_id
        JOIN personas p    ON p.id = t.persona_id
        JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
        WHERE raiz.es_empleado = FALSE AND {_cam('z.camara_id', False)} AND {_fecha('t.timestamp')}
        GROUP BY z.tipo, COALESCE(p.cliente_id, p.id)""", p)

    m = _base('personas_permanencia', 'Tiempos de permanencia promedio', 'Personas / Afluencia')
    if not por_dia and not por_zona:
        m['notas'].append('Sin visitas registradas en el período y las cámaras seleccionadas.')
        return m

    if por_dia:
        clientes = sum(r['clientes'] for r in por_dia)
        prom = sum(r['total_min'] for r in por_dia) / clientes
        m['resumen'] = [
            ('Permanencia promedio (min)', round(prom, 1)),
            ('Permanencia máxima (min)', round(max(r['max_min'] for r in por_dia), 1)),
            ('Visitas cliente-día analizadas', clientes),
        ]
        m['tablas'].append(_tabla(
            'Permanencia por día', ['Fecha', 'Día', 'Promedio (min)', 'Máximo (min)', 'Clientes'],
            [[_iso(r['fecha']), DIAS[r['fecha'].weekday()], _r(r['prom_min']), _r(r['max_min']), r['clientes']]
             for r in por_dia]))
        if len(por_dia) > 1:
            m['graficos'].append({
                'id': 'permanencia_diaria', 'tipo': 'line', 'titulo': 'Permanencia promedio por día',
                'labels': [f"{r['fecha']:%d/%m}" for r in por_dia],
                'valores': [_r(r['prom_min']) for r in por_dia], 'ylabel': 'minutos'})

    if por_zona:
        nombres = {'caja': 'Caja', 'gondola': 'Góndolas', 'otro': 'Salón'}
        acum = {}
        for r in por_zona:
            acum.setdefault(r['tipo'], []).append(r['puntos'] * INTERVALO_SEG / 60)
        total_min = sum(sum(v) for v in acum.values()) or 1
        filas = sorted(([nombres.get(t, t), len(v), _r(sum(v) / len(v)), _r(max(v)), _r(sum(v)),
                         round(sum(v) / total_min * 100)] for t, v in acum.items()), key=lambda x: -x[2])
        m['tablas'].append(_tabla(
            'Permanencia por zona',
            ['Zona', 'Visitantes', 'Promedio (min)', 'Máximo (min)', 'Tiempo total (min)', '% del tiempo'], filas))
        m['graficos'].append({
            'id': 'permanencia_zona', 'tipo': 'bar', 'titulo': 'Permanencia promedio por zona',
            'labels': [r[0] for r in filas], 'valores': [r[2] for r in filas], 'ylabel': 'minutos por visitante'})
    return m


# ── Personas: congestion ───────────────────────────────────────────────────

def _congestion(cur, f):
    p = f.params()
    rows = _fetch(cur, f"""
        WITH ocupacion AS (
            SELECT gs AS hora_ts, COALESCE(p.cliente_id, p.id) AS cid
            FROM visitas v
            JOIN personas p        ON p.id = v.persona_id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            JOIN personas raiz     ON raiz.id = COALESCE(p.cliente_id, p.id)
            CROSS JOIN LATERAL generate_series(date_trunc('hour', v.entrada), date_trunc('hour', v.salida),
                                               interval '1 hour') AS gs
            WHERE raiz.es_empleado = FALSE AND {_cam('sv.camara_id', True)} AND {_fecha('v.entrada')}
        ),
        por_dia_hora AS (
            SELECT hora_ts::date AS fecha, EXTRACT(HOUR FROM hora_ts)::int AS hora,
                   COUNT(DISTINCT cid) AS cantidad
            FROM ocupacion GROUP BY hora_ts::date, EXTRACT(HOUR FROM hora_ts)
        )
        SELECT EXTRACT(DOW FROM fecha)::int AS dow, hora, ROUND(AVG(cantidad))::int AS promedio,
               COUNT(*) AS dias_con_datos
        FROM por_dia_hora GROUP BY dow, hora ORDER BY dow, hora""", p)

    m = _base('personas_congestion', 'Picos de congestión y franjas críticas', 'Personas / Afluencia')
    if not rows:
        m['notas'].append('Sin datos de ocupación horaria en el período y las cámaras seleccionadas.')
        return m

    matriz = [[0] * 24 for _ in DIAS]
    con_datos = [[0] * 24 for _ in DIAS]
    for r in rows:
        i = (r['dow'] + 6) % 7   # Postgres: 0=domingo -> reindexar a Lun(0)..Dom(6)
        matriz[i][r['hora']] = r['promedio']
        con_datos[i][r['hora']] = r['dias_con_datos']
    picos = detectar_picos(matriz, con_datos, DIAS)

    def franja(pk):
        return f"{pk['hora_inicio']:02d}-{(pk['hora_fin'] + 1) % 24:02d}hs"

    if picos:
        m['resumen'].append(('Pico más alto', f"{picos[0]['dia']} {franja(picos[0])} · {picos[0]['promedio']} personas"))
    m['resumen'].append(('Franjas críticas detectadas', len(picos)))
    m['tablas'] = [
        _tabla('Franjas críticas', ['Día', 'Franja', 'Personas (promedio)'],
               [[pk['dia'], franja(pk), pk['promedio']] for pk in picos]),
        _tabla('Congestión día-hora', ['Día', 'Hora', 'Personas (promedio)', 'Días con datos'],
               [[DIAS[i], h, matriz[i][h], con_datos[i][h]]
                for i in range(7) for h in range(24) if con_datos[i][h] > 0]),
    ]
    m['graficos'].append({
        'id': 'congestion_matriz', 'tipo': 'heat', 'titulo': 'Congestión por día y hora (promedio de personas)',
        'filas': DIAS, 'matriz': matriz, 'con_datos': [[c > 0 for c in fila] for fila in con_datos],
        'picos': [(DIAS.index(pk['dia']), pk['hora_inicio'], pk['hora_fin']) for pk in picos]})
    m['notas'].append('Los recuadros oscuros del gráfico marcan las franjas críticas '
                      '(máximos locales de al menos 60% del pico de ese día).')
    return m


# ── Personas: mapas de calor y trayectorias ────────────────────────────────

def _camaras_con_mapas(cur, f):
    p = f.params()
    return _fetch(cur, f"""
        SELECT c.id, c.nombre FROM camaras c
        WHERE {_cam('c.id', False)} AND EXISTS (SELECT 1 FROM mapas_calor mc WHERE mc.camara_id = c.id)
        ORDER BY c.id""", p)


def _heatmaps(cur, f):
    m = _base('personas_heatmaps', 'Trayectorias y mapas de calor', 'Personas / Afluencia')
    p = f.params()
    camaras = _camaras_con_mapas(cur, f)
    if not camaras:
        m['notas'].append('No hay mapas de calor guardados para las cámaras seleccionadas.')
        return m

    filas_mapa, filas_tray = [], []
    for cam in camaras:
        sesiones = _fetch(cur, f"""
            SELECT matriz, valor_maximo, total_detecciones, frames_procesados
            FROM mapas_calor mc
            WHERE mc.camara_id = %(cam)s AND {_fecha('mc.periodo_inicio')}""", {**p, 'cam': cam['id']})
        dims = _fetch(cur, """
            SELECT frame_w, frame_h FROM sesiones_video
            WHERE camara_id = %s AND frame_w IS NOT NULL ORDER BY inicio DESC LIMIT 1""", (cam['id'],))
        frame_wh = (dims[0]['frame_w'], dims[0]['frame_h']) if dims else None

        if sesiones:
            # Cada grilla esta normalizada 0-1 por su propio maximo; se multiplica
            # por 'valor_maximo' para recuperar la escala original antes de
            # sumar (igual que combinar_grids en deteccion/pipeline/heatmap.py).
            grid = None
            for s in sesiones:
                mat = s['matriz'] if not isinstance(s['matriz'], str) else json.loads(s['matriz'])
                g = np.array(mat, dtype=np.float64) * float(s['valor_maximo'] or 0)
                grid = g if grid is None else grid + g
            activa = float((grid > grid.max() * 0.1).mean() * 100) if grid.max() > 0 else 0.0
            filas_mapa.append([cam['nombre'], len(sesiones), sum(s['total_detecciones'] for s in sesiones),
                               sum(s['frames_procesados'] for s in sesiones), round(activa, 1)])
            m['imagenes'].append({
                'nombre': f"heatmap_camara_{cam['id']}",
                'png': heatmap_png(grid, cam['id'], f"Mapa de calor · {cam['nombre']} · {f.texto_periodo()}", frame_wh)})

        puntos = _fetch(cur, f"""
            SELECT t.persona_id, t.centroide_x AS x, t.centroide_y AS y
            FROM trayectorias t
            JOIN personas p        ON p.id = t.persona_id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            JOIN personas raiz     ON raiz.id = COALESCE(p.cliente_id, p.id)
            WHERE sv.camara_id = %(cam)s AND raiz.es_empleado = FALSE AND t.es_empleado = FALSE
              AND {_fecha('t.timestamp')}
            ORDER BY t.persona_id, t.timestamp LIMIT {MAX_PUNTOS_TRAYECTORIA}""", {**p, 'cam': cam['id']})
        if puntos:
            trazas, actual, xs, ys = [], None, [], []
            for r in puntos:
                if r['persona_id'] != actual:
                    if len(xs) > 1:
                        trazas.append((xs, ys))
                    actual, xs, ys = r['persona_id'], [], []
                xs.append(r['x'])
                ys.append(r['y'])
            if len(xs) > 1:
                trazas.append((xs, ys))
            filas_tray.append([cam['nombre'], len({r['persona_id'] for r in puntos}), len(puntos)])
            if trazas:
                m['imagenes'].append({
                    'nombre': f"trayectorias_camara_{cam['id']}",
                    'png': trayectorias_png(trazas, cam['id'],
                                            f"Trayectorias · {cam['nombre']} · {f.texto_periodo()}", frame_wh)})

    if not m['imagenes']:
        m['notas'].append('No hay mapas de calor ni trayectorias en el período seleccionado.')
        return m
    m['resumen'] = [('Cámaras con mapa de calor', len(filas_mapa)),
                    ('Recorridos registrados', sum(r[1] for r in filas_tray))]
    if filas_mapa:
        m['tablas'].append(_tabla('Mapas de calor por cámara',
                                  ['Cámara', 'Sesiones combinadas', 'Detecciones', 'Frames procesados',
                                   'Área activa (% >10% del pico)'], filas_mapa))
    if filas_tray:
        m['tablas'].append(_tabla('Trayectorias por cámara', ['Cámara', 'Personas', 'Puntos de trayectoria'], filas_tray))
    m['notas'].append(f'Las trayectorias dibujan como máximo {300} recorridos por cámara para mantener la legibilidad; '
                      'las tablas cuentan todos.')
    return m


# ── Stock: deteccion y ocupacion de gondolas ───────────────────────────────

def _stock_deteccion(cur, f):
    p = f.params()
    m = _base('stock_deteccion', 'Detección y ocupación de góndolas', 'Stock y Productos')

    por_estado = _fetch(cur, f"""
        SELECT COALESCE(estado_matching, 'sin estado') AS estado, COUNT(*) AS n,
               COALESCE(AVG(confianza_llm), 0) AS confianza
        FROM transacciones WHERE {_fecha('timestamp')} GROUP BY 1 ORDER BY n DESC""", p)
    por_producto = _fetch(cur, f"""
        SELECT pr.sku, pr.nombre, COALESCE(pr.categoria, '-') AS categoria, COUNT(*) AS detecciones,
               SUM(t.cantidad) AS unidades, COALESCE(AVG(t.confianza_llm), 0) AS confianza
        FROM transacciones t JOIN productos pr ON pr.sku = t.sku
        WHERE {_fecha('t.timestamp')} GROUP BY pr.sku, pr.nombre, pr.categoria ORDER BY detecciones DESC""", p)
    gondolas = _fetch(cur, f"""
        SELECT c.nombre AS camara, z.nombre AS zona, COUNT(DISTINCT COALESCE(p.cliente_id, p.id)) AS personas,
               COUNT(*) AS puntos
        FROM trayectorias t
        JOIN zonas z       ON z.id = t.zona_id AND z.tipo = 'gondola'
        JOIN camaras c     ON c.id = z.camara_id
        JOIN personas p    ON p.id = t.persona_id
        JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
        WHERE raiz.es_empleado = FALSE AND {_cam('z.camara_id', False)} AND {_fecha('t.timestamp')}
        GROUP BY c.id, c.nombre, z.id, z.nombre ORDER BY puntos DESC""", p)

    if not por_estado and not gondolas:
        m['notas'].append('Sin detecciones de productos ni actividad en góndolas en el período seleccionado.')
        return m

    if por_estado:
        total = sum(r['n'] for r in por_estado)
        reconocidas = sum(r['n'] for r in por_estado if r['estado'] == 'reconocido')
        conf = sum(r['confianza'] * r['n'] for r in por_estado) / total
        m['resumen'] += [('Productos detectados (transacciones)', total),
                         ('Unidades detectadas', sum(int(r['unidades']) for r in por_producto)),
                         ('Reconocidos sin ambigüedad', f'{round(reconocidas / total * 100)}%'),
                         ('Confianza promedio del modelo', round(conf, 2))]
        m['tablas'] += [
            _tabla('Detección por estado', ['Estado de matching', 'Cantidad', 'Confianza promedio'],
                   [[r['estado'], r['n'], round(r['confianza'], 2)] for r in por_estado]),
            _tabla('Detección por producto', ['SKU', 'Producto', 'Categoría', 'Detecciones', 'Unidades', 'Confianza promedio'],
                   [[r['sku'], r['nombre'], r['categoria'], r['detecciones'], int(r['unidades']), round(r['confianza'], 2)]
                    for r in por_producto]),
        ]
        top = por_producto[:TOP_N]
        m['graficos'].append({
            'id': 'stock_detecciones', 'tipo': 'bar', 'horizontal': True, 'titulo': f'Productos más detectados (top {len(top)})',
            'labels': [r['nombre'] for r in top], 'valores': [r['detecciones'] for r in top], 'ylabel': 'detecciones'})

    if gondolas:
        total_pts = sum(r['puntos'] for r in gondolas) or 1
        filas = [[r['camara'], r['zona'], r['personas'], _r(r['puntos'] * INTERVALO_SEG / 60),
                  round(r['puntos'] / total_pts * 100)] for r in gondolas]
        m['tablas'].append(_tabla('Ocupación de góndolas',
                                  ['Cámara', 'Zona', 'Personas', 'Tiempo de presencia (min)', '% del total'], filas))
        m['graficos'].append({
            'id': 'stock_ocupacion', 'tipo': 'bar', 'horizontal': True, 'titulo': 'Ocupación de góndolas (minutos de presencia)',
            'labels': [f'{r[0]} · {r[1]}' for r in filas], 'valores': [r[3] for r in filas], 'ylabel': 'minutos'})
        m['resumen'].append(('Góndola más concurrida', f'{filas[0][1]} ({filas[0][0]})'))
    m['notas'].append('La ocupación de góndolas mide la presencia de clientes frente a cada góndola (zonas tipo '
                      '"góndola"); el sistema no registra el nivel de llenado físico de las estanterías. '
                      'Las detecciones de productos provienen de la cámara de caja y no dependen del filtro de cámaras.')
    return m


# ── Stock: faltantes y rotacion ────────────────────────────────────────────

def _stock_faltantes(cur, f):
    p = f.params()
    m = _base('stock_faltantes', 'Faltantes y rotación de stock', 'Stock y Productos')
    productos = _fetch(cur, "SELECT sku, nombre, COALESCE(categoria, '-') AS categoria, cantidad FROM productos ORDER BY nombre", {})
    ventas = {r['sku']: r for r in _fetch(cur, f"""
        SELECT sku, SUM(cantidad) AS unidades, MIN(timestamp)::date AS primera, MAX(timestamp)::date AS ultima
        FROM transacciones WHERE {_fecha('timestamp')} GROUP BY sku""", p)}
    if not productos:
        m['notas'].append('No hay productos cargados en el catálogo.')
        return m

    if f.desde and f.hasta:
        dias = (f.hasta - f.desde).days + 1
    elif ventas:
        dias = (max(v['ultima'] for v in ventas.values()) - min(v['primera'] for v in ventas.values())).days + 1
    else:
        dias = 1
    dias = max(dias, 1)

    filas_rot, faltantes = [], []
    for pr in productos:
        vendidas = int(ventas[pr['sku']]['unidades']) if pr['sku'] in ventas else 0
        stock = pr['cantidad']
        rotacion = round(vendidas / (vendidas + stock) * 100, 1) if (vendidas + stock) else 0.0
        cobertura = round(stock / (vendidas / dias), 1) if vendidas else None
        filas_rot.append([pr['sku'], pr['nombre'], pr['categoria'], stock, vendidas, rotacion, cobertura])
        if stock <= UMBRAL_STOCK_BAJO:
            faltantes.append([pr['sku'], pr['nombre'], pr['categoria'], stock,
                              'Agotado' if stock <= 0 else 'Stock bajo', vendidas, cobertura])
    filas_rot.sort(key=lambda r: (-r[5], r[1]))
    faltantes.sort(key=lambda r: (r[3], r[1]))

    agotados = sum(1 for r in faltantes if r[3] <= 0)
    m['resumen'] = [('Productos en catálogo', len(productos)), ('Agotados', agotados),
                    (f'Stock bajo (≤ {UMBRAL_STOCK_BAJO} u.)', len(faltantes) - agotados)]
    if filas_rot and filas_rot[0][5] > 0:
        m['resumen'].append(('Mayor rotación', f'{filas_rot[0][1]} ({filas_rot[0][5]}%)'))
    m['tablas'] = [
        _tabla('Faltantes', ['SKU', 'Producto', 'Categoría', 'Stock actual', 'Estado', 'Vendidas (período)', 'Cobertura (días)'], faltantes),
        _tabla('Rotación de stock', ['SKU', 'Producto', 'Categoría', 'Stock actual', 'Vendidas (período)', 'Rotación (%)', 'Cobertura (días)'], filas_rot),
    ]
    top = [r for r in filas_rot if r[5] > 0][:TOP_N]
    if top:
        m['graficos'].append({
            'id': 'stock_rotacion', 'tipo': 'bar', 'horizontal': True, 'titulo': f'Productos con mayor rotación (top {len(top)})',
            'labels': [r[1] for r in top], 'valores': [r[5] for r in top], 'ylabel': 'rotación (%)'})
    if faltantes:
        crit = faltantes[:TOP_N]
        m['graficos'].append({
            'id': 'stock_faltantes', 'tipo': 'bar', 'horizontal': True, 'titulo': f'Productos con menor stock (top {len(crit)})',
            'labels': [r[1] for r in crit], 'valores': [r[3] for r in crit], 'ylabel': 'unidades en stock'})
    m['notas'] += [
        f'Rotación (%) = unidades vendidas en el período ÷ (vendidas + stock actual). Cobertura (días) = stock actual ÷ '
        f'ventas diarias promedio ({dias} día{"s" if dias != 1 else ""} considerados).',
        'El stock es el actual del catálogo (no se guarda historial diario); las ventas sí respetan el rango de fechas. '
        'Este bloque no depende del filtro de cámaras.',
    ]
    return m


METRICAS = {
    'personas_flujo':       {'categoria': 'personas', 'titulo': 'Conteo y flujo de personas',
                             'descripcion': 'Personas únicas por día, por día de semana y por cámara.', 'fn': _flujo},
    'personas_permanencia': {'categoria': 'personas', 'titulo': 'Tiempos de permanencia promedio',
                             'descripcion': 'Minutos promedio y máximos por día y por zona (caja, góndolas, salón).', 'fn': _permanencia},
    'personas_congestion':  {'categoria': 'personas', 'titulo': 'Picos de congestión y franjas horarias críticas',
                             'descripcion': 'Matriz día × hora y franjas críticas detectadas.', 'fn': _congestion},
    'personas_heatmaps':    {'categoria': 'personas', 'titulo': 'Trayectorias y mapas de calor (heatmaps)',
                             'descripcion': 'Imágenes por cámara sobre la foto del local.', 'fn': _heatmaps},
    'stock_deteccion':      {'categoria': 'stock', 'titulo': 'Detección y ocupación de góndolas/estanterías',
                             'descripcion': 'Productos detectados, confianza del modelo y presencia frente a góndolas.', 'fn': _stock_deteccion},
    'stock_faltantes':      {'categoria': 'stock', 'titulo': 'Faltantes y rotación de stock',
                             'descripcion': 'Productos agotados o con stock bajo, rotación y cobertura.', 'fn': _stock_faltantes},
}


def catalogo():
    return [{'id': k, 'categoria': v['categoria'], 'titulo': v['titulo'], 'descripcion': v['descripcion']}
            for k, v in METRICAS.items()]


def recolectar(conn, ids, filtros):
    """Corre los recolectores de las metricas pedidas (en el orden del
    catalogo). Si uno falla (p. ej. tabla inexistente en esa BD), se rollbackea
    y queda una nota en su seccion sin tumbar el resto del reporte."""
    resultados = []
    for id_, meta in METRICAS.items():
        if id_ not in ids:
            continue
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            resultados.append(meta['fn'](cur, filtros))
        except Exception as e:
            conn.rollback()
            m = _base(id_, meta['titulo'], 'Personas / Afluencia' if meta['categoria'] == 'personas' else 'Stock y Productos')
            m['notas'].append(f'No se pudo obtener esta métrica: {e}')
            resultados.append(m)
        finally:
            cur.close()
    return resultados

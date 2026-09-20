"""Recoleccion de datos de Reportes 2.0.

Cada metrica seleccionable en el front tiene un recolector que consulta SOLO lo
que hace falta, filtrado por rango de fechas y camaras, y devuelve un dict:

    {'id', 'titulo', 'categoria',
     'resumen':  [(etiqueta, valor), ...]      # KPIs para el resumen ejecutivo
     'tablas':   [{'nombre', 'columnas', 'filas'}]   # datos tabulares crudos
     'graficos': [spec]                        # ver reportes_graficos.grafico_png
     'notas':    [str]}

Los formatos (PDF/XLSX/CSV/PNG) se generan a partir de ese dict en
reportes_formatos.py, asi todos muestran exactamente los mismos numeros.

Criterios de exclusion identicos a /reportes/* (reportes.py): empleados afuera
y, en las metricas que CUENTAN personas, CAMARAS_EXCLUIDAS_DE_CONTEO.
"""
import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from itertools import groupby

import psycopg2.extras

from .db import CAMARAS_EXCLUIDAS_DE_CONTEO
from .reportes import detectar_picos

DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
NOMBRES_ZONA = {'caja': 'Caja', 'gondola': 'Góndolas', 'otro': 'Salón',
                'entrada': 'Entrada', 'salida': 'Salida', 'deposito': 'Depósito'}
DIAS_LARGO = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
INTERVALO_SEG = 10.0     # debe coincidir con TRAYECTORIA_INTERVALO_SEG en deteccion/config.py
UMBRAL_STOCK_BAJO = 5    # unidades: por debajo de esto un producto se informa como "stock bajo"
TOP_N = 10               # productos en los graficos de ranking
CAJA_APROXIMACION_RATIO = 0.08   # debe coincidir con deteccion/config.py (cercania a Zona Caja)
MIN_PUNTOS_ESPERA = 2    # muestras de trayectoria seguidas cerca de caja para contar una espera
MIN_MUESTRA_FRANJA = 3   # esperas minimas para mostrar una franja horaria


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


def _r(v, n=1):
    return None if v is None else round(float(v), n)


def _base(id_, titulo, categoria):
    return {'id': id_, 'titulo': titulo, 'categoria': categoria,
            'resumen': [], 'tablas': [], 'graficos': [], 'notas': []}


def _tabla(nombre, columnas, filas, solo_datos=False):
    """solo_datos=True: la tabla es la fuente de un grafico de la misma metrica; va a Excel/CSV
    pero no al PDF, para no mostrar el mismo dato dos veces."""
    return {'nombre': nombre, 'columnas': columnas, 'filas': filas, 'solo_datos': solo_datos}


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

    m = _base('personas_flujo', 'Conteo y flujo de personas', 'Personas / Afluencia')
    if not por_dia:
        m['notas'].append('Sin personas detectadas en el período y las cámaras seleccionadas.')
        return m

    por_dow = {}
    for r in por_dia:
        por_dow.setdefault(r['fecha'].weekday(), []).append(r['personas'])
    dow_rows = [[DIAS_LARGO[i], round(sum(v) / len(v))] for i, v in sorted(por_dow.items())]
    pico = max(por_dia, key=lambda r: r['personas'])

    m['resumen'] = [
        ('Promedio diario', round(sum(r['personas'] for r in por_dia) / len(por_dia))),
        ('Día de mayor afluencia', f"{pico['fecha']:%d/%m/%Y} ({pico['personas']})"),
    ]
    m['tablas'] = [_tabla('Flujo por día de semana', ['Día', 'Promedio de personas'], dow_rows, solo_datos=True)]
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
        ]
        # Por dia de la semana: promedio de los promedios diarios de cada fecha que cayo
        # en ese dia (mismo criterio que /reportes/permanencia-semanal), sin listar fechas.
        por_dow = {}
        for r in por_dia:
            por_dow.setdefault(r['fecha'].weekday(), []).append(r)
        filas_dow = [[DIAS_LARGO[i], _r(sum(x['prom_min'] for x in v) / len(v)), _r(max(x['max_min'] for x in v))]
                     for i, v in sorted(por_dow.items())]
        m['tablas'].append(_tabla('Permanencia por día',
                                  ['Día', 'Promedio (min)', 'Máximo (min)'], filas_dow, solo_datos=True))
        m['graficos'].append({
            'id': 'permanencia_semana', 'tipo': 'bar', 'titulo': 'Permanencia promedio por día de la semana',
            'labels': [r[0] for r in filas_dow], 'valores': [r[1] for r in filas_dow], 'ylabel': 'minutos'})

    if por_zona:
        acum = {}
        for r in por_zona:
            acum.setdefault(r['tipo'], []).append(r['puntos'] * INTERVALO_SEG / 60)
        total_min = sum(sum(v) for v in acum.values()) or 1
        filas = sorted(([NOMBRES_ZONA.get(t, t), _r(sum(v) / len(v)), _r(max(v)), _r(sum(v)),
                         round(sum(v) / total_min * 100)] for t, v in acum.items()), key=lambda x: -x[1])
        m['tablas'].append(_tabla(
            'Permanencia por zona',
            ['Zona', 'Promedio (min)', 'Máximo (min)', 'Tiempo total (min)', '% del tiempo'], filas, solo_datos=True))
        m['graficos'].append({
            'id': 'permanencia_zona', 'tipo': 'bar', 'titulo': 'Permanencia promedio por zona',
            'labels': [r[0] for r in filas], 'valores': [r[1] for r in filas], 'ylabel': 'minutos por visitante'})
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
    m['graficos'].append({
        'id': 'congestion_matriz', 'tipo': 'heat', 'titulo': 'Congestión por día y hora (promedio de personas)',
        'filas': DIAS, 'matriz': matriz, 'con_datos': [[c > 0 for c in fila] for fila in con_datos],
        'picos': [(DIAS.index(pk['dia']), pk['hora_inicio'], pk['hora_fin']) for pk in picos]})
    m['notas'].append('Los recuadros oscuros del gráfico marcan las franjas críticas '
                      '(máximos locales de al menos 60% del pico de ese día).')
    return m


# ── Personas: tiempo de espera en caja ─────────────────────────────────────

def _en_poligono(x, y, poly):
    dentro, j = False, len(poly) - 1
    for i in range(len(poly)):
        (xi, yi), (xj, yj) = poly[i], poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def _dist_a_poligono(x, y, poly):
    """0 si el punto cae dentro; si no, distancia (px) al borde mas cercano."""
    if _en_poligono(x, y, poly):
        return 0.0
    mejor = float('inf')
    for i in range(len(poly)):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = bx - ax, by - ay
        largo = dx * dx + dy * dy
        t = 0 if largo == 0 else max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / largo))
        mejor = min(mejor, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return mejor


def _fmt_seg(seg):
    seg = round(seg)
    return f'{seg} s' if seg < 60 else f'{seg // 60} min {seg % 60:02d} s'


def _espera_caja(cur, f):
    """Tiempo de espera en caja. Zona Caja es el lado del EMPLEADO del
    mostrador: un cliente que paga o espera su pedido se ACERCA pero casi nunca
    pisa el poligono (ver utils.cerca_de_zona_tipo en deteccion/). Por eso una
    "espera" es un tramo de al menos MIN_PUNTOS_ESPERA muestras de trayectoria
    consecutivas de un cliente a menos de CAJA_APROXIMACION_RATIO del ancho del
    frame del borde de una zona de caja -- mismo criterio de cercania que usa el
    pipeline para 'paso_por_caja'. Su duracion es el tiempo entre la primera y
    la ultima muestra del tramo (+ un intervalo de muestreo). No se puede
    separar la fila de la atencion en si: es el tiempo total en la zona de
    aproximacion antes de irse."""
    p = f.params()
    m = _base('personas_espera_caja', 'Tiempo de espera en caja', 'Personas / Afluencia')

    zonas = _fetch(cur, f"""
        SELECT z.camara_id, z.poligono FROM zonas z
        WHERE z.tipo = 'caja' AND {_cam('z.camara_id', False)}""", p)
    poligonos = {}
    for z in zonas:
        poligonos.setdefault(z['camara_id'], []).append(z['poligono'])

    esperas = []   # (hora de inicio, duracion en segundos)
    for cam_id, polis in sorted(poligonos.items()):
        # Ancho de frame mas frecuente de la camara (alguna sesion puede tener otra resolucion)
        fw = _fetch(cur, """SELECT frame_w FROM sesiones_video WHERE camara_id = %(cam)s AND frame_w IS NOT NULL
                            GROUP BY frame_w ORDER BY COUNT(*) DESC LIMIT 1""", {'cam': cam_id})
        margen = CAJA_APROXIMACION_RATIO * (fw[0]['frame_w'] if fw else 1920)
        # Caja delimitadora de cada zona (+ margen): descarta rapido los puntos lejanos
        cajas = [(poli, min(x for x, _ in poli) - margen, max(x for x, _ in poli) + margen,
                  min(y for _, y in poli) - margen, max(y for _, y in poli) + margen) for poli in polis]
        puntos = _fetch(cur, f"""
            SELECT t.persona_id, t.timestamp AS ts, t.centroide_x AS x, t.centroide_y AS y
            FROM trayectorias t
            JOIN personas p        ON p.id = t.persona_id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            JOIN personas raiz     ON raiz.id = COALESCE(p.cliente_id, p.id)
            WHERE sv.camara_id = %(cam)s AND raiz.es_empleado = FALSE AND t.es_empleado = FALSE
              AND {_fecha('t.timestamp')}
            ORDER BY t.persona_id, t.timestamp""", {**p, 'cam': cam_id})
        for _, grupo in groupby(puntos, key=lambda r: r['persona_id']):
            grupo = list(grupo)
            cerca = [any(x0 <= r['x'] <= x1 and y0 <= r['y'] <= y1 and _dist_a_poligono(r['x'], r['y'], poli) <= margen
                         for poli, x0, x1, y0, y1 in cajas) for r in grupo]
            i = 0
            while i < len(grupo):
                if not cerca[i]:
                    i += 1
                    continue
                j = i
                while (j + 1 < len(grupo) and cerca[j + 1]
                       and (grupo[j + 1]['ts'] - grupo[j]['ts']).total_seconds() <= 3 * INTERVALO_SEG):
                    j += 1
                if j - i + 1 >= MIN_PUNTOS_ESPERA:
                    esperas.append((grupo[i]['ts'].hour, (grupo[j]['ts'] - grupo[i]['ts']).total_seconds() + INTERVALO_SEG))
                i = j + 1

    if not esperas:
        m['notas'].append('Sin esperas registradas en la zona de caja en el período y las cámaras seleccionadas.')
        return m

    duraciones = [d for _, d in esperas]
    largas = sum(1 for d in duraciones if d > 60)
    m['resumen'] = [
        ('Espera promedio', _fmt_seg(statistics.mean(duraciones))),
        ('Espera mediana', _fmt_seg(statistics.median(duraciones))),
        ('Espera máxima', _fmt_seg(max(duraciones))),
        ('Esperas de más de 1 minuto', f'{round(largas / len(duraciones) * 100)}%'),
        ('Esperas registradas', len(duraciones)),
    ]

    por_hora = {}
    for h, d in esperas:
        por_hora.setdefault(h, []).append(d)
    filas_hora = [[f'{h:02d}-{(h + 1) % 24:02d}hs', round(statistics.mean(v) / 60, 2), round(max(v) / 60, 2), len(v)]
                  for h, v in sorted(por_hora.items()) if len(v) >= MIN_MUESTRA_FRANJA]
    tramos = [('Menos de 30 s', 0, 30), ('30 s a 1 min', 30, 60), ('1 a 2 min', 60, 120),
              ('2 a 5 min', 120, 300), ('Más de 5 min', 300, float('inf'))]
    filas_dist = [[nombre, sum(1 for d in duraciones if lo <= d < hi), 0] for nombre, lo, hi in tramos]
    for fila in filas_dist:
        fila[2] = round(fila[1] / len(duraciones) * 100, 1)

    m['tablas'] = [
        _tabla('Espera por franja horaria',
               ['Franja horaria', 'Espera promedio (min)', 'Espera máxima (min)', 'Esperas registradas'],
               filas_hora, solo_datos=True),
        _tabla('Distribución de la espera', ['Tiempo de espera', 'Esperas', '% de las esperas'],
               filas_dist, solo_datos=True),
    ]
    if filas_hora:
        m['graficos'].append({
            'id': 'espera_franja', 'tipo': 'bar', 'titulo': 'Tiempo de espera promedio en caja por franja horaria',
            'labels': [r[0] for r in filas_hora], 'valores': [r[1] for r in filas_hora], 'ylabel': 'minutos'})
    m['graficos'].append({
        'id': 'espera_distribucion', 'tipo': 'bar', 'titulo': 'Distribución del tiempo de espera en caja',
        'labels': [r[0] for r in filas_dist], 'valores': [r[2] for r in filas_dist], 'ylabel': '% de las esperas'})
    m['notas'] += [
        'Espera = tiempo que un cliente permanece en la zona de aproximación a la caja (a menos del '
        f'{round(CAJA_APROXIMACION_RATIO * 100)}% del ancho de imagen del borde de la zona de caja), con al menos '
        f'{MIN_PUNTOS_ESPERA} muestras seguidas; quien solo pasa caminando cerca no cuenta. Incluye la atención: no se '
        'puede separar la fila del cobro.',
        f'Las franjas horarias con menos de {MIN_MUESTRA_FRANJA} esperas se omiten por no ser representativas. '
        'Se combinan las cámaras que captan la caja, por lo que una misma espera vista por varias cámaras se cuenta en cada una.',
    ]
    return m


# ── Personas: permanencia por zona (mapa de calor) y trayectorias ──────────

_TRAYECTORIAS_VALIDAS = """
    FROM trayectorias t
    JOIN zonas z       ON z.id = t.zona_id
    JOIN personas p    ON p.id = t.persona_id
    JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
    WHERE raiz.es_empleado = FALSE AND t.es_empleado = FALSE AND {cam} AND {fecha}
"""


def _zonas_y_recorridos(cur, f):
    """Estadisticas por zona en vez de imagenes: el mapa de calor acumula
    detecciones por posicion, asi que su lectura por zona es cuanto tiempo de
    presencia cae en cada una (cada punto de trayectoria ~ INTERVALO_SEG). Se
    cruza con los recorridos: cuantas personas pasan por cada zona, cuanto
    se quedan y en que orden las recorren.

    Las zonas se consolidan por TIPO (Caja / Gondolas / Salon) entre todas las
    camaras que las captan, sin desglose por camara: los promedios son
    ponderados (tiempo total / personas, sumando camaras) y el maximo es el
    mayor entre camaras."""
    p = f.params()
    donde = _TRAYECTORIAS_VALIDAS.format(cam=_cam('z.camara_id', False), fecha=_fecha('t.timestamp'))
    m = _base('personas_heatmaps', 'Trayectorias y mapas de calor', 'Personas / Afluencia')

    filas = _fetch(cur, f"""
        SELECT z.tipo, z.camara_id, COALESCE(p.cliente_id, p.id) AS cid, COUNT(*) AS puntos
        {donde} GROUP BY z.tipo, z.camara_id, COALESCE(p.cliente_id, p.id)""", p)
    if not filas:
        m['notas'].append('Sin trayectorias registradas en el período y las cámaras seleccionadas.')
        return m

    # ── Permanencia por zona: una entrada por (camara, cliente) en cada tipo de zona
    por_tipo, personas_camara = {}, {}
    for r in filas:
        por_tipo.setdefault(r['tipo'], []).append(r['puntos'] * INTERVALO_SEG / 60)
        personas_camara.setdefault(r['camara_id'], set()).add(r['cid'])
    total_min = sum(sum(v) for v in por_tipo.values()) or 1
    total_personas = sum(len(s) for s in personas_camara.values())   # persona-camara: pondera cada camara por su gente

    tabla_zonas = []   # [zona, % permanencia, promedio, maximo, % de personas que pasaron]
    for tipo, mins in sorted(por_tipo.items(), key=lambda kv: -sum(kv[1])):
        tabla_zonas.append([NOMBRES_ZONA.get(tipo, tipo), round(sum(mins) / total_min * 100, 1),
                            _r(sum(mins) / len(mins)), _r(max(mins)), round(len(mins) / total_personas * 100, 1)])

    # ── Recorridos: zonas distintas de cada aparicion, en el orden en que se pisaron
    puntos = _fetch(cur, f"""
        SELECT t.persona_id, z.tipo
        {donde} ORDER BY t.persona_id, t.timestamp""", p)
    rutas, ruta_min = Counter(), Counter()
    for _, grupo in groupby(puntos, key=lambda r: r['persona_id']):
        seq = [NOMBRES_ZONA.get(r['tipo'], r['tipo']) for r in grupo]
        orden = tuple(dict.fromkeys(seq))
        rutas[orden] += 1
        ruta_min[orden] += len(seq) * INTERVALO_SEG / 60
    total_rec = sum(rutas.values())
    tabla_rutas = [[' → '.join(o), n, round(n / total_rec * 100, 1), _r(ruta_min[o] / n)]
                   for o, n in rutas.most_common(10)]

    # ── Resumen ejecutivo
    mas_transitada = max(tabla_zonas, key=lambda r: r[4])
    mas_permanencia = max(tabla_zonas, key=lambda r: r[1])
    mas_demora = max(tabla_zonas, key=lambda r: r[2])
    m['resumen'] = [
        ('Zona más transitada', f'{mas_transitada[0]} · {mas_transitada[4]}% de las personas'),
        ('Mayor % de permanencia', f'{mas_permanencia[0]} · {mas_permanencia[1]}%'),
        ('Donde más se demoran', f'{mas_demora[0]} · {mas_demora[2]} min por persona'),
        ('Recorrido más frecuente', f'{tabla_rutas[0][0]} · {tabla_rutas[0][2]}%'),
    ]
    m['tablas'] = [
        _tabla('Permanencia y tránsito por zona',
               ['Zona', '% de permanencia', 'Permanencia promedio (min)', 'Permanencia máxima (min)',
                '% de las personas que pasaron'], tabla_zonas),
        _tabla('Recorridos más frecuentes',
               ['Zonas recorridas (en orden)', 'Recorridos', '% de los recorridos', 'Tiempo promedio (min)'], tabla_rutas),
    ]
    etiquetas = [r[0] for r in tabla_zonas]
    m['graficos'] = [
        {'id': 'personas_zonas', 'tipo': 'bar', 'titulo': 'Personas que pasaron por cada zona (%)',
         'labels': etiquetas, 'valores': [r[4] for r in tabla_zonas], 'ylabel': '% de las personas'},
    ]
    m['notas'] += [
        'El mapa de calor acumula la presencia por posición; acá se lee por zona: cada punto de trayectoria equivale a '
        f'~{int(INTERVALO_SEG)} s de presencia, y el % de permanencia es la porción del tiempo total detectado que '
        'transcurrió en cada zona.',
        'Las zonas del mismo tipo captadas por varias cámaras se consolidan: los promedios son ponderados por la '
        'cantidad de personas de cada cámara y el máximo es el mayor entre cámaras.',
        'Un recorrido es una aparición de una persona en un video; sus zonas se ordenan según la primera vez que las pisó.',
        'Se excluye al personal del local: las zonas ocupadas solo por empleados (p. ej. la zona de caja) no figuran.',
    ]
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
    'personas_espera_caja': {'categoria': 'personas', 'titulo': 'Tiempo de espera en caja',
                             'descripcion': 'Cuánto esperan los clientes cerca de la caja: promedio por franja horaria y distribución.',
                             'fn': _espera_caja},
    'personas_heatmaps':    {'categoria': 'personas', 'titulo': 'Trayectorias y mapas de calor (heatmaps)',
                             'descripcion': 'Permanencia (%) y personas por zona, recorridos más frecuentes y flujo entre zonas.', 'fn': _zonas_y_recorridos},
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

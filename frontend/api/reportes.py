"""Endpoints de reportes agregados (tendencias, congestion, zonas, etc.)."""
from flask import jsonify

from .blueprint import api_bp
from .db import (_get_conn, CAMARAS_EXCLUIDAS_DE_CONTEO, rango_de_request, sql_rango,
                 sql_tiempo_visto, filtro_conteo, PARAMS_TIEMPO_VISTO)

# Umbral de la heuristica "posible empleado": si un cliente_id suma mas de
# esto de tiempo total detectado en UN mismo dia calendario (entre todas sus
# apariciones/sesiones), se sugiere como candidato -- un visitante normal no
# permanece tantas horas en el local. Es solo una sugerencia: nunca marca
# es_empleado sola, requiere confirmacion manual via /personas/<id>/empleado.
UMBRAL_HORAS_POSIBLE_EMPLEADO = 3


def detectar_picos(matriz, dias_con_datos, dias, umbral_pico=0.6):
    """Picos de congestion por dia (ver reportes_congestion_horaria). Devuelve
    una lista de {'dia','hora_inicio','hora_fin','promedio'} ordenada de mayor
    a menor. Compartida con la exportacion de reportes (reportes_datos.py)."""
    # Un mismo dia puede tener MAS DE UN pico real (ej. una franja a la
    # manana y otra a la tarde/noche, con un valle de por medio) -- un
    # solo maximo global se perdia todos menos el mas alto de toda la
    # semana. Se buscan, POR DIA, las horas que son maximo LOCAL (mayor
    # o igual que ambos vecinos horarios) y ademas "significativas"
    # (llegan al umbral_pico del maximo de ESE dia -- sin esto, cualquier
    # bache chico entre horas bajas se marcaria como "pico"). Horas
    # consecutivas que cumplen se agrupan en un solo rango.
    picos = []
    for i, fila in enumerate(matriz):
        con_datos_fila = dias_con_datos[i]
        valores_con_datos = [fila[h] for h in range(24) if con_datos_fila[h] > 0]
        max_dia = max(valores_con_datos, default=0)
        if max_dia <= 0:
            continue

        es_pico = [False] * 24
        for h in range(24):
            if con_datos_fila[h] == 0 or fila[h] <= 0:
                continue
            prev_val = fila[h - 1] if h > 0 and con_datos_fila[h - 1] > 0 else -1
            next_val = fila[h + 1] if h < 23 and con_datos_fila[h + 1] > 0 else -1
            if fila[h] >= prev_val and fila[h] >= next_val and fila[h] >= max_dia * umbral_pico:
                es_pico[h] = True

        h = 0
        while h < 24:
            if not es_pico[h]:
                h += 1
                continue
            inicio = h
            while h < 24 and es_pico[h]:
                h += 1
            fin = h - 1
            picos.append({
                'dia': dias[i], 'hora_inicio': inicio, 'hora_fin': fin,
                'promedio': max(fila[inicio:fin + 1]),
            })
    picos.sort(key=lambda p: p['promedio'], reverse=True)
    return picos


DIAS_SEMANA = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']


def _semanal(filas, decimales):
    """Respuesta comun de tendencia-semanal y permanencia-semanal a partir de un valor por fecha
    ('filas': {'fecha', 'valor'} ya acotadas al rango pedido). Devuelve la serie dia por dia ('por_fecha',
    la que usa el dashboard con Hoy / 7 dias: una barra por fecha) y el promedio por dia de la semana sobre
    esas mismas fechas ('promedio' / 'dias_con_datos', Lun..Dom: con 30 dias o Personalizado, cada barra es
    el promedio de los lunes, de los martes, etc. del periodo)."""
    acum = [[] for _ in DIAS_SEMANA]
    for r in filas:
        acum[r['fecha'].weekday()].append(float(r['valor']))   # weekday(): 0 = lunes

    def red(v):
        return int(round(v)) if decimales == 0 else round(v, decimales)
    return {
        'labels':         DIAS_SEMANA,
        'promedio':       [red(sum(v) / len(v)) if v else 0 for v in acum],
        'dias_con_datos': [len(v) for v in acum],
        'por_fecha':      [{'fecha': r['fecha'].isoformat(), 'valor': red(float(r['valor']))} for r in filas],
        'fuente':         'db',
    }


def _semanal_vacio(fuente):
    return {'labels': DIAS_SEMANA, 'promedio': [0] * 7, 'dias_con_datos': [0] * 7, 'por_fecha': [], 'fuente': fuente}


@api_bp.route('/reportes/tendencia-semanal')
def reportes_tendencia_semanal():
    """Personas UNICAS reales por fecha calendario (cada cliente_id una sola vez por dia, entre todas las
    sesiones/camaras contadas). El dia es el de cada deteccion (timestamp de su trayectoria), NO el de grabacion
    del video: un analisis que sigue corriendo pasada la medianoche cuenta cada persona en el dia en que se la vio, dentro del rango ?desde=&hasta= del dashboard; ver _semanal para la serie
    diaria y el promedio por dia de la semana. Excluye CAMARAS_EXCLUIDAS_DE_CONTEO (camaras que miran el
    mismo lugar que otra ya contada -- ver comentario junto a la constante). Sin rango: todo el historial."""
    desde, hasta = rango_de_request()
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify(_semanal_vacio('sin_bd'))

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH por_dia AS (
                SELECT ts::date AS fecha, COUNT(DISTINCT cliente_id) AS valor
                FROM """ + sql_tiempo_visto(filtro_conteo()) + """ pv
                GROUP BY ts::date
            )
            SELECT fecha, valor FROM por_dia ORDER BY fecha
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta, **PARAMS_TIEMPO_VISTO})
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify(_semanal(rows, 0))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reportes/permanencia-semanal')
def reportes_permanencia_semanal():
    """Permanencia real promedio (en minutos) por fecha: para cada cliente real (cliente_id) y fecha
    calendario, suma su tiempo VISTO de ese dia (sql_tiempo_visto -- la misma regla que el KPI de
    permanencia y las zonas) y promedia entre los clientes de ese dia. Mismo rango ?desde=&hasta= y misma
    salida que tendencia-semanal (ver _semanal), con minutos en vez de cantidad de personas."""
    desde, hasta = rango_de_request()
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify(_semanal_vacio('sin_bd'))

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH permanencia_por_cliente_dia AS (
                SELECT ts::date AS fecha, cliente_id, SUM(segundos) AS duracion_seg
                FROM """ + sql_tiempo_visto(filtro_conteo()) + """ pv
                GROUP BY ts::date, cliente_id
                HAVING SUM(segundos) > %(minima)s      -- sin ruido, igual que el KPI
            )
            SELECT fecha, AVG(duracion_seg) / 60 AS valor
            FROM permanencia_por_cliente_dia
            GROUP BY fecha
            ORDER BY fecha
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta, **PARAMS_TIEMPO_VISTO})
        rows = cur.fetchall()
        cur.close(); conn.close()
        return jsonify(_semanal(rows, 1))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reportes/congestion-horaria')
def reportes_congestion_horaria():
    """Horarios estimados de congestion: cuanta gente (personas UNICAS reales,
    via cliente_id) hubo presente en camara durante cada franja horaria, en
    cada dia de la semana. Un cliente cuenta como presente en una hora si se
    lo VIO en esa hora (algun punto de sql_tiempo_visto, la misma fuente que
    el KPI de permanencia): alguien visto de 15:40 a 16:20 cuenta tanto en el
    bucket de las 15hs como en el de las 16hs. Antes se expandian las 'visitas'
    de entrada a salida, que seguian abiertas mientras la persona no se veia. Se promedia entre todas
    las fechas calendario que cayeron en cada dia de la semana, asi el
    resultado no depende de cuantos dias de cada tipo se analizaron todavia,
    y permite ver que un viernes al mediodia tiene mas gente que un martes.

    Ademas devuelve la grilla de CADA fecha del rango ('por_fecha': {fecha,
    horas[24]}) y sus picos ('picos_por_fecha', con 'dia' = la fecha ISO): el
    dashboard la usa con Hoy y 7 dias (una fila por fecha) y el promedio por dia
    de la semana con 30 dias o Personalizado."""
    dias  = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    horas = list(range(24))
    desde, hasta = rango_de_request()      # ?desde=&hasta= opcionales (filtros del dashboard)
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({
                'dias': dias, 'horas': horas,
                'matriz': [[0] * 24 for _ in dias],
                'dias_con_datos': [[0] * 24 for _ in dias],
                'por_fecha': [], 'picos_por_fecha': [],
                'fuente': 'sin_bd',
            })

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH ocupacion AS (
                SELECT date_trunc('hour', ts) AS hora_ts, cliente_id
                FROM """ + sql_tiempo_visto(filtro_conteo()) + """ pv
            ),
            por_dia_hora AS (
                SELECT
                    hora_ts::date                   AS fecha,
                    EXTRACT(HOUR FROM hora_ts)::int AS hora,
                    COUNT(DISTINCT cliente_id)      AS cantidad
                FROM ocupacion
                GROUP BY hora_ts::date, EXTRACT(HOUR FROM hora_ts)
            )
            SELECT fecha, hora, cantidad
            FROM por_dia_hora
            ORDER BY fecha, hora
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta, **PARAMS_TIEMPO_VISTO})
        rows = cur.fetchall()
        cur.close(); conn.close()

        # Promedio por dia de la semana (Lun..Dom) de cada hora, entre las fechas que la tienen
        acum = [[[] for _ in horas] for _ in dias]
        por_fecha = {}
        for r in rows:
            acum[r['fecha'].weekday()][r['hora']].append(r['cantidad'])   # weekday(): 0 = lunes
            por_fecha.setdefault(r['fecha'], [0] * 24)[r['hora']] = r['cantidad']
        matriz         = [[int(sum(v) / len(v) + 0.5) if v else 0 for v in fila] for fila in acum]
        dias_con_datos = [[len(v) for v in fila] for fila in acum]

        picos = detectar_picos(matriz, dias_con_datos, dias)
        pico = picos[0] if picos else None

        fechas = sorted(por_fecha)
        picos_por_fecha = detectar_picos([por_fecha[f] for f in fechas],
                                         [[1 if c > 0 else 0 for c in por_fecha[f]] for f in fechas],
                                         [f.isoformat() for f in fechas])

        return jsonify({
            'dias': dias, 'horas': horas,
            'matriz': matriz, 'dias_con_datos': dias_con_datos,
            'pico': pico, 'picos': picos,
            'por_fecha': [{'fecha': f.isoformat(), 'horas': por_fecha[f]} for f in fechas],
            'picos_por_fecha': picos_por_fecha,
            'fuente': 'db',
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reportes/promedio-diario')
def reportes_promedio_diario():
    """Promedio de personas UNICAS detectadas por dia (clientes distintos por
    fecha calendario, promediado entre todos los dias con datos). Combina
    TODOS los grupos fisicos de camaras (ver GRUPOS_CAMARA en
    deteccion/config.py), pero de cada grupo solo cuenta la camara canonica
    (CAMARAS_EXCLUIDAS_DE_CONTEO) -- fusionar el conteo entre camaras que
    miran el mismo lugar via Re-ID por descripcion de texto nunca converge
    del todo, asi que en vez de eso se cuenta esa gente UNA sola vez desde
    una sola camara por grupo. Respeta el rango ?desde=&hasta= del dashboard (por la fecha en que se detecto cada persona)."""
    desde, hasta = rango_de_request()
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'promedio': None, 'dias_con_datos': 0, 'fuente': 'sin_bd'})

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH por_dia AS (
                SELECT ts::date AS fecha, COUNT(DISTINCT cliente_id) AS cantidad
                FROM """ + sql_tiempo_visto(filtro_conteo()) + """ pv
                GROUP BY ts::date
            )
            SELECT ROUND(AVG(cantidad))::int AS promedio, COUNT(*) AS dias_con_datos
            FROM por_dia
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta, **PARAMS_TIEMPO_VISTO})
        row = cur.fetchone()
        cur.close(); conn.close()

        return jsonify({
            'promedio':       row['promedio'] if row and row['dias_con_datos'] > 0 else None,
            'dias_con_datos': row['dias_con_datos'] if row else 0,
            'fuente':         'db',
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reportes/posibles-empleados')
def reportes_posibles_empleados():
    """Candidatos a 'empleado' por heuristica de permanencia total diaria.
    Agrupa por cliente_id real y dia calendario el tiempo VISTO (sql_tiempo_visto,
    la misma regla que el KPI de permanencia); si supera el umbral, se sugiere.
    Antes sumaba 'visitas', que seguian abiertas mientras la persona no se veia
    y sugerian como empleados a clientes que solo se habian visto unos minutos."""
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'candidatos': [], 'umbral_horas': UMBRAL_HORAS_POSIBLE_EMPLEADO, 'fuente': 'sin_bd'})

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                cliente_id,
                ts::date                             AS fecha,
                COUNT(DISTINCT persona_id)           AS apariciones,
                ROUND(SUM(segundos) / 60)::int       AS minutos_totales,
                MIN(ts)                              AS primera_hora,
                MAX(ts)                              AS ultima_hora
            FROM """ + sql_tiempo_visto(filtro_conteo()) + """ pv
            GROUP BY cliente_id, ts::date
            HAVING SUM(segundos) >= %(umbral)s
            ORDER BY minutos_totales DESC
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': None, 'hasta': None,
              'umbral': UMBRAL_HORAS_POSIBLE_EMPLEADO * 3600, **PARAMS_TIEMPO_VISTO})
        rows = cur.fetchall()
        cur.close(); conn.close()

        for r in rows:
            r['fecha']        = r['fecha'].isoformat()
            r['primera_hora'] = r['primera_hora'].strftime('%H:%M:%S')
            r['ultima_hora']  = r['ultima_hora'].strftime('%H:%M:%S')

        return jsonify({'candidatos': rows, 'umbral_horas': UMBRAL_HORAS_POSIBLE_EMPLEADO, 'fuente': 'db'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reportes/conversion-compra')
def reportes_conversion_compra():
    """Promedio diario de clientes reales que COMPRARON vs. que NO compraron
    nada, segun la clasificacion Escenario A/B/C de cada visita (ver
    deteccion/pipeline/eventos.py, tabla 'eventos'). Un cliente_id cuenta como
    "compro" ese dia si CUALQUIERA de sus visitas de ese dia dio
    accion_detectada='COMPRA_NORMAL' (bool_or) -- alguien puede entrar varias
    veces en un dia y basta con que haya comprado en una. Sin evento ese dia
    (ninguna visita con zonas registradas) queda afuera del calculo, ni
    compro ni no compro: no hay evidencia. Mismo criterio de exclusion que el
    resto de /reportes/* (empleados afuera, CAMARAS_EXCLUIDAS_DE_CONTEO para
    no duplicar el mismo mostrador visto por 2 camaras). Respeta el rango
    ?desde=&hasta= del dashboard (con Hoy, el promedio es el del dia de hoy)."""
    desde, hasta = rango_de_request()
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({
                'promedio_compraron': None, 'promedio_no_compraron': None,
                'pct_conversion': None, 'dias_con_datos': 0, 'fuente': 'sin_bd',
            })

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH por_persona_dia AS (
                SELECT
                    p.primera_deteccion::date    AS fecha,
                    COALESCE(p.cliente_id, p.id)  AS cliente_id,
                    bool_or(e.accion_detectada = 'COMPRA_NORMAL') AS compro
                FROM eventos e
                JOIN personas p    ON p.id = e.persona_id
                JOIN sesiones_video sv ON sv.id = p.sesion_id
                JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
                WHERE raiz.es_empleado = FALSE AND sv.camara_id NOT IN %(excl)s
                  AND """ + sql_rango('p.primera_deteccion') + """
                GROUP BY p.primera_deteccion::date, COALESCE(p.cliente_id, p.id)
            ),
            por_dia AS (
                SELECT fecha,
                       COUNT(*) FILTER (WHERE compro)     AS compraron,
                       COUNT(*) FILTER (WHERE NOT compro) AS no_compraron
                FROM por_persona_dia
                GROUP BY fecha
            )
            SELECT ROUND(AVG(compraron))::int    AS promedio_compraron,
                   ROUND(AVG(no_compraron))::int AS promedio_no_compraron,
                   COUNT(*)                      AS dias_con_datos
            FROM por_dia
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta})
        row = cur.fetchone()
        cur.close(); conn.close()

        if not row or not row['dias_con_datos']:
            return jsonify({
                'promedio_compraron': None, 'promedio_no_compraron': None,
                'pct_conversion': None, 'dias_con_datos': 0, 'fuente': 'db',
            })

        compraron    = row['promedio_compraron'] or 0
        no_compraron = row['promedio_no_compraron'] or 0
        total        = compraron + no_compraron
        pct          = round(100.0 * compraron / total, 1) if total else None

        return jsonify({
            'promedio_compraron':    compraron,
            'promedio_no_compraron': no_compraron,
            'pct_conversion':        pct,
            'dias_con_datos':        row['dias_con_datos'],
            'fuente':                'db',
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reportes/permanencia-por-zona')
def reportes_permanencia_por_zona():
    """Permanencia real por zona -- las 3 zonas definidas del local (Caja,
    Gondolas, Salon; cada camara tiene su propia fila en 'zonas', se agrupan
    por 'tipo'). Minutos en cada zona, POR CLIENTE (cliente_id), con la misma
    regla de tiempo visto que el KPI de permanencia (sql_tiempo_visto): el
    tiempo que aporta cada punto se le asigna a la zona del punto, asi la suma
    de las zonas de un cliente es su permanencia total. Con esa serie por
    cliente se calcula el promedio ('minutos_por_visitante' es el mismo numero)
    y la MAXIMA. Mismas camaras que el KPI: sin CAMARAS_EXCLUIDAS_DE_CONTEO (1 y
    3 miran el mismo sector que la 4, ver GRUPOS_CAMARA) -- antes las sumaba y
    el promedio por zona no se podia comparar con el KPI. Excluye empleados."""
    NOMBRES_TIPO  = {'caja': 'Caja', 'gondola': 'Góndolas', 'otro': 'Salón'}
    desde, hasta = rango_de_request()      # ?desde=&hasta= opcionales (filtros del dashboard)
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'zonas': [], 'fuente': 'sin_bd'})

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT zona_tipo AS tipo, cliente_id, SUM(segundos)::float AS segundos
            FROM """ + sql_tiempo_visto(filtro_conteo()) + """ pv
            WHERE zona_tipo IS NOT NULL
            GROUP BY zona_tipo, cliente_id
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta, **PARAMS_TIEMPO_VISTO})
        rows = cur.fetchall()
        cur.close(); conn.close()

        por_tipo = {}
        for r in rows:
            por_tipo.setdefault(r['tipo'], []).append(r['segundos'] / 60)

        zonas = []
        for tipo, minutos_por_cliente in por_tipo.items():
            visitantes      = len(minutos_por_cliente)
            minutos_totales = sum(minutos_por_cliente)
            zonas.append({
                'tipo':                    tipo,
                'nombre':                  NOMBRES_TIPO.get(tipo, tipo),
                'permanencia_promedio_min':round(minutos_totales / visitantes, 1) if visitantes else 0,
                'permanencia_maxima_min':  round(max(minutos_por_cliente), 1) if visitantes else 0,
                # 'minutos_por_visitante' se mantiene por compatibilidad con el
                # grafico de barras existente -- es el mismo valor que el promedio.
                'minutos_por_visitante':   round(minutos_totales / visitantes, 1) if visitantes else 0,
                'visitantes':              visitantes,
                'minutos_totales':         round(minutos_totales, 1),
            })

        total_min = sum(z['minutos_totales'] for z in zonas) or 1
        for z in zonas:
            z['pct'] = round(z['minutos_totales'] / total_min * 100)

        zonas.sort(key=lambda z: z['minutos_por_visitante'], reverse=True)

        return jsonify({'zonas': zonas, 'fuente': 'db'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

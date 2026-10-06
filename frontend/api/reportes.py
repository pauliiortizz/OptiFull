"""Endpoints de reportes agregados (tendencias, congestion, zonas, etc.)."""
from flask import jsonify

from .blueprint import api_bp
from .db import _get_conn, CAMARAS_EXCLUIDAS_DE_CONTEO, rango_de_request, sql_rango

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


@api_bp.route('/reportes/tendencia-semanal')
def reportes_tendencia_semanal():
    """Promedio real de personas UNICAS detectadas por dia de la semana: agrupa
    todas las sesiones (videos analizados) por su fecha calendario, contando
    cada cliente real una sola vez por dia (via cliente_id, que reidentifica
    apariciones del mismo cliente en distintas sesiones/camaras), y despues
    promedia esos totales diarios entre todas las fechas que cayeron en cada
    dia de la semana. Excluye CAMARAS_EXCLUIDAS_DE_CONTEO (camaras que miran
    el mismo lugar que otra ya contada -- ver comentario junto a la
    constante)."""
    dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'labels': dias, 'promedio': [0]*7, 'dias_con_datos': [0]*7, 'fuente': 'sin_bd'})

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH por_dia AS (
                SELECT s.inicio::date AS fecha,
                       COUNT(DISTINCT COALESCE(p.cliente_id, p.id)) AS cantidad
                FROM sesiones_video s
                JOIN personas p ON p.sesion_id = s.id
                JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
                WHERE raiz.es_empleado = FALSE AND s.camara_id NOT IN %(excl)s
                GROUP BY s.inicio::date
            )
            SELECT EXTRACT(DOW FROM fecha)::int AS dow,
                   ROUND(AVG(cantidad))::int    AS promedio,
                   COUNT(*)                     AS dias_con_datos
            FROM por_dia
            GROUP BY dow
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO})
        rows = cur.fetchall()
        cur.close(); conn.close()

        # Postgres: dow 0=domingo..6=sabado -> reindexar a Lun(0)..Dom(6)
        promedio       = [0] * 7
        dias_con_datos = [0] * 7
        for r in rows:
            idx = (r['dow'] + 6) % 7
            promedio[idx]       = r['promedio']
            dias_con_datos[idx] = r['dias_con_datos']

        return jsonify({'labels': dias, 'promedio': promedio, 'dias_con_datos': dias_con_datos, 'fuente': 'db'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reportes/permanencia-semanal')
def reportes_permanencia_semanal():
    """Permanencia real promedio (en minutos) por dia de la semana: para cada
    cliente real (cliente_id) y fecha calendario, suma sus 'visitas' (segmentos
    de presencia sin huecos -- igual que cargar_permanencias_db) de ese dia, y
    promedia esos totales entre todos los clientes que pasaron ese dia. Despues
    promedia esos promedios diarios entre todas las fechas que cayeron en cada
    dia de la semana, igual que reportes_tendencia_semanal pero con tiempo de
    permanencia en vez de cantidad de personas."""
    dias = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'labels': dias, 'promedio': [0]*7, 'dias_con_datos': [0]*7, 'fuente': 'sin_bd'})

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH permanencia_por_cliente_dia AS (
                SELECT v.entrada::date                  AS fecha,
                       COALESCE(p.cliente_id, p.id)      AS cliente_id,
                       SUM(v.duracion_seg)               AS duracion_seg
                FROM visitas v
                JOIN personas p    ON p.id = v.persona_id
                JOIN sesiones_video sv ON sv.id = p.sesion_id
                JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
                WHERE raiz.es_empleado = FALSE AND sv.camara_id NOT IN %(excl)s
                GROUP BY v.entrada::date, COALESCE(p.cliente_id, p.id)
            ),
            por_dia AS (
                SELECT fecha, AVG(duracion_seg) / 60 AS promedio_min
                FROM permanencia_por_cliente_dia
                GROUP BY fecha
            )
            SELECT EXTRACT(DOW FROM fecha)::int AS dow,
                   ROUND(AVG(promedio_min))::int AS promedio,
                   COUNT(*)                      AS dias_con_datos
            FROM por_dia
            GROUP BY dow
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO})
        rows = cur.fetchall()
        cur.close(); conn.close()

        # Postgres: dow 0=domingo..6=sabado -> reindexar a Lun(0)..Dom(6)
        promedio       = [0] * 7
        dias_con_datos = [0] * 7
        for r in rows:
            idx = (r['dow'] + 6) % 7
            promedio[idx]       = r['promedio']
            dias_con_datos[idx] = r['dias_con_datos']

        return jsonify({'labels': dias, 'promedio': promedio, 'dias_con_datos': dias_con_datos, 'fuente': 'db'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/reportes/congestion-horaria')
def reportes_congestion_horaria():
    """Horarios estimados de congestion: cuanta gente (personas UNICAS reales,
    via cliente_id) hubo presente en camara durante cada franja horaria, en
    cada dia de la semana. Usa 'visitas' (segmentos de presencia real, sin
    huecos -- igual que cargar_permanencias_db) expandidos hora por hora con
    generate_series: una visita de 15:40 a 16:20 cuenta como presente tanto
    en el bucket de las 15hs como en el de las 16hs. Se promedia entre todas
    las fechas calendario que cayeron en cada dia de la semana, asi el
    resultado no depende de cuantos dias de cada tipo se analizaron todavia,
    y permite ver que un viernes al mediodia tiene mas gente que un martes."""
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
                'fuente': 'sin_bd',
            })

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH ocupacion AS (
                SELECT
                    gs                              AS hora_ts,
                    COALESCE(p.cliente_id, p.id)     AS cliente_id
                FROM visitas v
                JOIN personas p    ON p.id = v.persona_id
                JOIN sesiones_video sv ON sv.id = p.sesion_id
                JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
                CROSS JOIN LATERAL generate_series(
                    date_trunc('hour', v.entrada),
                    date_trunc('hour', v.salida),
                    interval '1 hour'
                ) AS gs
                WHERE raiz.es_empleado = FALSE AND sv.camara_id NOT IN %(excl)s
                  AND """ + sql_rango('v.entrada') + """
            ),
            por_dia_hora AS (
                SELECT
                    hora_ts::date                   AS fecha,
                    EXTRACT(HOUR FROM hora_ts)::int AS hora,
                    COUNT(DISTINCT cliente_id)      AS cantidad
                FROM ocupacion
                GROUP BY hora_ts::date, EXTRACT(HOUR FROM hora_ts)
            )
            SELECT
                EXTRACT(DOW FROM fecha)::int AS dow,
                hora,
                ROUND(AVG(cantidad))::int    AS promedio,
                COUNT(*)                     AS dias_con_datos
            FROM por_dia_hora
            GROUP BY dow, hora
            ORDER BY dow, hora
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': desde, 'hasta': hasta})
        rows = cur.fetchall()
        cur.close(); conn.close()

        # Postgres: dow 0=domingo..6=sabado -> reindexar a Lun(0)..Dom(6)
        matriz         = [[0] * 24 for _ in dias]
        dias_con_datos = [[0] * 24 for _ in dias]
        for r in rows:
            idx = (r['dow'] + 6) % 7
            matriz[idx][r['hora']]         = r['promedio']
            dias_con_datos[idx][r['hora']] = r['dias_con_datos']

        picos = detectar_picos(matriz, dias_con_datos, dias)
        pico = picos[0] if picos else None

        return jsonify({
            'dias': dias, 'horas': horas,
            'matriz': matriz, 'dias_con_datos': dias_con_datos,
            'pico': pico, 'picos': picos, 'fuente': 'db',
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
    una sola camara por grupo."""
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'promedio': None, 'dias_con_datos': 0, 'fuente': 'sin_bd'})

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            WITH por_dia AS (
                SELECT s.inicio::date AS fecha,
                       COUNT(DISTINCT COALESCE(p.cliente_id, p.id)) AS cantidad
                FROM sesiones_video s
                JOIN personas p ON p.sesion_id = s.id
                JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
                WHERE raiz.es_empleado = FALSE AND s.camara_id NOT IN %(excl)s
                GROUP BY s.inicio::date
            )
            SELECT ROUND(AVG(cantidad))::int AS promedio, COUNT(*) AS dias_con_datos
            FROM por_dia
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO})
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
    Agrupa las apariciones de personas por cliente_id real y dia calendario;
    si la suma de tiempo REAL detectado ese dia (via 'visitas', sin huecos --
    ver cargar_permanencias_db) supera el umbral, se sugiere."""
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'candidatos': [], 'umbral_horas': UMBRAL_HORAS_POSIBLE_EMPLEADO, 'fuente': 'sin_bd'})

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                raiz.id                                        AS cliente_id,
                p.primera_deteccion::date                      AS fecha,
                COUNT(DISTINCT p.id)                            AS apariciones,
                ROUND(SUM(v.duracion_seg) / 60)::int            AS minutos_totales,
                MIN(v.entrada)                                  AS primera_hora,
                MAX(v.salida)                                   AS ultima_hora
            FROM personas p
            JOIN visitas  v    ON v.persona_id = p.id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
            WHERE raiz.es_empleado = FALSE AND sv.camara_id NOT IN %(excl)s
            GROUP BY raiz.id, p.primera_deteccion::date
            HAVING SUM(v.duracion_seg) >= %(umbral)s
            ORDER BY minutos_totales DESC
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'umbral': UMBRAL_HORAS_POSIBLE_EMPLEADO * 3600})
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
    no duplicar el mismo mostrador visto por 2 camaras)."""
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
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO})
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
    por 'tipo'). Estima minutos en cada zona, POR CLIENTE (cliente_id), a
    partir de la cantidad de puntos de trayectoria con esa zona_id (se guarda
    un punto cada TRAYECTORIA_INTERVALO_SEG segundos por persona -- ver
    deteccion/config.py); con esa serie por cliente se calcula tanto el
    promedio (antes 'minutos_por_visitante': total de la zona / visitantes,
    matematicamente el mismo numero) como la MAXIMA (el cliente que mas
    tiempo paso ahi). A diferencia de reportes que cuentan personas
    (CAMARAS_EXCLUIDAS_DE_CONTEO), esto NO excluye ninguna camara -- las 4
    aportan su propia Zona Gondola/Salon, son espacios fisicos DISTINTOS
    entre camaras (a diferencia de Zona Caja, donde 1/3/4 miran el mismo
    mostrador -- ver GRUPOS_CAMARA). Excluye empleados (raiz.es_empleado)."""
    INTERVALO_SEG = 10.0  # debe coincidir con TRAYECTORIA_INTERVALO_SEG en deteccion/config.py
    NOMBRES_TIPO  = {'caja': 'Caja', 'gondola': 'Góndolas', 'otro': 'Salón'}
    desde, hasta = rango_de_request()      # ?desde=&hasta= opcionales (filtros del dashboard)
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'zonas': [], 'fuente': 'sin_bd'})

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                z.tipo                              AS tipo,
                COALESCE(p.cliente_id, p.id)         AS cliente_id,
                COUNT(*)                             AS puntos
            FROM trayectorias t
            JOIN zonas z       ON z.id = t.zona_id
            JOIN personas p    ON p.id = t.persona_id
            JOIN personas raiz ON raiz.id = COALESCE(p.cliente_id, p.id)
            WHERE raiz.es_empleado = FALSE
              AND """ + sql_rango('t.timestamp') + """
            GROUP BY z.tipo, COALESCE(p.cliente_id, p.id)
        """, {'desde': desde, 'hasta': hasta})
        rows = cur.fetchall()
        cur.close(); conn.close()

        por_tipo = {}
        for r in rows:
            por_tipo.setdefault(r['tipo'], []).append(r['puntos'] * INTERVALO_SEG / 60)

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

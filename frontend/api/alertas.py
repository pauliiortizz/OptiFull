"""Endpoints de 'alertas' reales (tabla 'alertas', ver db/schema.sql y
deteccion/pipeline/eventos.py) -- reemplaza los datos mock de AlertsPage."""
import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from flask import Response, jsonify, request, send_from_directory

from .aprendizaje_empleados import descartar_por_cliente, puntuar
from .blueprint import api_bp
from .configuracion import historial_umbral_espera, leer_configuracion
from .db import CAMARAS_EXCLUIDAS_DE_CONTEO, PARAMS_TIEMPO_VISTO, _get_conn, filtro_conteo, sql_tiempo_visto
from .paths import BASE
from .reportes import UMBRAL_HORAS_POSIBLE_EMPLEADO
from .reportes_datos import Filtros, esperas_en_caja, puntos_cerca_de_caja
from .seguridad import ruta_dentro

# Solo 'posible_hurto' se genera hoy (ver Persistencia.guardar_evento) -- los
# demas tipos existen en el schema para alertas futuras (stock, colas, etc.)
# que todavia no tiene ningun modulo que las inserte.
_TITULOS = {
    'posible_hurto':        'Posible hurto detectado',
    'salida_sin_pagar':     'Salida sin pagar',
    'permanencia_excesiva': 'Permanencia excesiva',
    'zona_restringida':     'Zona restringida',
    'posible_empleado':     'Persona posiblemente empleada',
    'espera_excesiva':      'Espera larga en caja',
    'otro':                 'Alerta',
}
# Dos niveles: 'warn' (Warning) para lo que hay que mirar -- un posible hurto y las demas alertas de seguridad -- e
# 'info' para lo que solo pide una decision, como confirmar si alguien es empleado. Antes los hurtos eran 'critical'.
_SEVERIDADES = {
    'posible_hurto':        'warn',
    'salida_sin_pagar':     'warn',
    'permanencia_excesiva': 'warn',
    'zona_restringida':     'warn',
    'posible_empleado':     'info',
    'espera_excesiva':      'warn',
    'otro':                 'info',
}

# Segundos de margen ANTES del momento exacto de la alerta para que el clip
# (ver /api/sessions/<id>/clip en video.py) arranque con un poco de contexto,
# no justo en el instante detectado -- mismo criterio que usa list_sessions()
# en video.py ("5 s antes del evento").
_MARGEN_CLIP_SEG = 8

# Carpeta (en la raiz del proyecto) donde deteccion/pipeline/evidencia.py guarda la evidencia cuando Supabase Storage
# no responde; sus rutas relativas se sirven bajo /api/evidencias/.
EVIDENCIAS_DIR = os.path.join(os.path.dirname(BASE), 'evidencias')


def _url_evidencia(ruta):
    """URL de un archivo de evidencia: las de Storage ya son URLs completas; las del respaldo local son rutas
    relativas a la carpeta 'evidencias/' y se sirven por /api/evidencias/."""
    if not ruta:
        return None
    return ruta if ruta.startswith(('http://', 'https://')) else f"/api/evidencias/{ruta.replace(chr(92), '/')}"


def _evidencia_para_front(evidencia):
    """Evidencia guardada (JSON) -> {video, frames:[{url, etiqueta, ts}]} con las URLs listas para el navegador,
    o None si la alerta no tiene evidencia (alertas viejas, de videos grabados, o la subida todavia no termino)."""
    if not evidencia or not evidencia.get('frames'):
        return None
    return {
        'video':  _url_evidencia(evidencia.get('video')),
        'frames': [{'url': _url_evidencia(f.get('url')), 'etiqueta': f.get('etiqueta', ''), 'ts': f.get('ts')}
                   for f in evidencia['frames']],
    }


def _rutas_de_evidencia(evidencia):
    """Todos los archivos guardados de una evidencia (clip + frames), tal como quedaron en alertas.evidencia."""
    if not evidencia:
        return []
    rutas = [evidencia.get('video')] + [f.get('url') for f in evidencia.get('frames') or []]
    return [r for r in rutas if r]


def _borrar_de_storage(urls):
    """Borra de Supabase Storage los archivos con estas URLs publicas (las que arma deteccion/pipeline/storage.py:
    <SUPABASE_URL>/storage/v1/object/public/<bucket>/<ruta>), con un pedido por bucket. Solo toca URLs del propio
    proyecto de Supabase. Devuelve cuantos se borraron (0 si Storage no esta configurado o no responde)."""
    base  = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
    clave = os.environ.get('SUPABASE_SERVICE_KEY')
    prefijo = f"{base}/storage/v1/object/public/"
    por_bucket = {}
    for url in urls:
        if base and url.startswith(prefijo):
            bucket, _, ruta = url[len(prefijo):].partition('/')
            if bucket and ruta:
                por_bucket.setdefault(bucket, []).append(urllib.parse.unquote(ruta.split('?')[0]))
    if not por_bucket or not clave:
        if por_bucket:
            print('[Evidencia] SUPABASE_URL/SUPABASE_SERVICE_KEY no configurados: no se pueden borrar los archivos de Storage')
        return 0
    borrados = 0
    for bucket, rutas in por_bucket.items():
        pedido = urllib.request.Request(
            f"{base}/storage/v1/object/{bucket}", method='DELETE', data=json.dumps({'prefixes': rutas}).encode(),
            headers={'Authorization': f'Bearer {clave}', 'apikey': clave, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(pedido, timeout=10) as r:
                borrados += len(json.loads(r.read() or b'[]'))
        except Exception as e:
            print(f'[Evidencia] No se pudieron borrar {len(rutas)} archivos del bucket {bucket}: {e}')
    return borrados


def borrar_archivos_evidencia(evidencia):
    """Borra los archivos de una evidencia: los de Storage y los del respaldo local (carpeta evidencias/, sin salir
    de ella). Devuelve cuantos archivos se borraron."""
    rutas = _rutas_de_evidencia(evidencia)
    borrados = _borrar_de_storage([r for r in rutas if r.startswith(('http://', 'https://'))])
    carpetas = set()
    for ruta in rutas:
        if ruta.startswith(('http://', 'https://')):
            continue
        local = ruta_dentro(EVIDENCIAS_DIR, ruta.replace(chr(92), '/'))
        if local:
            os.remove(local)
            borrados += 1
            carpetas.add(os.path.dirname(local))
    for carpeta in carpetas:   # la carpeta alerta_<id>/ queda vacia
        if os.path.abspath(carpeta) != os.path.abspath(EVIDENCIAS_DIR) and not os.listdir(carpeta):
            os.rmdir(carpeta)
    return borrados


def _alertas_posible_empleado(cur):
    """Alertas 'Persona posiblemente empleada': personas (por cliente_id real) con mas de UMBRAL_HORAS_POSIBLE_EMPLEADO
    de tiempo VISTO en un mismo dia (sql_tiempo_visto, la misma regla que el KPI de permanencia y
    /reportes/posibles-empleados). No se guardan en 'alertas': se arman al consultar, y el usuario las resuelve diciendo si es empleado o no (POST /personas/<id>/empleado). Las que
    ya resolvio quedan en la lista como 'resueltas'. Necesita personas.foto_url y personas.empleado_revisado (ver
    db/schema.sql); si todavia no existen, devuelve [] para no romper el resto de las alertas."""
    try:
        cur.execute("""
            WITH por_dia AS (
                SELECT cliente_id,
                       ts::date                                  AS fecha,
                       SUM(segundos)                             AS segundos,
                       SUM(segundos) FILTER (WHERE zona_tipo = 'caja')    AS seg_caja,
                       SUM(segundos) FILTER (WHERE zona_tipo = 'gondola') AS seg_gondola,
                       SUM(segundos) FILTER (WHERE zona_tipo = 'otro')    AS seg_otro,
                       MIN(ts)                                   AS primera_hora,
                       MAX(ts)                                   AS ultima_hora,
                       MODE() WITHIN GROUP (ORDER BY camara_id)  AS camara_id,   -- la camara que mas lo vio
                       ARRAY_AGG(DISTINCT persona_id)            AS apariciones
                FROM """ + sql_tiempo_visto(filtro_conteo(), "raiz.empleado_revisado = TRUE OR raiz.es_empleado = FALSE") + """ pv
                GROUP BY cliente_id, ts::date
            )
            SELECT d.cliente_id, d.fecha, ROUND(d.segundos / 60)::int AS minutos,
                   d.segundos, d.seg_caja, d.seg_gondola, d.seg_otro,
                   d.primera_hora, d.ultima_hora, d.camara_id,
                   COALESCE(raiz.descripcion_visual,
                            (SELECT p.descripcion_visual FROM personas p
                             WHERE p.id = ANY(d.apariciones) AND p.descripcion_visual IS NOT NULL LIMIT 1)) AS descripcion_visual,
                   COALESCE(raiz.foto_url,
                            (SELECT p.foto_url FROM personas p
                             WHERE p.id = ANY(d.apariciones) AND p.foto_url IS NOT NULL LIMIT 1)) AS foto_url,
                   raiz.empleado_revisado                    AS revisado,
                   raiz.es_empleado                          AS es_empleado
            FROM por_dia d
            JOIN personas raiz ON raiz.id = d.cliente_id
            -- los dias que superan el umbral son las alertas; los de las personas ya revisadas (aunque hayan estado
            -- menos) son ademas los ejemplos de los que aprende el modelo
            WHERE d.segundos >= %(umbral)s OR raiz.empleado_revisado
            ORDER BY d.ultima_hora DESC
        """, {'excl': CAMARAS_EXCLUIDAS_DE_CONTEO, 'desde': None, 'hasta': None,
              'umbral': UMBRAL_HORAS_POSIBLE_EMPLEADO * 3600, **PARAMS_TIEMPO_VISTO})
        rows = cur.fetchall()
    except Exception:
        cur.connection.rollback()
        return []

    # Lo que se aprendio de las alertas ya resueltas (ver aprendizaje_empleados.py): cada candidato abierto sale con
    # su parecido a los empleados confirmados, y los que se parecen claramente a clientes confirmados no se levantan.
    modelo = puntuar(rows)
    revisadas = len({r['cliente_id'] for r in rows if r['revisado']})
    umbral_seg = UMBRAL_HORAS_POSIBLE_EMPLEADO * 3600

    alertas = []
    for r in rows:
        if float(r['segundos'] or 0) < umbral_seg:
            continue   # solo sirvio de ejemplo para el modelo
        if not r['revisado'] and descartar_por_cliente(modelo, r):
            continue
        horas, minutos = divmod(r['minutos'], 60)
        desc = (f"Estuvo {horas} h {minutos:02d} min en la tienda el {r['fecha']:%d/%m} "
                f"({r['primera_hora']:%H:%M}–{r['ultima_hora']:%H:%M}). Un cliente no suele quedarse tanto: "
                f"confirmá si es empleado para excluirlo de las métricas.")
        if r['prob_empleado'] is not None:
            parecido = ('se parece a los empleados que confirmaste' if r['prob_empleado'] >= 0.5
                        else 'se parece más a los clientes que confirmaste')
            motivos = f": {', '.join(r['motivos'])}" if r['motivos'] else ''
            desc += (f" Según las {revisadas} personas que ya revisaste, {parecido} "
                     f"({round(r['prob_empleado'] * 100)}% de probabilidad de empleado){motivos}.")
        if r['revisado']:
            desc = "Marcada como empleada: excluida de las métricas." if r['es_empleado']                 else "Confirmada como cliente: sigue contando en las métricas."
        alertas.append({
            'id':          f"emp-{r['cliente_id']}-{r['fecha']:%Y%m%d}",
            'tipo':        'posible_empleado',
            'persona_id':  r['cliente_id'],
            'sev':         _SEVERIDADES['posible_empleado'],
            'title':       _TITULOS['posible_empleado'],
            'desc':        desc,
            'zone':        'Tienda',
            'secuencia':   [],
            'cam':         r['camara_id'],
            'ts':          int(r['ultima_hora'].timestamp() * 1000),
            'status':      'resolved' if r['revisado'] else 'open',
            'sesion_id':   None,
            'offset_seg':  0,
            'evidencia':   None,
            'foto':        _url_evidencia(r['foto_url']),
            'es_empleado': bool(r['es_empleado']),
            'minutos':     r['minutos'],
            'prob_empleado': None if r['prob_empleado'] is None else round(r['prob_empleado'], 3),
        })
    return alertas


# Las alertas de espera en caja se calculan al consultar (como las de posible empleado) con el umbral de
# la pagina Configuracion, sobre los ultimos DIAS_ALERTAS_CAJA dias. No traen video ni foto ni muestran estado: sin
# resolver van con status None, y las que el usuario resuelve (se recuerda su id en 'alertas_caja_resueltas', ver
# db/schema.sql) con 'resolved', para que salgan de la vista de las abiertas.
DIAS_ALERTAS_CAJA = 7
_CREAR_RESUELTAS = """
    CREATE TABLE IF NOT EXISTS alertas_caja_resueltas (
        id           TEXT       PRIMARY KEY,
        resuelta_en  TIMESTAMP  NOT NULL DEFAULT NOW()
    )"""


def _hay_archivo(ruta):
    """True si el video original de la sesion esta en este servidor (no si era una camara en vivo o se analizo en
    la PC del local)."""
    return bool(ruta) and os.path.isfile(ruta)


def umbral_que_dispara(espera, historial):
    """Minutos del umbral que convierte a 'espera' en alerta, o None. Cada umbral rige desde que se guardo
    hasta el siguiente cambio (historial_umbral_espera): hay alerta si en algun momento de la espera, mientras regia
    un umbral, la persona ya llevaba esperando al menos ese umbral. Asi un cambio de umbral solo afecta de ahi en
    adelante: no vuelve alertas esperas viejas ni borra las que ya habia."""
    inicio = espera['inicio']
    fin = inicio + timedelta(seconds=espera['segundos'])
    for i, (desde, minutos) in enumerate(historial):
        hasta = historial[i + 1][0] if i + 1 < len(historial) else datetime.max
        momento = max(desde, inicio + timedelta(minutes=minutos))   # primer instante en que este umbral la dispara
        if momento <= fin and momento < hasta:
            return minutos
    return None


def _minutos(seg):
    """Segundos -> minutos para mostrar ('4', '4,5')."""
    return f"{seg / 60:.1f}".replace('.0', '').replace('.', ',')


def _alertas_caja(cur):
    """Alertas 'Espera larga en caja': un cliente que espero al menos el umbral de minutos vigente en ese momento
    (ver umbral_que_dispara), con el mismo criterio de cercania a la caja que el reporte de espera
    (reportes_datos.puntos_cerca_de_caja). Si falta algo en la base devuelve [] para no romper el resto de las
    alertas."""
    try:
        historial = historial_umbral_espera(cur, leer_configuracion(cur)['umbrales']['wait'])
        hoy = date.today()
        cerca = puntos_cerca_de_caja(cur, Filtros(desde=hoy - timedelta(days=DIAS_ALERTAS_CAJA - 1), hasta=hoy))
        esperas = []
        for e in esperas_en_caja(cerca):
            umbral = umbral_que_dispara(e, historial)
            if umbral is not None:
                esperas.append({**e, 'umbral': umbral})
        resueltas = set()
        if esperas:
            cur.execute(_CREAR_RESUELTAS)
            cur.execute("SELECT id FROM alertas_caja_resueltas")
            resueltas = {r['id'] for r in cur.fetchall()}
        cur.connection.commit()
    except Exception:
        cur.connection.rollback()
        return []
    def id_de(e):
        return f"espera-{e['camara_id']}-{e['persona_id']}-{int(e['inicio'].timestamp())}"

    return [{
        'id': id_de(e),
        'tipo': 'espera_excesiva', 'persona_id': e['persona_id'], 'sev': _SEVERIDADES['espera_excesiva'],
        'title': _TITULOS['espera_excesiva'],
        'desc': (f"Un cliente esperó {_minutos(e['segundos'])} min en la caja ({e['inicio']:%d/%m %H:%M}–"
                 f"{e['fin']:%H:%M}). El umbral vigente en ese momento era {_minutos(e['umbral'] * 60)} min."),
        'zone': 'Caja', 'secuencia': [], 'cam': e['camara_id'],
        'ts': int(e['fin'].timestamp() * 1000),
        'status': 'resolved' if id_de(e) in resueltas else None, 'sesion_id': None, 'offset_seg': 0, 'evidencia': None,
    } for e in esperas]


@api_bp.route('/alertas')
def listar_alertas():
    """Alertas reales generadas por el pipeline (ver
    Persistencia.guardar_evento) -- hoy solo 'posible_hurto', insertado
    cuando eventos.clasificar_evento() da POSIBLE_HURTO. Se hace JOIN con
    'eventos' por (persona_id, timestamp) -- ambas filas se insertan en la
    MISMA llamada con el mismo timestamp calculado, asi que ese par identifica
    sin ambiguedad el evento que genero esta alerta puntual (una persona
    puede tener mas de una fila en 'eventos' si tuvo varias visitas)."""
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify([])

        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT al.id, al.persona_id, al.tipo, al.timestamp, al.descripcion, al.resuelta,
                   p.sesion_id, sv.camara_id, sv.inicio AS sesion_inicio,
                   sv.archivo_path, e.secuencia_zonas, al.evidencia
            FROM alertas al
            JOIN personas p ON p.id = al.persona_id
            JOIN sesiones_video sv ON sv.id = p.sesion_id
            LEFT JOIN eventos e ON e.persona_id = al.persona_id AND e.timestamp = al.timestamp
            ORDER BY al.timestamp DESC
        """)
        rows = cur.fetchall()
        extra = _alertas_posible_empleado(cur) + _alertas_caja(cur)
        cur.close(); conn.close()

        alertas = []
        for r in rows:
            zonas = r['secuencia_zonas'] or []
            zona = zonas[-1] if zonas else 'Desconocida'
            offset_seg = 0
            if r['sesion_inicio']:
                offset_seg = max(0, int((r['timestamp'] - r['sesion_inicio']).total_seconds()) - _MARGEN_CLIP_SEG)
            alertas.append({
                'id':          r['id'],
                'tipo':        r['tipo'],
                'persona_id':  r['persona_id'],
                'sev':         _SEVERIDADES.get(r['tipo'], 'info'),
                'title':       _TITULOS.get(r['tipo'], 'Alerta'),
                'desc':        r['descripcion'] or '',
                'zone':        zona,
                'secuencia':   zonas,
                'cam':         r['camara_id'],
                'ts':          int(r['timestamp'].timestamp() * 1000),
                'status':      'resolved' if r['resuelta'] else 'open',
                'sesion_id':   r['sesion_id'],
                'offset_seg':  offset_seg,
                # el clip de /api/sessions/<id>/clip sale del video original: solo existe si ese archivo esta en
                # este servidor (no si se analizo en la PC del local o era una camara en vivo)
                'video_disponible': _hay_archivo(r.get('archivo_path')),
                'evidencia':   _evidencia_para_front(r['evidencia']),
            })
        alertas.extend(extra)
        alertas.sort(key=lambda a: a['ts'], reverse=True)
        return jsonify(alertas)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/alertas/<int:alerta_id>/resolver', methods=['POST'])
def resolver_alerta(alerta_id):
    """Marca (o revierte) 'alertas.resuelta'. body opcional {"resuelta": bool},
    default true -- mismo patron que POST /personas/<id>/empleado. Al resolverla se borra su evidencia (clip y
    frames, de Storage o del respaldo local) y se limpia alertas.evidencia: primero la base, para que nunca quede
    una referencia a un archivo que ya no existe; despues los archivos."""
    body     = request.get_json(silent=True) or {}
    resuelta = bool(body.get('resuelta', True))
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'error': 'sin conexion a la base de datos'}), 503

        cur = conn.cursor()
        evidencia = None
        if resuelta:
            cur.execute("SELECT evidencia FROM alertas WHERE id = %s FOR UPDATE", (alerta_id,))
            fila = cur.fetchone()
            evidencia = fila[0] if fila else None
            cur.execute("UPDATE alertas SET resuelta = TRUE, evidencia = NULL WHERE id = %s", (alerta_id,))
        else:
            cur.execute("UPDATE alertas SET resuelta = FALSE WHERE id = %s", (alerta_id,))
        actualizado = cur.rowcount > 0
        conn.commit()
        cur.close(); conn.close()

        if not actualizado:
            return jsonify({'error': f'no existe alerta con id {alerta_id}'}), 404
        respuesta = {'id': alerta_id, 'resuelta': resuelta}
        if evidencia:
            respuesta['evidencia_borrada'] = borrar_archivos_evidencia(evidencia)
        return jsonify(respuesta)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/alertas/<alerta_id>/resolver', methods=['POST'])
def resolver_alerta_caja(alerta_id):
    """Resuelve (o reabre) una alerta de espera en caja. No estan en 'alertas' (se calculan al consultar), asi que
    se recuerda su id en 'alertas_caja_resueltas'. body opcional {"resuelta": bool}."""
    if not alerta_id.startswith('espera-'):
        return jsonify({'error': f'no existe alerta con id {alerta_id}'}), 404
    resuelta = bool((request.get_json(silent=True) or {}).get('resuelta', True))
    try:
        conn = _get_conn()
        if conn is None:
            return jsonify({'error': 'sin conexion a la base de datos'}), 503
        cur = conn.cursor()
        cur.execute(_CREAR_RESUELTAS)
        if resuelta:
            cur.execute("INSERT INTO alertas_caja_resueltas (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (alerta_id,))
        else:
            cur.execute("DELETE FROM alertas_caja_resueltas WHERE id = %s", (alerta_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({'id': alerta_id, 'resuelta': resuelta})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/evidencias/<path:filename>')
def servir_evidencia(filename):
    """Archivos de evidencia guardados en disco (respaldo cuando Storage no respondio). Una ruta que sale de la
    carpeta se trata igual que un archivo que no existe (ver seguridad.ruta_dentro)."""
    if not ruta_dentro(EVIDENCIAS_DIR, filename):
        return Response('Not Found', status=404)
    return send_from_directory(EVIDENCIAS_DIR, filename)

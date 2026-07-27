"""Streaming/transcodificado de video y endpoints de sesiones/tracking."""
import json
import os
import re

from flask import Response, jsonify, request

from .blueprint import api_bp
from .db import _get_conn as _db_connect
from .paths import VIDEOS_DIR


def _find_ffmpeg():
    import shutil, glob
    if shutil.which('ffmpeg'):
        found = shutil.which('ffmpeg')
        print(f'[ffmpeg] encontrado en PATH: {found}')
        return found
    patterns = [
        r'C:\Users\*\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\ffmpeg.exe',
        r'C:\ProgramData\chocolatey\bin\ffmpeg.exe',
        r'C:\ffmpeg\bin\ffmpeg.exe',
    ]
    for p in patterns:
        matches = glob.glob(p, recursive=True)
        if matches:
            print(f'[ffmpeg] encontrado en: {matches[0]}')
            return matches[0]
    print('[ffmpeg] NO encontrado — clips no disponibles')
    return None


FFMPEG = _find_ffmpeg()


# ── Video: helper de streaming ─────────────────────────────────────────────────

_VIDEO_MIME = {
    'mp4': 'video/mp4', 'mov': 'video/mp4',
    'avi': 'video/x-msvideo', 'mkv': 'video/x-matroska', 'webm': 'video/webm',
}

def _stream_video(path):
    ext  = os.path.splitext(path.lower())[1].lstrip('.')
    mime = _VIDEO_MIME.get(ext, 'video/mp4')
    size = os.path.getsize(path)

    range_hdr = request.headers.get('Range')
    if range_hdr:
        m     = re.search(r'bytes=(\d+)-(\d*)', range_hdr)
        byte1 = int(m.group(1))
        byte2 = int(m.group(2)) if m.group(2) else size - 1
        length = byte2 - byte1 + 1

        def gen_partial():
            with open(path, 'rb') as f:
                f.seek(byte1)
                rem = length
                while rem > 0:
                    chunk = f.read(min(65536, rem))
                    if not chunk:
                        break
                    rem -= len(chunk)
                    yield chunk

        return Response(gen_partial(), 206, headers={
            'Content-Range':  f'bytes {byte1}-{byte2}/{size}',
            'Accept-Ranges':  'bytes',
            'Content-Length': str(length),
            'Content-Type':   mime,
        })

    def gen_full():
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                yield chunk

    return Response(gen_full(), 200, headers={
        'Content-Length': str(size),
        'Content-Type':   mime,
        'Accept-Ranges':  'bytes',
    })


# ── Video: sesiones desde BD ───────────────────────────────────────────────────

@api_bp.route('/sessions')
def list_sessions():
    try:
        import psycopg2.extras
        conn = _db_connect()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Trae el offset del primer evento significativo de cada sesión
        cur.execute("""
            SELECT sv.id, sv.camara_id, sv.inicio, sv.fin, sv.archivo_path,
                   MIN(p.primera_deteccion) AS primer_evento
            FROM sesiones_video sv
            LEFT JOIN personas p ON p.sesion_id = sv.id
                AND p.duracion_total_seg > 10
            GROUP BY sv.id, sv.camara_id, sv.inicio, sv.fin, sv.archivo_path
            ORDER BY sv.inicio DESC
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
        result = []
        for r in rows:
            p      = r['archivo_path'] or ''
            inicio = r['inicio']
            evento = r['primer_evento']
            offset = int((evento - inicio).total_seconds()) if evento and inicio else 0
            result.append({
                'id':         r['id'],
                'camara_id':  r['camara_id'],
                'inicio':     inicio.isoformat() if inicio else None,
                'fin':        r['fin'].isoformat() if r['fin'] else None,
                'nombre':     os.path.basename(p),
                'disponible': os.path.isfile(p),
                'offset_seg': max(0, offset - 5),   # 5 s antes del evento
            })
        return jsonify(result)
    except Exception:
        return jsonify([])


def _session_path(sid):
    conn = _db_connect()
    cur  = conn.cursor()
    cur.execute("SELECT archivo_path FROM sesiones_video WHERE id = %s", (sid,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0] if row else None


@api_bp.route('/sessions/<int:sid>/clip')
def session_clip(sid):
    """Extrae y transcodifica a H.264 el fragmento relevante del video."""
    t_start  = float(request.args.get('t',   0))
    duration = float(request.args.get('dur', 50))

    try:
        path = _session_path(sid)
    except Exception as e:
        print(f'[clip] Error obteniendo ruta de sesion {sid}: {e}')
        return Response(str(e), status=500)

    if not path:
        print(f'[clip] Sesion {sid} no encontrada en BD')
        return Response('Not Found', status=404)
    if not os.path.isfile(path):
        print(f'[clip] Archivo no existe en disco: {path}')
        return Response(f'Archivo no encontrado: {path}', status=404)

    print(f'[clip] sesion={sid} archivo={path} t={t_start}s dur={duration}s')

    import subprocess
    if not FFMPEG:
        print('[clip] ffmpeg no disponible, sirviendo video completo')
        return _stream_video(path)

    cmd = [
        FFMPEG, '-y',
        '-ss', str(t_start),
        '-i', path,
        '-t', str(duration),
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '26',
        '-c:a', 'aac', '-ac', '2',
        '-movflags', 'frag_keyframe+empty_moov',
        '-f', 'mp4',
        'pipe:1',
    ]
    print(f'[clip] cmd: {" ".join(cmd)}')
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def generate():
        try:
            bytes_sent = 0
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                bytes_sent += len(chunk)
                yield chunk
            stderr_out = proc.stderr.read().decode(errors='replace')
            rc = proc.wait()
            print(f'[clip] ffmpeg terminó rc={rc} bytes_enviados={bytes_sent}')
            if rc != 0:
                print(f'[clip] stderr ffmpeg:\n{stderr_out[-1000:]}')
        except Exception as ex:
            print(f'[clip] Error en generate(): {ex}')
            proc.kill()

    return Response(generate(), mimetype='video/mp4',
                    headers={'Cache-Control': 'no-cache'})


@api_bp.route('/sessions/<int:sid>/video')
def session_video(sid):
    try:
        path = _session_path(sid)
    except Exception as e:
        return Response(str(e), status=500)

    if not path:
        return Response('Not Found', status=404)
    if not os.path.isfile(path):
        return Response(f'Archivo no encontrado: {path}', status=404)
    return _stream_video(path)


@api_bp.route('/sessions/<int:sid>/tracking')
def session_tracking(sid):
    """Datos REALES de tracking de un video ya analizado: personas detectadas
    en esa sesion, sus trayectorias (tabla 'trayectorias', muestreadas cada
    TRAYECTORIA_INTERVALO_SEG durante el analisis -- ver deteccion/main.py) y
    las zonas definidas para esa camara. Reemplaza el mapa/lista simulados de
    la pagina de Tracking por el recorrido real de un analisis ya hecho (no
    hay tracking en vivo todavia, ver WipBanner de esa pagina)."""
    try:
        import psycopg2.extras
        conn = _db_connect()
        if conn is None:
            return jsonify(None)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT sv.id, sv.camara_id, sv.inicio, sv.fin, sv.archivo_path,
                   sv.frame_w, sv.frame_h,
                   c.nombre AS camara_nombre
            FROM sesiones_video sv
            LEFT JOIN camaras c ON c.id = sv.camara_id
            WHERE sv.id = %s
        """, (sid,))
        sesion = cur.fetchone()
        if not sesion:
            cur.close(); conn.close()
            return jsonify(None)

        cur.execute("""
            SELECT p.id, COALESCE(p.cliente_id, p.id) AS cliente_id,
                   p.primera_deteccion, p.ultima_deteccion, p.duracion_total_seg,
                   p.metodo_reid, p.es_empleado, p.descripcion_visual
            FROM personas p
            WHERE p.sesion_id = %s
            ORDER BY p.primera_deteccion
        """, (sid,))
        personas = cur.fetchall()

        persona_ids  = [p['id'] for p in personas]
        trayectorias = []
        bounds       = None
        if persona_ids:
            cur.execute("""
                SELECT t.persona_id, t.timestamp, t.centroide_x, t.centroide_y,
                       t.zona_id, z.nombre AS zona_nombre
                FROM trayectorias t
                LEFT JOIN zonas z ON z.id = t.zona_id
                WHERE t.persona_id = ANY(%s)
                ORDER BY t.persona_id, t.timestamp
            """, (persona_ids,))
            trayectorias = cur.fetchall()
            if trayectorias:
                xs = [t['centroide_x'] for t in trayectorias]
                ys = [t['centroide_y'] for t in trayectorias]
                bounds = {'min_x': min(xs), 'max_x': max(xs), 'min_y': min(ys), 'max_y': max(ys)}

        cur.execute(
            "SELECT id, nombre, tipo, poligono FROM zonas WHERE camara_id = %s",
            (sesion['camara_id'],)
        )
        zonas = cur.fetchall()

        cur.close(); conn.close()

        def _iso(v):
            return v.isoformat() if v else None

        return jsonify({
            'sesion': {
                'id':            sesion['id'],
                'camara_id':     sesion['camara_id'],
                'camara_nombre': sesion['camara_nombre'],
                'inicio':        _iso(sesion['inicio']),
                'fin':           _iso(sesion['fin']),
                'nombre':        os.path.basename(sesion['archivo_path'] or ''),
                'frame_w':       sesion['frame_w'],
                'frame_h':       sesion['frame_h'],
            },
            'personas': [{
                'id':                 p['id'],
                'cliente_id':         p['cliente_id'],
                'primera_deteccion':  _iso(p['primera_deteccion']),
                'ultima_deteccion':   _iso(p['ultima_deteccion']),
                'duracion_seg':       p['duracion_total_seg'],
                'metodo_reid':        p['metodo_reid'],
                'es_empleado':        p['es_empleado'],
                'descripcion_visual': json.loads(p['descripcion_visual']) if p['descripcion_visual'] else None,
            } for p in personas],
            'trayectorias': [{
                'persona_id':  t['persona_id'],
                'timestamp':   _iso(t['timestamp']),
                'cx':          t['centroide_x'],
                'cy':          t['centroide_y'],
                'zona_id':     t['zona_id'],
                'zona_nombre': t['zona_nombre'],
            } for t in trayectorias],
            'zonas': [{
                'id':       z['id'],
                'nombre':   z['nombre'],
                'tipo':     z['tipo'],
                'poligono': z['poligono'],
            } for z in zonas],
            'bounds': bounds,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/cameras/<int:camara_id>/tracking')
def camera_tracking(camara_id):
    """Igual que /sessions/<sid>/tracking, pero junta TODAS las sesiones
    (videos) de una camara que caigan en un mismo dia calendario -- para que
    el mapa de trayectorias se pueda ver por CAMARA (todo lo que grabo ese
    dia, en orden cronologico real) en vez de video por video. 'fecha'
    (query param, YYYY-MM-DD) es opcional -- sin ella, se usa el dia mas
    reciente con sesiones analizadas de esa camara. Tambien devuelve la
    lista de fechas disponibles para esa camara, para armar un selector de
    dia en el frontend."""
    try:
        import psycopg2.extras
        conn = _db_connect()
        if conn is None:
            return jsonify(None)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT DISTINCT inicio::date AS fecha
            FROM sesiones_video WHERE camara_id = %s
            ORDER BY fecha DESC
        """, (camara_id,))
        fechas = [r['fecha'].isoformat() for r in cur.fetchall()]
        if not fechas:
            cur.close(); conn.close()
            return jsonify(None)

        fecha_param = request.args.get('fecha')
        fecha = fecha_param if fecha_param in fechas else fechas[0]

        cur.execute("""
            SELECT sv.id, sv.frame_w, sv.frame_h, sv.inicio, sv.fin, c.nombre AS camara_nombre
            FROM sesiones_video sv
            LEFT JOIN camaras c ON c.id = sv.camara_id
            WHERE sv.camara_id = %s AND sv.inicio::date = %s
            ORDER BY sv.inicio
        """, (camara_id, fecha))
        sesiones = cur.fetchall()
        if not sesiones:
            cur.close(); conn.close()
            return jsonify(None)
        sesion_ids = [s['id'] for s in sesiones]

        cur.execute("""
            SELECT p.id, COALESCE(p.cliente_id, p.id) AS cliente_id,
                   p.primera_deteccion, p.ultima_deteccion, p.duracion_total_seg,
                   p.metodo_reid, p.es_empleado, p.descripcion_visual
            FROM personas p
            WHERE p.sesion_id = ANY(%s)
            ORDER BY p.primera_deteccion
        """, (sesion_ids,))
        personas = cur.fetchall()

        persona_ids  = [p['id'] for p in personas]
        trayectorias = []
        bounds       = None
        if persona_ids:
            cur.execute("""
                SELECT t.persona_id, t.timestamp, t.centroide_x, t.centroide_y,
                       t.zona_id, z.nombre AS zona_nombre
                FROM trayectorias t
                LEFT JOIN zonas z ON z.id = t.zona_id
                WHERE t.persona_id = ANY(%s)
                ORDER BY t.persona_id, t.timestamp
            """, (persona_ids,))
            trayectorias = cur.fetchall()
            if trayectorias:
                xs = [t['centroide_x'] for t in trayectorias]
                ys = [t['centroide_y'] for t in trayectorias]
                bounds = {'min_x': min(xs), 'max_x': max(xs), 'min_y': min(ys), 'max_y': max(ys)}

        cur.execute(
            "SELECT id, nombre, tipo, poligono FROM zonas WHERE camara_id = %s",
            (camara_id,)
        )
        zonas = cur.fetchall()

        cur.close(); conn.close()

        def _iso(v):
            return v.isoformat() if v else None

        frame_w = next((s['frame_w'] for s in sesiones if s['frame_w']), None)
        frame_h = next((s['frame_h'] for s in sesiones if s['frame_h']), None)

        return jsonify({
            'sesion': {
                'camara_id':     camara_id,
                'camara_nombre': sesiones[0]['camara_nombre'],
                'fecha':         fecha,
                'inicio':        _iso(min(s['inicio'] for s in sesiones)),
                'fin':           _iso(max(s['fin'] for s in sesiones if s['fin']) if any(s['fin'] for s in sesiones) else None),
                'nombre':        f"Cámara {camara_id} · {fecha}",
                'n_videos':      len(sesiones),
                'frame_w':       frame_w,
                'frame_h':       frame_h,
            },
            'fechas_disponibles': fechas,
            'personas': [{
                'id':                 p['id'],
                'cliente_id':         p['cliente_id'],
                'primera_deteccion':  _iso(p['primera_deteccion']),
                'ultima_deteccion':   _iso(p['ultima_deteccion']),
                'duracion_seg':       p['duracion_total_seg'],
                'metodo_reid':        p['metodo_reid'],
                'es_empleado':        p['es_empleado'],
                'descripcion_visual': json.loads(p['descripcion_visual']) if p['descripcion_visual'] else None,
            } for p in personas],
            'trayectorias': [{
                'persona_id':  t['persona_id'],
                'timestamp':   _iso(t['timestamp']),
                'cx':          t['centroide_x'],
                'cy':          t['centroide_y'],
                'zona_id':     t['zona_id'],
                'zona_nombre': t['zona_nombre'],
            } for t in trayectorias],
            'zonas': [{
                'id':       z['id'],
                'nombre':   z['nombre'],
                'tipo':     z['tipo'],
                'poligono': z['poligono'],
            } for z in zonas],
            'bounds': bounds,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Video: carpeta local videos/ ───────────────────────────────────────────────

@api_bp.route('/videos')
def list_videos():
    if not os.path.isdir(VIDEOS_DIR):
        return jsonify([])
    exts  = {'.mp4', '.avi', '.mkv', '.mov', '.webm'}
    files = sorted(f for f in os.listdir(VIDEOS_DIR)
                   if os.path.splitext(f.lower())[1] in exts)
    return jsonify(files)


@api_bp.route('/video/<path:filename>')
def serve_video(filename):
    safe = os.path.normpath(os.path.join(VIDEOS_DIR, filename))
    if not safe.startswith(os.path.normpath(VIDEOS_DIR)):
        return Response('Forbidden', status=403)
    if not os.path.isfile(safe):
        return Response('Not Found', status=404)
    return _stream_video(safe)

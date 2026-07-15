"""
OptiFull API — sirve estadísticas desde la BD Supabase (Postgres) o fallback a CSV.
"""
from flask import Flask, Blueprint, jsonify, send_from_directory, Response, request
import os, csv, io, re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app    = Flask(__name__)
api_bp = Blueprint('api', __name__, url_prefix='/api')

BASE        = os.path.dirname(os.path.abspath(__file__))
CSV_PATH    = os.path.join(BASE, '..', 'permanencia.csv')
VIDEOS_DIR  = os.path.join(BASE, '..', 'videos')
FONDOS_DIR  = os.path.join(BASE, 'fondos')


def _imagen_url(imagen_path):
    """'imagen_path' puede ser una URL completa de Supabase Storage (subida
    nueva) o un nombre de archivo local (fallback de cuando Storage no estaba
    configurado). Devuelve la URL lista para usar en el frontend."""
    if not imagen_path:
        return None
    if imagen_path.startswith('http://') or imagen_path.startswith('https://'):
        return imagen_path
    return f'/api/heatmap/image/{os.path.basename(imagen_path)}'


def _get_conn():
    """Abre una conexion a Supabase si DATABASE_URL esta configurada en .env."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    import psycopg2
    return psycopg2.connect(database_url, connect_timeout=3)

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


# ── Carga de datos ─────────────────────────────────────────────────────────────

def cargar_csv():
    rows = []
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append({
                'id':           int(r['id']),
                'entrada':      r['entrada'],
                'salida':       r['salida'],
                'duracion_seg': float(r['duracion_seg']),
                'duracion_min': float(r['duracion_min']),
            })
    return rows


def cargar_db():
    conn = _get_conn()
    if conn is None:
        return None
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id,
                   TO_CHAR(primera_deteccion, 'HH24:MI:SS') AS entrada,
                   TO_CHAR(ultima_deteccion,  'HH24:MI:SS') AS salida,
                   duracion_total_seg                       AS duracion_seg
            FROM personas
            ORDER BY id
        """)
        rows = cur.fetchall()
        for r in rows:
            r['duracion_min'] = round(r['duracion_seg'] / 60, 2)
        cur.close(); conn.close()
        return rows or None
    except Exception:
        return None


# ── Cálculo de estadísticas ────────────────────────────────────────────────────

def calcular_stats(rows):
    duraciones = [r['duracion_min'] for r in rows]
    validas    = [d for d in duraciones if d > 0.5]   # filtra detecciones ruido

    ORDEN = ['< 1 min', '1-5 min', '5-15 min', '15-60 min', '> 1 hora']

    def bucket(d):
        s = d * 60
        if s < 60:  return '< 1 min'
        if d < 5:   return '1-5 min'
        if d < 15:  return '5-15 min'
        if d < 60:  return '15-60 min'
        return '> 1 hora'

    conteo = {b: 0 for b in ORDEN}
    for d in duraciones:
        conteo[bucket(d)] += 1

    return {
        'personas_totales':             len(rows),
        'personas_validas':             len(validas),
        'permanencia_promedio_min':     round(sum(validas) / len(validas), 1) if validas else 0,
        'permanencia_maxima_min':       round(max(duraciones), 1) if duraciones else 0,
        'permanencia_minima_valida_min':round(min(validas), 1) if validas else 0,
        'distribucion': [{'rango': b, 'count': conteo[b]} for b in ORDEN],
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@api_bp.route('/stats')
def api_stats():
    rows   = cargar_db()
    fuente = 'db' if rows is not None else 'csv'
    if rows is None:
        try:
            rows = cargar_csv()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    stats = calcular_stats(rows)
    stats['fuente']                = fuente
    stats['tiempo_real_disponible'] = False
    return jsonify(stats)


@api_bp.route('/personas')
def api_personas():
    rows   = cargar_db()
    fuente = 'db' if rows is not None else 'csv'
    if rows is None:
        try:
            rows = cargar_csv()
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'fuente': fuente, 'registros': rows})


# ── Exportación CSV ───────────────────────────────────────────────────────────

@api_bp.route('/export/csv')
def export_csv():
    rows = cargar_db()
    if rows is None:
        try:
            rows = cargar_csv()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    stats = calcular_stats(rows)
    buf = io.StringIO()
    w   = csv.writer(buf)

    # Encabezado con resumen
    w.writerow(['# OptiFull — Reporte de Permanencia'])
    w.writerow([f'# Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")}'])
    w.writerow([f'# Fuente: {"Base de datos" if cargar_db() is not None else "CSV local"}'])
    w.writerow([])
    w.writerow(['## Resumen'])
    w.writerow(['Personas totales', stats['personas_totales']])
    w.writerow(['Permanencia promedio (min)', stats['permanencia_promedio_min']])
    w.writerow(['Permanencia maxima (min)', stats['permanencia_maxima_min']])
    w.writerow(['Permanencia minima valida (min)', stats['permanencia_minima_valida_min']])
    w.writerow([])
    w.writerow(['## Distribucion'])
    w.writerow(['Rango', 'Cantidad'])
    for d in stats['distribucion']:
        w.writerow([d['rango'], d['count']])
    w.writerow([])

    # Detalle por persona
    w.writerow(['## Detalle por persona'])
    w.writerow(['ID', 'Entrada', 'Salida', 'Duracion (seg)', 'Duracion (min)'])
    for r in rows:
        w.writerow([r['id'], r['entrada'], r['salida'],
                    r['duracion_seg'], r['duracion_min']])

    fname = f'optifull_reporte_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    return Response(
        buf.getvalue().encode('utf-8-sig'),   # utf-8-sig para que Excel lo abra bien
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'}
    )


# ── Exportación PDF ────────────────────────────────────────────────────────────

@api_bp.route('/export/pdf')
def export_pdf():
    rows = cargar_db()
    if rows is None:
        try:
            rows = cargar_csv()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    stats  = calcular_stats(rows)
    fuente = 'Base de datos' if cargar_db() is not None else 'CSV local'

    from fpdf import FPDF

    def t(s):
        """Elimina caracteres fuera del rango latin-1 que fpdf no soporta."""
        return s.replace('—', '-').replace('–', '-').encode('latin-1', 'replace').decode('latin-1')

    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 14)
            self.set_text_color(37, 99, 168)
            self.cell(0, 10, t('OptiFull - Reporte de Permanencia'), align='L')
            self.set_font('Helvetica', '', 9)
            self.set_text_color(120, 120, 120)
            self.cell(0, 10, datetime.now().strftime('%d/%m/%Y  %H:%M'), align='R')
            self.ln(4)
            self.set_draw_color(220, 220, 220)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(6)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, t(f'Pagina {self.page_no()}  -  Fuente: {fuente}'), align='C')

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── KPIs ──
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, t('Resumen estadistico'), ln=True)
    pdf.ln(2)

    kpis = [
        ('Personas analizadas',          f"{stats['personas_totales']} registros"),
        ('Permanencia promedio',          f"{stats['permanencia_promedio_min']} min"),
        ('Permanencia maxima',            f"{stats['permanencia_maxima_min']} min"),
        ('Permanencia minima valida',     f"{stats['permanencia_minima_valida_min']} min"),
        ('Registros validos (> 0.5 min)', f"{stats['personas_validas']}"),
    ]
    pdf.set_font('Helvetica', '', 10)
    for label, val in kpis:
        pdf.set_text_color(80, 80, 80)
        pdf.cell(90, 7, t(label))
        pdf.set_text_color(30, 30, 30)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 7, t(val), ln=True)
        pdf.set_font('Helvetica', '', 10)

    # ── Distribución ──
    pdf.ln(6)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, t('Distribucion de permanencia'), ln=True)
    pdf.ln(2)

    pdf.set_fill_color(245, 247, 250)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(80, 7, 'Rango', border='B', fill=True)
    pdf.cell(40, 7, 'Personas', border='B', fill=True, align='C')
    pdf.ln()

    pdf.set_font('Helvetica', '', 10)
    total = stats['personas_totales'] or 1
    for d in stats['distribucion']:
        pct = round(d['count'] / total * 100, 1)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(80, 7, d['rango'])
        pdf.cell(40, 7, f"{d['count']}  ({pct}%)", align='C')
        pdf.ln()

    # ── Tabla detalle ──
    pdf.ln(6)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, t('Detalle por persona'), ln=True)
    pdf.ln(2)

    pdf.set_fill_color(245, 247, 250)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(60, 60, 60)
    for col, w in [('ID', 15), ('Entrada', 40), ('Salida', 40), ('Seg.', 30), ('Min.', 30)]:
        pdf.cell(w, 7, col, border='B', fill=True, align='C')
    pdf.ln()

    pdf.set_font('Helvetica', '', 9)
    for i, r in enumerate(rows):
        if i % 2 == 0:
            pdf.set_fill_color(250, 251, 253)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(15, 6.5, str(r['id']),          fill=True, align='C')
        pdf.cell(40, 6.5, str(r['entrada']),      fill=True, align='C')
        pdf.cell(40, 6.5, str(r['salida']),       fill=True, align='C')
        pdf.cell(30, 6.5, str(r['duracion_seg']), fill=True, align='C')
        pdf.cell(30, 6.5, str(r['duracion_min']), fill=True, align='C')
        pdf.ln()

    buf  = io.BytesIO(pdf.output())
    fname = f'optifull_reporte_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf'
    return Response(
        buf.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'}
    )


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

def _db_connect():
    return _get_conn()


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


# ── Heatmap ───────────────────────────────────────────────────────────────────

@api_bp.route('/heatmap/latest')
def heatmap_latest():
    try:
        import psycopg2.extras
        conn = _db_connect()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT mc.*,
                   c.nombre  AS camara_nombre,
                   z.nombre  AS zona_mas_caliente_nombre
            FROM   mapas_calor mc
            LEFT JOIN camaras c ON c.id = mc.camara_id
            LEFT JOIN zonas   z ON z.id = mc.zona_id_mas_caliente
            ORDER  BY mc.periodo_inicio DESC
            LIMIT  1
        """)
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            return jsonify(None)

        # Ranking de zonas desde trayectorias de esa sesion
        zonas_ranking = []
        if row.get('sesion_id'):
            cur.execute("""
                SELECT z.nombre, COUNT(*) AS detecciones
                FROM   trayectorias t
                JOIN   zonas z ON z.id = t.zona_id
                WHERE  t.persona_id IN (
                    SELECT id FROM personas WHERE sesion_id = %s
                )
                GROUP  BY z.id, z.nombre
                ORDER  BY detecciones DESC
            """, (row['sesion_id'],))
            zona_rows = cur.fetchall()
            total = sum(r['detecciones'] for r in zona_rows) or 1
            zonas_ranking = [
                {'nombre': r['nombre'],
                 'detecciones': r['detecciones'],
                 'pct': round(r['detecciones'] / total * 100)}
                for r in zona_rows
            ]

        cur.close(); conn.close()

        return jsonify({
            'id':                row['id'],
            'camara_id':         row['camara_id'],
            'camara_nombre':     row['camara_nombre'],
            'periodo_inicio':    row['periodo_inicio'].isoformat() if row['periodo_inicio'] else None,
            'periodo_fin':       row['periodo_fin'].isoformat()    if row['periodo_fin']    else None,
            'imagen_url':        _imagen_url(row.get('imagen_path')),
            'punto_max_x':       row['punto_max_x'],
            'punto_max_y':       row['punto_max_y'],
            'valor_maximo':      row['valor_maximo'],
            'area_activa_pct':   row['area_activa_pct'],
            'concentracion':     row['concentracion'],
            'total_detecciones': row['total_detecciones'],
            'frames_procesados': row['frames_procesados'],
            'zona_mas_caliente': row['zona_mas_caliente_nombre'],
            'zonas_ranking':     zonas_ranking,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/heatmap/camara/<int:camara_id>')
def heatmap_camara(camara_id):
    """Mapa de calor acumulado (todas las sesiones combinadas) de una camara."""
    try:
        import psycopg2.extras
        conn = _db_connect()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT mcc.*,
                   c.nombre AS camara_nombre,
                   z.nombre AS zona_mas_caliente_nombre
            FROM   mapas_calor_camara mcc
            LEFT JOIN camaras c ON c.id = mcc.camara_id
            LEFT JOIN zonas   z ON z.id = mcc.zona_id_mas_caliente
            WHERE  mcc.camara_id = %s
        """, (camara_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return jsonify(None)

        return jsonify({
            'camara_id':           row['camara_id'],
            'camara_nombre':       row['camara_nombre'],
            'imagen_url':          _imagen_url(row.get('imagen_path')),
            'punto_max_x':         row['punto_max_x'],
            'punto_max_y':         row['punto_max_y'],
            'valor_maximo':        row['valor_maximo'],
            'area_activa_pct':     row['area_activa_pct'],
            'concentracion':       row['concentracion'],
            'total_detecciones':   row['total_detecciones'],
            'frames_procesados':   row['frames_procesados'],
            'sesiones_combinadas': row['sesiones_combinadas'],
            'zona_mas_caliente':   row['zona_mas_caliente_nombre'],
            'actualizado_en':      row['actualizado_en'].isoformat() if row['actualizado_en'] else None,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/heatmap/image/<path:filename>')
def serve_heatmap_image(filename):
    root     = os.path.dirname(BASE)   # proyecto raiz (un nivel arriba de frontend/)
    img_path = os.path.join(root, filename)
    if not os.path.isfile(img_path):
        return Response('Not Found', status=404)
    return send_from_directory(root, filename)


@api_bp.route('/heatmap/fondo/<int:camara_id>')
def heatmap_fondo(camara_id):
    """Foto fija del local (fondo vacio) para esa camara, subida una unica vez
    a mano en frontend/fondos/camara_<id>.<ext> -- el frontend superpone el
    heatmap combinado (con canal alfa) arriba de esta imagen via CSS."""
    if not os.path.isdir(FONDOS_DIR):
        return Response('Not Found', status=404)
    for ext in ('jpg', 'jpeg', 'png', 'webp'):
        filename = f'camara_{camara_id}.{ext}'
        if os.path.isfile(os.path.join(FONDOS_DIR, filename)):
            return send_from_directory(FONDOS_DIR, filename)
    return Response('Not Found', status=404)


# ── Registro del Blueprint y archivos estáticos ────────────────────────────────

app.register_blueprint(api_bp)

@app.route('/')
def index():
    return send_from_directory(BASE, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(BASE, path)

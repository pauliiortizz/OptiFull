"""
OptiFull API — sirve estadísticas desde la BD Supabase (Postgres) o fallback a CSV.

Paquete dividido por responsabilidad:
  paths.py      rutas de archivos/directorios (CSV, videos, fondos)
  blueprint.py  Blueprint compartido 'api' (url_prefix='/api')
  db.py         acceso a datos (Supabase/CSV) y CAMARAS_EXCLUIDAS_DE_CONTEO
  stats.py      calcular_stats() y endpoints /stats, /personas, /personas/<id>/empleado
  reportes.py   endpoints /reportes/*
  reportes_export.py  Reportes 2.0: /reportes/opciones y /reportes/exportar (PDF/XLSX/CSV/PNG);
                reportes_datos.py (consultas), reportes_graficos.py (matplotlib),
                reportes_formatos.py (generadores de archivo)
  alertas.py    endpoints /alertas* (alertas reales, ver deteccion/pipeline/eventos.py)
  export.py     endpoints /export/csv, /export/pdf
  video.py      streaming/transcodificado y endpoints /sessions*, /videos, /cameras/*
  heatmap.py    endpoints /heatmap/*
  productos.py  endpoints /productos/* (caja en vivo, stock, metricas -- ver
                deteccion_productos/README.md)
  health.py     endpoint /health (liveness + estado de BD + commit, ver .github/workflows)
"""
import os

from dotenv import load_dotenv
from flask import Flask, send_from_directory

load_dotenv()

from .paths import DIST
from .blueprint import api_bp
from .stats import calcular_stats  # re-exportado: usado por test_calcular_stats.py

app = Flask(__name__)

# Importar los modulos de rutas registra sus endpoints en api_bp via el
# decorador @api_bp.route (ver blueprint.py) -- deben importarse antes de
# app.register_blueprint(api_bp) mas abajo.
from . import stats, reportes, reportes_export, alertas, export, video, heatmap, productos, health  # noqa: F401,E402

app.register_blueprint(api_bp)

_BUILD_MISSING = f"""
<!doctype html><meta charset="utf-8">
<body style="background:#090a0f;color:#f8fafc;font:13px ui-monospace,monospace;padding:32px">
  <h1 style="font-size:14px">Falta el build del frontend</h1>
  <p style="color:#94a3b8">No se encontro <code>frontend/dist/</code>. Corre:</p>
  <pre style="background:#0f1117;border:1px solid #1e2230;padding:10px 14px">cd frontend &amp;&amp; npm install &amp;&amp; npm run build</pre>
  <p style="color:#64748b">y volve a cargar esta pagina. (Para desarrollo con hot-reload usa <code>npm run dev</code> en su lugar.)</p>
</body>
"""


# El SPA de React (Vite) se sirve desde frontend/dist/ una vez compilado con
# `npm run build`. En desarrollo con hot-reload, usar `npm run dev` (Vite
# proxea /api hacia este mismo backend, ver vite.config.js).
@app.route('/')
def index():
    if not os.path.isfile(os.path.join(DIST, 'index.html')):
        return _BUILD_MISSING, 503
    return send_from_directory(DIST, 'index.html')


@app.route('/<path:path>')
def static_files(path):
    full = os.path.join(DIST, path)
    if os.path.isfile(full):
        return send_from_directory(DIST, path)
    # Fallback de SPA: rutas desconocidas devuelven index.html.
    if not os.path.isfile(os.path.join(DIST, 'index.html')):
        return _BUILD_MISSING, 503
    return send_from_directory(DIST, 'index.html')

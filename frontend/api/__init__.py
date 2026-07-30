"""
OptiFull API — sirve estadísticas desde la BD Supabase (Postgres) o fallback a CSV.

Paquete dividido por responsabilidad:
  paths.py      rutas de archivos/directorios (CSV, videos, fondos)
  blueprint.py  Blueprint compartido 'api' (url_prefix='/api')
  db.py         acceso a datos (Supabase/CSV) y CAMARAS_EXCLUIDAS_DE_CONTEO
  stats.py      calcular_stats() y endpoints /stats, /personas, /personas/<id>/empleado
  reportes.py   endpoints /reportes/*
  alertas.py    endpoints /alertas* (alertas reales, ver deteccion/pipeline/eventos.py)
  export.py     endpoints /export/csv, /export/pdf
  video.py      streaming/transcodificado y endpoints /sessions*, /videos, /cameras/*
  heatmap.py    endpoints /heatmap/*
  productos.py  endpoints /productos/* (caja en vivo, stock, metricas -- ver
                deteccion_productos/README.md)
"""
from dotenv import load_dotenv
from flask import Flask, send_from_directory

load_dotenv()

from .paths import BASE
from .blueprint import api_bp
from .stats import calcular_stats  # re-exportado: usado por test_calcular_stats.py

app = Flask(__name__)

# Importar los modulos de rutas registra sus endpoints en api_bp via el
# decorador @api_bp.route (ver blueprint.py) -- deben importarse antes de
# app.register_blueprint(api_bp) mas abajo.
from . import stats, reportes, alertas, export, video, heatmap, productos  # noqa: F401,E402

app.register_blueprint(api_bp)


@app.route('/')
def index():
    return send_from_directory(BASE, 'index.html')


@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(BASE, path)

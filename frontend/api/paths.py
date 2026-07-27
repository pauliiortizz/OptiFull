"""Rutas de archivos y directorios usadas por el resto del paquete 'api'."""
import os

BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # frontend/
CSV_PATH    = os.path.join(BASE, '..', 'permanencia.csv')
VIDEOS_DIR  = os.path.join(BASE, '..', 'videos')
FONDOS_DIR  = os.path.join(BASE, 'fondos')

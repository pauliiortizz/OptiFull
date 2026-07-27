"""Blueprint compartido: cada modulo de rutas (stats, reportes, export, video,
heatmap) le agrega sus propios endpoints via el decorador @api_bp.route."""
from flask import Blueprint

api_bp = Blueprint('api', __name__, url_prefix='/api')

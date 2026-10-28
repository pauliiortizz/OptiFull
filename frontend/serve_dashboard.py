"""Arranca el dashboard OptiFull.

Uso:
  python serve_dashboard.py            -> panel local en http://localhost:8080 (desarrollo)
  python serve_dashboard.py --agente   -> agente local para la compu de la caja: abre el panel de PRODUCCION, que
                                          toma de esta compu el video del celular y el detector (ver api/agente.py)
"""
import os
import sys
import threading
import webbrowser

from api import app

PORT = 8080
PANEL_PRODUCCION = os.environ.get('AGENTE_PANEL_URL', 'https://optifull.onrender.com')

if __name__ == '__main__':
    modo_agente = '--agente' in sys.argv[1:]
    if modo_agente:
        print(f'Agente local corriendo en http://127.0.0.1:{PORT} (video del celular y detector de productos).')
        print(f'Abrí el panel de producción: {PANEL_PRODUCCION}')
    else:
        print(f'Dashboard corriendo en http://localhost:{PORT}')
    print('Presiona Ctrl+C para detener el servidor.')
    destino = PANEL_PRODUCCION if modo_agente else f'http://localhost:{PORT}'
    threading.Timer(0.8, lambda: webbrowser.open(destino)).start()
    # threaded=True: sin esto, Flask atiende un solo pedido a la vez -- el
    # streaming de video (varios "Range requests" chiquitos) queda atascado
    # detras de cualquier request lenta (ej. un intento de conexion a
    # Postgres que tarda en fallar por connect_timeout, ver
    # frontend/api/productos.py) que caiga justo en el medio.
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False, threaded=True)

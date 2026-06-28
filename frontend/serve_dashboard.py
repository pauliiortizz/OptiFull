"""Arranca el dashboard OptiFull. Uso: python serve_dashboard.py"""
import webbrowser, threading
from api import app

PORT = 8080

if __name__ == '__main__':
    print(f'Dashboard corriendo en http://localhost:{PORT}')
    print('Presiona Ctrl+C para detener el servidor.')
    threading.Timer(0.8, lambda: webbrowser.open(f'http://localhost:{PORT}')).start()
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

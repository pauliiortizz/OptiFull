"""Aviso de alerta nueva al backend, para que la mande como notificacion push (ver frontend/api/push.py).

El detector en vivo (RTSP) llama a avisar_alerta(alerta_id) cuando guarda una alerta. El pedido va en un hilo
aparte para no frenar el analisis: en el plan gratuito de Render el backend puede estar dormido y tardar hasta
un minuto en despertar. El backend lee la alerta de la base y la manda a los navegadores suscriptos; aca solo
viaja el id, nunca el texto.

Configuracion (.env del detector): OPTIFULL_API_URL (ej. https://optifull.onrender.com) y PUSH_TOKEN (el mismo
del backend, ver db/generar_claves_push.py). Sin alguna de las dos no se avisa nada.
"""
import json
import threading
import time
import urllib.error
import urllib.request

TIMEOUT_SEG = 90            # alcanza para que Render despierte el backend
REINTENTO_TRAS_SEG = 5      # un solo reintento si el primer pedido falla (red caida, backend reiniciando)


def _enviar(url_api: str, token: str, alerta_id: int) -> bool:
    pedido = urllib.request.Request(
        f"{url_api.rstrip('/')}/api/push/alerta",
        data=json.dumps({'alerta_id': alerta_id}).encode(),
        headers={'Content-Type': 'application/json', 'X-Push-Token': token},
        method='POST',
    )
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_SEG) as r:
            print(f"[Push] Alerta {alerta_id} avisada: {r.read().decode(errors='replace')[:120]}")
            return True
    except urllib.error.HTTPError as e:
        print(f"[Push] El backend rechazo el aviso de la alerta {alerta_id} (HTTP {e.code}).")
        return e.code in (400, 403, 404)   # no tiene sentido reintentar: token o alerta incorrectos
    except Exception as e:
        print(f"[Push] No se pudo avisar la alerta {alerta_id}: {e}")
        return False


def _avisar(url_api: str, token: str, alerta_id: int) -> None:
    if not _enviar(url_api, token, alerta_id):
        time.sleep(REINTENTO_TRAS_SEG)
        _enviar(url_api, token, alerta_id)


def crear_aviso(url_api, token):
    """Devuelve la funcion avisar(alerta_id) para conectar a Persistencia.on_alerta_nueva, o None si falta
    configuracion (asi main.py no conecta nada y no se intenta en cada alerta)."""
    if not url_api or not token:
        print("[Push] OPTIFULL_API_URL / PUSH_TOKEN no configurados: las alertas no se avisaran como notificacion push.")
        return None

    def avisar(alerta_id: int) -> threading.Thread:
        hilo = threading.Thread(target=_avisar, args=(url_api, token, alerta_id), daemon=True)
        hilo.start()
        return hilo
    return avisar

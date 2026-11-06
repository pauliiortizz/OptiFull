"""Genera el par de claves VAPID de las notificaciones push (ver frontend/api/push.py) y un PUSH_TOKEN.

    python db/generar_claves_push.py

Imprime las cuatro variables listas para copiar:
  - VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT y PUSH_TOKEN en el servicio de Render (QA y produccion);
  - PUSH_TOKEN y OPTIFULL_API_URL tambien en el .env del detector (deteccion/config.py).
Se generan UNA sola vez: si se cambian las claves VAPID, todos los navegadores tienen que volver a activar las
notificaciones desde Configuracion.
"""
import base64
import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b'=').decode()


def generar():
    privada = ec.generate_private_key(ec.SECP256R1())
    publica = privada.public_key().public_bytes(serialization.Encoding.X962,
                                                serialization.PublicFormat.UncompressedPoint)
    return {
        'VAPID_PUBLIC_KEY':  _b64url(publica),
        'VAPID_PRIVATE_KEY': _b64url(privada.private_numbers().private_value.to_bytes(32, 'big')),
        'VAPID_SUBJECT':     'https://optifull.onrender.com',
        'PUSH_TOKEN':        secrets.token_urlsafe(32),
    }


if __name__ == '__main__':
    for nombre, valor in generar().items():
        print(f'{nombre}={valor}')

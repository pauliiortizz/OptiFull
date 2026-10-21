"""Controles compartidos de la API para datos que vienen del usuario: rutas de archivo e IPs de camaras.

Ver DEF-023 a DEF-027 en docs/calidad/defectos.md.
"""
import ipaddress
import os
import urllib.parse

from werkzeug.security import safe_join

EXTENSIONES_VIDEO = {'.mp4', '.avi', '.mkv', '.mov', '.webm'}


def ruta_dentro(carpeta, relativa):
    """Ruta absoluta de 'relativa' dentro de 'carpeta', o None si sale de ella ('..', ruta absoluta, unidad de
    Windows) o no es un archivo. Usa safe_join, el mismo control que send_from_directory: comparar con
    startswith deja pasar carpetas vecinas con el mismo prefijo (DEF-027)."""
    ruta = safe_join(os.path.abspath(carpeta), relativa)
    return ruta if ruta and os.path.isfile(ruta) else None


def es_ip_de_red_local(host):
    """True solo para una IP literal de una red local (10.x, 172.16-31.x, 192.168.x, fc00::/7). No alcanza con
    ipaddress.is_private, que tambien es True para 127.0.0.1 (el propio servidor), 0.0.0.0 y 169.254.x
    (metadatos de la nube): por ahi un pedido llegaria a servicios internos (DEF-023)."""
    try:
        ip = ipaddress.ip_address(host or '')
    except ValueError:
        return False
    return (ip.is_private and not ip.is_loopback and not ip.is_link_local
            and not ip.is_unspecified and not ip.is_multicast and not ip.is_reserved)


def es_url_de_camara_local(url, esquemas=('http', 'https', 'rtsp')):
    """URL de una camara de la red local del negocio: esquema permitido y host que es una IP local."""
    partes = urllib.parse.urlsplit(url or '')
    return partes.scheme in esquemas and es_ip_de_red_local(partes.hostname)


def en_la_nube():
    """QA y produccion corren en Render: desde ahi la red local de la tienda (camaras, celular) no existe."""
    return os.environ.get('APP_ENV') in ('qa', 'production')

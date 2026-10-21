"""Aviso por email de cada pedido de demo de la landing (lo usa leads.py).

Arma el correo con la plantilla de "NUEVA SOLICITUD DE DEMO" (texto plano + HTML) y lo envia a
LEADS_EMAIL_DESTINO (por defecto optifull27@gmail.com). Hay dos formas de enviarlo, segun que
variables de entorno esten cargadas (en .env o en el dashboard de Render):

  - RESEND_API_KEY: API HTTPS de Resend (https://resend.com). Es la opcion para Render en plan
    free, que bloquea la salida por los puertos SMTP. Remitente: LEADS_EMAIL_REMITENTE (por
    defecto "OptiFull <onboarding@resend.dev>", que solo puede enviar a la casilla de la cuenta).
  - SMTP_USUARIO + SMTP_CLAVE: SMTP de Gmail (u otro: SMTP_SERVIDOR, SMTP_PUERTO). Con Gmail la
    clave es una "contraseña de aplicacion" (requiere verificacion en dos pasos), no la normal.

Si no hay ninguna configurada, enviar_aviso_lead() devuelve None: el pedido igual queda guardado
en leads.jsonl y el endpoint responde bien (asi la landing sigue funcionando en desarrollo).
"""
import html
import json
import logging
import os
import smtplib
import ssl
import urllib.request
from email.message import EmailMessage

log = logging.getLogger(__name__)

DESTINO_POR_DEFECTO = 'optifull27@gmail.com'
TIMEOUT_S = 12

# Los mismos textos que ve el usuario en el formulario (PROBLEMAS en LandingPage.jsx).
PRIORIDADES = {
    'colas': 'Colas en caja',
    'faltantes': 'Faltantes de stock',
    'picos': 'Horarios pico y turnos',
    'otro': 'Otro',
}

# (etiqueta, clave del lead), en el orden de la plantilla.
CAMPOS = (
    ('Nombre y Apellido', 'nombre'),
    ('Rol / Cargo', 'rol'),
    ('Estación y Localidad', 'estacion'),
    ('Cantidad de Cámaras', 'camaras'),
    ('Prioridad a resolver', 'problema'),
    ('WhatsApp / Email de contacto', 'contacto'),
)
LINEA = '-' * 50


def _una_linea(texto):
    """Sin saltos de linea: los valores van en el asunto (evita inyectar cabeceras)."""
    return ' '.join(str(texto or '').split())


def _valores(lead):
    v = {k: _una_linea(lead.get(k)) or '—' for _, k in CAMPOS}
    v['problema'] = PRIORIDADES.get(lead.get('problema'), v['problema'])
    return v


def armar_aviso(lead):
    """Devuelve (asunto, texto, html) del aviso de un lead."""
    v = _valores(lead)
    asunto = f"Nueva solicitud de demo — {v['nombre']} ({v['estacion']})"
    # el canal de origen (utm_*), si el link lo traia
    origen = ', '.join(f'{k}={_una_linea(x)}' for k, x in lead.items() if k.startswith('utm_') and x)

    texto = '\n'.join([
        LINEA,
        '📩 NUEVA SOLICITUD DE DEMO - OPTIFULL',
        '',
        *(f'• {etiqueta}: {v[k]}' for etiqueta, k in CAMPOS),
        LINEA,
        '',
        f"Recibido: {lead.get('recibido', '')} (UTC)",
        *([f'Origen: {origen}'] if origen else []),
    ])

    filas = ''.join(
        '<tr>'
        f'<td style="padding:8px 14px 8px 0;color:#6b6b63;white-space:nowrap;vertical-align:top">• <b style="color:#1b1b1f">{html.escape(etiqueta)}:</b></td>'
        f'<td style="padding:8px 0;color:#1b1b1f">{html.escape(v[k])}</td>'
        '</tr>'
        for etiqueta, k in CAMPOS
    )
    cuerpo_html = (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;font-size:15px;line-height:1.45;'
        'max-width:560px;margin:0 auto;padding:8px">'
        '<div style="border-top:2px solid #1b1b1f;border-bottom:2px solid #1b1b1f;padding:16px 4px">'
        '<p style="margin:0 0 12px;font-size:17px"><b>📩 NUEVA SOLICITUD DE DEMO - OPTIFULL</b></p>'
        f'<table role="presentation" style="border-collapse:collapse">{filas}</table>'
        '</div>'
        f'<p style="margin:12px 4px 0;font-size:12px;color:#8a877e">Recibido: {html.escape(str(lead.get("recibido", "")))} (UTC)</p>'
        '</div>'
    )
    return asunto, texto, cuerpo_html


def _responder_a(lead):
    """Si el contacto es un email, las respuestas van directo a esa persona."""
    c = _una_linea(lead.get('contacto'))
    return c if '@' in c and ' ' not in c else None


def _por_resend(clave, destino, asunto, texto, cuerpo_html, responder_a):
    datos = {
        'from': os.getenv('LEADS_EMAIL_REMITENTE', 'OptiFull <onboarding@resend.dev>'),
        'to': [destino], 'subject': asunto, 'text': texto, 'html': cuerpo_html,
    }
    if responder_a:
        datos['reply_to'] = responder_a
    req = urllib.request.Request(
        'https://api.resend.com/emails', data=json.dumps(datos).encode('utf-8'), method='POST',
        headers={'Authorization': f'Bearer {clave}', 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        if r.status >= 300:
            raise RuntimeError(f'Resend respondio {r.status}')


def _por_smtp(usuario, clave, destino, asunto, texto, cuerpo_html, responder_a):
    msg = EmailMessage()
    msg['Subject'] = asunto
    msg['From'] = os.getenv('LEADS_EMAIL_REMITENTE', f'OptiFull <{usuario}>')
    msg['To'] = destino
    if responder_a:
        msg['Reply-To'] = responder_a
    msg.set_content(texto)
    msg.add_alternative(cuerpo_html, subtype='html')

    servidor = os.getenv('SMTP_SERVIDOR', 'smtp.gmail.com')
    puerto = int(os.getenv('SMTP_PUERTO', '465'))
    contexto = ssl.create_default_context()
    if puerto == 465:
        with smtplib.SMTP_SSL(servidor, puerto, context=contexto, timeout=TIMEOUT_S) as s:
            s.login(usuario, clave)
            s.send_message(msg)
    else:
        with smtplib.SMTP(servidor, puerto, timeout=TIMEOUT_S) as s:
            s.starttls(context=contexto)
            s.login(usuario, clave)
            s.send_message(msg)


def enviar_aviso_lead(lead):
    """Envia el aviso. True si salio, False si fallo, None si no hay envio configurado."""
    destino = os.getenv('LEADS_EMAIL_DESTINO', DESTINO_POR_DEFECTO)
    asunto, texto, cuerpo_html = armar_aviso(lead)
    responder_a = _responder_a(lead)
    resend = os.getenv('RESEND_API_KEY')
    usuario, clave = os.getenv('SMTP_USUARIO'), os.getenv('SMTP_CLAVE')
    try:
        if resend:
            _por_resend(resend, destino, asunto, texto, cuerpo_html, responder_a)
        elif usuario and clave:
            _por_smtp(usuario, clave, destino, asunto, texto, cuerpo_html, responder_a)
        else:
            log.warning('Pedido de demo sin aviso por email: falta RESEND_API_KEY o SMTP_USUARIO/SMTP_CLAVE')
            return None
        return True
    except Exception:   # noqa: BLE001 -- cualquier falla de red/credenciales se informa igual
        log.exception('No se pudo enviar el aviso del pedido de demo')
        return False

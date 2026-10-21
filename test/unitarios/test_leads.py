"""Tests de POST /api/leads (frontend/api/leads.py) y del aviso por email (frontend/api/correo.py): la plantilla,
el destinatario, la eleccion del medio de envio y la respuesta del endpoint segun salga o no el email.
No se envia nada de verdad: SMTP y Resend se simulan."""
import json

import pytest

from frontend.api import app
from frontend.api import correo
from frontend.api import leads as m

LEAD = {
    'nombre': 'Laura Gómez', 'rol': 'Gerente de tienda', 'estacion': 'YPF Full Av. Colón, Córdoba',
    'camaras': '4 a 8', 'problema': 'colas', 'contacto': 'laura@tienda.com',
}


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'LEADS_PATH', str(tmp_path / 'leads.jsonl'))
    for k in ('RESEND_API_KEY', 'SMTP_USUARIO', 'SMTP_CLAVE', 'LEADS_EMAIL_DESTINO', 'LEADS_EMAIL_REMITENTE'):
        monkeypatch.delenv(k, raising=False)
    app.config['TESTING'] = True
    return app.test_client()


def _guardados():
    with open(m.LEADS_PATH, encoding='utf-8') as f:
        return [json.loads(l) for l in f]


# ── la plantilla ──────────────────────────────────────────────────────────
def test_plantilla_con_todos_los_campos():
    asunto, texto, cuerpo_html = correo.armar_aviso({**LEAD, 'recibido': '2026-10-20T12:00:00+00:00'})
    assert asunto == 'Nueva solicitud de demo — Laura Gómez (YPF Full Av. Colón, Córdoba)'
    assert '📩 NUEVA SOLICITUD DE DEMO - OPTIFULL' in texto
    for linea in ('• Nombre y Apellido: Laura Gómez', '• Rol / Cargo: Gerente de tienda',
                  '• Estación y Localidad: YPF Full Av. Colón, Córdoba', '• Cantidad de Cámaras: 4 a 8',
                  '• Prioridad a resolver: Colas en caja', '• WhatsApp / Email de contacto: laura@tienda.com'):
        assert linea in texto
    assert 'Colas en caja' in cuerpo_html and 'NUEVA SOLICITUD DE DEMO' in cuerpo_html


def test_plantilla_escapa_html_y_saltos_de_linea():
    asunto, _, cuerpo_html = correo.armar_aviso({**LEAD, 'nombre': '<b>Ana</b>\r\nBcc: x@y.com'})
    assert '\n' not in asunto and '\r' not in asunto
    assert '<b>Ana</b>' not in cuerpo_html and '&lt;b&gt;Ana&lt;/b&gt;' in cuerpo_html


def test_campo_vacio_muestra_guion():
    _, texto, _ = correo.armar_aviso({**LEAD, 'rol': ''})
    assert '• Rol / Cargo: —' in texto


# ── el envio ──────────────────────────────────────────────────────────────
def test_sin_configuracion_no_envia(monkeypatch):
    for k in ('RESEND_API_KEY', 'SMTP_USUARIO', 'SMTP_CLAVE'):
        monkeypatch.delenv(k, raising=False)
    assert correo.enviar_aviso_lead(LEAD) is None


def test_smtp_envia_a_optifull(monkeypatch):
    enviados = []

    class SMTPFalso:
        def __init__(self, servidor, puerto, **kw):
            self.servidor, self.puerto = servidor, puerto
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def login(self, u, c):
            self.login_ok = (u, c)
        def send_message(self, msg):
            enviados.append((self.servidor, self.puerto, self.login_ok, msg))

    monkeypatch.delenv('RESEND_API_KEY', raising=False)
    monkeypatch.delenv('LEADS_EMAIL_DESTINO', raising=False)
    monkeypatch.setenv('SMTP_USUARIO', 'optifull27@gmail.com')
    monkeypatch.setenv('SMTP_CLAVE', 'clave-de-aplicacion')
    monkeypatch.setattr(correo.smtplib, 'SMTP_SSL', SMTPFalso)

    assert correo.enviar_aviso_lead(LEAD) is True
    servidor, puerto, login, msg = enviados[0]
    assert (servidor, puerto) == ('smtp.gmail.com', 465)
    assert login == ('optifull27@gmail.com', 'clave-de-aplicacion')
    assert msg['To'] == 'optifull27@gmail.com'
    assert msg['Reply-To'] == 'laura@tienda.com'      # el contacto es un email: se le responde directo
    assert 'Prioridad a resolver: Colas en caja' in msg.get_body(('plain',)).get_content()


def test_whatsapp_no_va_como_reply_to():
    assert correo._responder_a({**LEAD, 'contacto': '+54 9 351 555 1234'}) is None


def test_resend_tiene_prioridad(monkeypatch):
    llamadas = []
    monkeypatch.setenv('RESEND_API_KEY', 're_test')
    monkeypatch.setenv('SMTP_USUARIO', 'x@gmail.com')
    monkeypatch.setenv('SMTP_CLAVE', 'x')
    monkeypatch.setattr(correo, '_por_resend', lambda *a: llamadas.append(a))
    monkeypatch.setattr(correo, '_por_smtp', lambda *a: pytest.fail('no deberia usar SMTP'))
    assert correo.enviar_aviso_lead(LEAD) is True
    assert llamadas[0][1] == 'optifull27@gmail.com'


def test_falla_del_envio_devuelve_false(monkeypatch):
    monkeypatch.setenv('RESEND_API_KEY', 're_test')
    def falla(*a):
        raise OSError('sin red')
    monkeypatch.setattr(correo, '_por_resend', falla)
    assert correo.enviar_aviso_lead(LEAD) is False


# ── el endpoint ───────────────────────────────────────────────────────────
def test_lead_valido_se_guarda_y_responde_ok(cliente, monkeypatch):
    monkeypatch.setattr(m, 'enviar_aviso_lead', lambda lead: True)
    r = cliente.post('/api/leads', json=LEAD)
    assert r.status_code == 201 and r.get_json() == {'ok': True}
    g = _guardados()[0]
    assert g['nombre'] == 'Laura Gómez' and g['aviso_email'] is True


def test_sin_email_configurado_igual_responde_ok(cliente):
    r = cliente.post('/api/leads', json=LEAD)
    assert r.status_code == 201
    assert _guardados()[0]['aviso_email'] is None


def test_si_el_email_falla_responde_502_pero_guarda(cliente, monkeypatch):
    monkeypatch.setattr(m, 'enviar_aviso_lead', lambda lead: False)
    r = cliente.post('/api/leads', json=LEAD)
    assert r.status_code == 502 and r.get_json()['ok'] is False
    assert _guardados()[0]['aviso_email'] is False


def test_lead_incompleto_no_envia(cliente, monkeypatch):
    monkeypatch.setattr(m, 'enviar_aviso_lead', lambda lead: pytest.fail('no deberia enviar'))
    r = cliente.post('/api/leads', json={**LEAD, 'contacto': ''})
    assert r.status_code == 400

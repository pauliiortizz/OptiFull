"""Endpoint /api/leads: pedidos de demo desde la landing (experimento de validacion).

Guarda cada pedido como una linea JSON en leads.jsonl (raiz del repo, ignorado
por git). Es deliberadamente simple: el experimento apunta a 30-50 pedidos, no
necesita tabla ni migracion. Los campos utm_* identifican el canal de origen.
"""
import json
import os
from datetime import datetime, timezone

from flask import jsonify, request

from .blueprint import api_bp
from .paths import BASE

LEADS_PATH = os.path.join(BASE, '..', 'leads.jsonl')

_PROBLEMAS = {'colas', 'faltantes', 'picos', 'otro'}
_CAMPOS_UTM = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content')


def _txt(valor, maximo):
    return str(valor or '').strip()[:maximo]


@api_bp.route('/leads', methods=['POST'])
def crear_lead():
    d = request.get_json(silent=True) or {}
    lead = {
        'nombre':   _txt(d.get('nombre'), 120),
        'contacto': _txt(d.get('contacto'), 160),
        'estacion': _txt(d.get('estacion'), 160),
        'rol':      _txt(d.get('rol'), 40),
        'camaras':  _txt(d.get('camaras'), 20),
        'problema': _txt(d.get('problema'), 20),
    }
    faltan = [k for k in ('nombre', 'contacto', 'estacion', 'camaras') if not lead[k]]
    if faltan or lead['problema'] not in _PROBLEMAS:
        return jsonify({'ok': False, 'faltan': faltan or ['problema']}), 400

    for k in _CAMPOS_UTM:
        lead[k] = _txt(d.get(k), 80)
    lead['recibido'] = datetime.now(timezone.utc).isoformat(timespec='seconds')

    with open(LEADS_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(lead, ensure_ascii=False) + '\n')
    return jsonify({'ok': True}), 201

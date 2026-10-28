"""/heatmap/plano/tiempo y /plano/flujo agrupan en SQL (para que viaje menos desde Supabase). Estos tests cargan
recorridos aleatorios en un Postgres real y verifican que la respuesta sea la MISMA que la de celdas_por_zona y
tramos_por_zona de plano_calor.py aplicadas a todos los puntos crudos (lo que hacian antes los endpoints)."""
import random
from datetime import timedelta

import pytest

from api import app
from api import heatmap as hm
from api.plano_calor import FUENTES_POR_DEFECTO, celdas_por_zona, rango_horario, tramos_por_zona

from conftest import HOY, URL

# Camara 4: gondola y caja que se pisan (en /flujo gana la primera de 'fuentes'), un poligono no rectangular y
# una segunda gondola que no se usa (gana la de id menor). Camara 2: 'otro'. Camara 3: fuente alternativa.
ZONAS = [
    (4, "gondola", [[900, 100], [1850, 150], [1800, 1000], [1000, 950]]),
    (4, "caja", [[100, 300], [1100, 250], [1050, 900], [150, 1000], [400, 600]]),
    (4, "gondola", [[0, 0], [300, 0], [300, 300], [0, 300]]),
    (2, "otro", [[200, 200], [1700, 200], [1700, 900], [200, 900]]),
    (3, "caja", [[0, 0], [1920, 0], [1920, 1080], [0, 1080]]),
]
RESOLUCION = {2: 1920, 3: None, 4: 1280}     # frame_w (None: el endpoint asume 1920x1080)


@pytest.fixture
def recorridos(datos, monkeypatch):
    import psycopg2
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(hm, "_db_connect", lambda: psycopg2.connect(URL))
    for cache in ("_CACHE_PLANO_TIEMPO", "_CACHE_PLANO_FLUJO"):
        monkeypatch.setattr(hm, cache, {"t": 0.0, "clave": None, "version": None, "resp": None})
    rnd = random.Random(7)
    for cam in (2, 3, 4):
        datos.camara(cam)
    for cam, tipo, pol in ZONAS:
        datos.zona(cam, tipo, pol)
    for dia in range(5):
        inicio = HOY + timedelta(days=dia)
        for cam in (2, 3, 4):
            w = RESOLUCION[cam]
            W, H = (w, w * 9 // 16) if w else (1920, 1080)
            sesion = datos.sesion(cam, inicio=inicio, frame_w=w)
            datos.valor("UPDATE sesiones_video SET frame_h = %s WHERE id = %s RETURNING id", (H if w else None, sesion))
            for _ in range(2 if (dia == 4 and cam == 4) else 12):     # dia 4 casi vacio en la camara 4
                empleado = rnd.random() < 0.15
                pid = datos.persona(sesion, inicio=inicio, es_empleado=empleado)
                ts = inicio + timedelta(seconds=rnd.randint(0, 8 * 3600))
                x, y, paso = rnd.uniform(0, W), rnd.uniform(0, H), rnd.choice([0.002, 0.06])
                for _ in range(rnd.randint(2, 40)):
                    x = min(W - 0.5, max(0.0, x + rnd.gauss(0, paso * W)))
                    y = min(H - 0.5, max(0.0, y + rnd.gauss(0, paso * H)))
                    datos.punto(pid, ts=ts, x=x, y=y, es_empleado=empleado and rnd.random() < 0.9)
                    ts += timedelta(seconds=rnd.choice([10, 10, 10, 20, 50, 61, 70, 300]))
    return datos


def _crudo(datos, fuentes, solo_clientes):
    """Lo que traian antes los endpoints: cada punto de las camaras fuente, en fraccion del cuadro."""
    filas = datos.filas(f"""
        SELECT sv.camara_id, t.persona_id, t.timestamp::date, EXTRACT(EPOCH FROM t.timestamp::time)::int,
               t.centroide_x, t.centroide_y, COALESCE(sv.frame_w, 1920), COALESCE(sv.frame_h, 1080)
        FROM trayectorias t JOIN personas p ON p.id = t.persona_id JOIN sesiones_video sv ON sv.id = p.sesion_id
        WHERE sv.camara_id = ANY(%s) {"AND NOT t.es_empleado" if solo_clientes else ""}
        ORDER BY t.persona_id, t.timestamp""", (sorted(set(fuentes.values())),))
    return [{"camara_id": c, "persona_id": p, "dia": d, "seg": s, "xn": x / w, "yn": y / h}
            for c, p, d, s, x, y, w, h in filas]


def _zonas(datos, fuentes):
    import json
    zonas = {}
    for cam, tipo, pol in datos.filas("SELECT camara_id, tipo, poligono FROM zonas WHERE camara_id = ANY(%s) ORDER BY id",
                                      (sorted(set(fuentes.values())),)):
        zonas.setdefault(cam, []).append({"tipo": tipo, "poligono": pol if not isinstance(pol, str) else json.loads(pol)})
    return zonas


def _a_json(valor):
    """Las claves y fechas como las deja jsonify, para comparar con la respuesta del endpoint."""
    import json

    from flask import json as fjson
    with app.app_context():
        return json.loads(fjson.dumps(valor))


@pytest.mark.parametrize("fuentes", [FUENTES_POR_DEFECTO, {"gondola": 4, "otro": 4, "caja": 3}])
def test_plano_tiempo_coincide_con_agrupar_los_puntos_en_python(recorridos, fuentes):
    query = ",".join(f"{t}:{c}" for t, c in fuentes.items())
    resp = app.test_client().get(f"/api/heatmap/plano/tiempo?refrescar=1&fuentes={query}").get_json()
    zonas = celdas_por_zona(_crudo(recorridos, fuentes, False), _zonas(recorridos, fuentes), dict(FUENTES_POR_DEFECTO, **fuentes))
    assert resp["zonas"] and resp == _a_json({"rango": rango_horario(zonas), "zonas": zonas})


@pytest.mark.parametrize("fuentes", [FUENTES_POR_DEFECTO, {"gondola": 4, "otro": 4, "caja": 3}])
def test_plano_flujo_coincide_con_partir_los_recorridos_en_python(recorridos, fuentes):
    query = ",".join(f"{t}:{c}" for t, c in fuentes.items())
    resp = app.test_client().get(f"/api/heatmap/plano/flujo?refrescar=1&fuentes={query}").get_json()
    esperado = tramos_por_zona(_crudo(recorridos, fuentes, True), _zonas(recorridos, fuentes), dict(FUENTES_POR_DEFECTO, **fuentes))
    assert resp["zonas"] and resp == _a_json({"zonas": esperado})

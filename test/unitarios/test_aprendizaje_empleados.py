"""Tests de frontend/api/aprendizaje_empleados.py: el modelo que aprende de las respuestas a las alertas "Persona
posiblemente empleada" (Es empleado / No es empleado) y como cambia esas alertas."""
from datetime import date, datetime
from unittest.mock import MagicMock

from api import aprendizaje_empleados as ae
from api.alertas import _alertas_posible_empleado


def _dia(cliente_id, caja, salon, gondola=0.0, horas=4.0, llegada=8, revisado=False, es_empleado=False, ropa=None, **kw):
    """Una persona en un dia: 'caja'/'salon'/'gondola' son la fraccion del tiempo a la vista en cada zona."""
    seg = horas * 3600
    fila = {
        "cliente_id": cliente_id, "fecha": date(2026, 10, 7), "minutos": round(seg / 60),
        "segundos": seg, "seg_caja": seg * caja, "seg_gondola": seg * gondola, "seg_otro": seg * salon,
        "primera_hora": datetime(2026, 10, 7, llegada, 0), "ultima_hora": datetime(2026, 10, 7, min(23, llegada + 5), 0),
        "camara_id": 1, "foto_url": None, "revisado": revisado, "es_empleado": es_empleado,
        "descripcion_visual": ropa,
    }
    fila.update(kw)
    return fila


ROPA_CLIENTE = '{"color_ropa_superior": "rojo", "color_ropa_inferior": "azul"}'


def _decisiones(n=6):
    """Lo que el usuario ya respondio: los empleados pasan casi todo el tiempo en la caja y visten de negro; los
    clientes que se quedaron mucho, en el salon."""
    # con algo de variacion entre personas, como en los datos reales
    empleados = [_dia(100 + i, caja=0.6 + 0.3 * (i % 3) / 2, salon=0.1, horas=4 + i % 3, llegada=7 + i % 3,
                      revisado=True, es_empleado=True,
                      ropa='{"color_ropa_superior": "negro", "color_ropa_inferior": "negro"}') for i in range(n)]
    clientes = [_dia(200 + i, caja=0.05 * (i % 2), salon=0.7 + 0.1 * (i % 3), horas=3 + (i % 2) / 2, llegada=15 + i % 4,
                     revisado=True, es_empleado=False,
                     ropa=ROPA_CLIENTE) for i in range(n)]
    return empleados + clientes


def test_caracteristicas_de_un_dia():
    c = ae.caracteristicas(_dia(1, caja=0.5, salon=0.25, gondola=0.25, horas=2, llegada=9,
                                ropa='{"color_ropa_superior": "Negro", "color_ropa_inferior": "no visible"}'))
    assert c["horas"] == 2 and c["jornada"] == 5 and c["llegada"] == 9
    assert (c["frac_caja"], c["frac_salon"], c["frac_gondola"], c["frac_sin_zona"]) == (0.5, 0.25, 0.25, 0)
    assert c["ropa"] == {"sup": "negro"}       # "no visible" no cuenta
    assert ae.caracteristicas(_dia(1, 0, 0, ropa="no es json"))["ropa"] == {}


def test_sin_ejemplos_de_las_dos_respuestas_no_estima_nada():
    solo_empleados = [r for r in _decisiones() if r["es_empleado"]]
    filas = solo_empleados + [_dia(1, caja=0.9, salon=0.1)]
    modelo = ae.puntuar(filas)
    assert not modelo.listo
    assert filas[-1]["prob_empleado"] is None and filas[-1]["motivos"] == []


def test_aprende_de_las_decisiones_y_explica_por_que():
    nuevo_empleado = _dia(1, caja=0.85, salon=0.05, ropa='{"color_ropa_superior": "negro"}')
    nuevo_cliente = _dia(2, caja=0.0, salon=0.95, llegada=18)
    filas = _decisiones() + [nuevo_empleado, nuevo_cliente]
    modelo = ae.puntuar(filas)
    assert modelo.listo and (modelo.n_empleados, modelo.n_clientes) == (6, 6)
    assert nuevo_empleado["prob_empleado"] > 0.8
    assert nuevo_cliente["prob_empleado"] < 0.2
    assert any("85% del tiempo en la caja" in m for m in nuevo_empleado["motivos"])
    assert any("salón" in m or "no pasó por la caja" in m for m in nuevo_cliente["motivos"])
    # las ya revisadas no se puntuan: ya tienen respuesta
    assert all(f["prob_empleado"] is None for f in filas if f["revisado"])


def test_cada_respuesta_nueva_cambia_lo_que_aprende():
    """Si el usuario empieza a confirmar como empleados a personas que pasan el dia en el salon, el modelo deja de
    tratar 'mucho salon' como señal de cliente."""
    def prob(decisiones):
        candidato = _dia(1, caja=0.0, salon=0.95, llegada=17)
        ae.puntuar(decisiones + [candidato])
        return candidato["prob_empleado"]

    repositores = [_dia(300 + i, caja=0.0, salon=0.95, llegada=17, revisado=True, es_empleado=True) for i in range(8)]
    assert prob(_decisiones() + repositores) > prob(_decisiones()) + 0.3


def test_descarta_solo_si_se_parece_claramente_a_un_cliente_y_hay_ejemplos_suficientes():
    cliente = _dia(2, caja=0.0, salon=0.95, llegada=18, ropa=ROPA_CLIENTE)
    modelo = ae.puntuar(_decisiones(n=15) + [cliente])
    assert cliente["prob_empleado"] < ae.PROB_DESCARTE_CLIENTE and ae.descartar_por_cliente(modelo, cliente)
    # con pocos ejemplos todavia pregunta
    cliente2 = _dia(2, caja=0.0, salon=0.95, llegada=18)
    modelo2 = ae.puntuar(_decisiones(n=3) + [cliente2])
    assert modelo2.listo and not ae.descartar_por_cliente(modelo2, cliente2)


# ── en las alertas ────────────────────────────────────────────────────────────────────────────────────────

def _alertas(filas):
    cur = MagicMock()
    cur.fetchall.return_value = filas
    return _alertas_posible_empleado(cur)


def test_las_alertas_de_posible_empleado_son_info_y_explican_lo_aprendido():
    alertas = _alertas(_decisiones() + [_dia(1, caja=0.85, salon=0.05)])
    nueva = next(a for a in alertas if a["persona_id"] == 1)
    assert nueva["sev"] == "info" and nueva["status"] == "open"
    assert nueva["prob_empleado"] > 0.8
    assert "Según las 12 personas que ya revisaste, se parece a los empleados que confirmaste" in nueva["desc"]


def test_un_candidato_parecido_a_los_clientes_confirmados_no_se_levanta_como_alerta():
    alertas = _alertas(_decisiones(n=15) + [_dia(2, caja=0.0, salon=0.95, llegada=18, ropa=ROPA_CLIENTE)])
    assert all(a["persona_id"] != 2 for a in alertas)
    assert len(alertas) == 30     # las ya revisadas siguen en la lista como resueltas


def test_las_revisadas_con_pocas_horas_ensenan_pero_no_aparecen_como_alerta():
    """El modelo aprende de todas las personas revisadas, aunque ese dia no hayan llegado al umbral de horas; pero
    la lista de alertas sigue mostrando solo los dias que lo superan."""
    cortas = [dict(f, segundos=3600, seg_caja=f["seg_caja"] / 4, seg_otro=f["seg_otro"] / 4, minutos=60)
              for f in _decisiones()]
    alertas = _alertas(cortas + [_dia(1, caja=0.85, salon=0.05)])
    assert [a["persona_id"] for a in alertas] == [1]
    assert alertas[0]["prob_empleado"] is not None

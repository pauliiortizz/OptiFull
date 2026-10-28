"""Tests de frontend/api/reportes_datos.py: los recolectores de cada metrica de Reportes 2.0.
La base de datos se simula con BDFalsa (conftest.py): cada test define las filas que devuelve cada consulta."""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from api import reportes_datos as rd
from api.reportes_datos import Filtros

LUNES = date(2026, 10, 5)
MARTES = date(2026, 10, 6)
CAJA = [[100, 100], [200, 100], [200, 200], [100, 200]]   # poligono de la zona de caja (px)


def cursor(bd):
    return bd.cursor()


# ── Filtros ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("desde, hasta, esperado", [
    (LUNES, MARTES, "05/10/2026 al 06/10/2026"),
    (LUNES, None, "desde el 05/10/2026"),
    (None, MARTES, "hasta el 06/10/2026"),
    (None, None, "todo el período con datos"),
])
def test_texto_periodo_segun_fechas_cargadas(desde, hasta, esperado):
    assert Filtros(desde=desde, hasta=hasta).texto_periodo() == esperado


def test_params_saca_las_camaras_excluidas_del_conteo():
    # Arrange: la camara 1 esta en CAMARAS_EXCLUIDAS_DE_CONTEO, la 2 no
    f = Filtros(camaras=[1, 2])
    # Act
    p = f.params()
    # Assert
    assert p["cams"] == [1, 2]
    assert p["cams_conteo"] == [2]
    assert p["excl"] == list(rd.CAMARAS_EXCLUIDAS_DE_CONTEO)


# ── Conteo y flujo ────────────────────────────────────────────────────────────

def test_flujo_sin_personas_deja_una_nota(bd):
    m = rd._flujo(cursor(bd), Filtros())
    assert m["resumen"] == []
    assert "Sin personas detectadas" in m["notas"][0]


def test_flujo_calcula_promedio_dia_pico_y_promedio_por_dia_de_semana(bd):
    bd.responder("COUNT(DISTINCT cliente_id) AS personas", [
        {"fecha": LUNES, "personas": 10},
        {"fecha": MARTES, "personas": 30},
        {"fecha": LUNES + timedelta(days=7), "personas": 20},
    ])
    m = rd._flujo(cursor(bd), Filtros())
    assert dict(m["resumen"]) == {"Promedio diario": 20, "Día de mayor afluencia": "06/10/2026 (30)"}
    assert m["tablas"][0]["filas"] == [["Lunes", 15], ["Martes", 30]]
    assert m["graficos"][0]["valores"] == [15, 30]
    assert any("no duplicar personas" in n for n in m["notas"])   # sin camaras elegidas avisa la exclusion


def test_flujo_con_camaras_elegidas_no_avisa_exclusion(bd):
    bd.responder("COUNT(DISTINCT cliente_id) AS personas", [{"fecha": LUNES, "personas": 4}])
    m = rd._flujo(cursor(bd), Filtros(camaras=[2]))
    assert m["notas"] == []


# ── Permanencia ───────────────────────────────────────────────────────────────

def test_permanencia_sin_datos_deja_una_nota(bd):
    m = rd._permanencia(cursor(bd), Filtros())
    assert "Sin personas detectadas" in m["notas"][0]


def test_permanencia_promedio_ponderado_por_clientes_y_por_zona(bd):
    bd.responder("WITH pc AS", [
        {"fecha": LUNES, "prom_min": Decimal("10"), "max_min": Decimal("30"), "clientes": 2, "total_min": Decimal("20")},
        {"fecha": MARTES, "prom_min": Decimal("4"), "max_min": Decimal("6"), "clientes": 3, "total_min": Decimal("12")},
    ]).responder("SELECT zona_tipo AS tipo, cliente_id AS cid", [
        # 'seg' = tiempo visto ya sumado en SQL (sql_tiempo_visto)
        {"tipo": "caja", "cid": 1, "seg": 120},      # 2 min
        {"tipo": "gondola", "cid": 1, "seg": 60},    # 1 min
        {"tipo": "gondola", "cid": 2, "seg": 180},   # 3 min
    ])
    m = rd._permanencia(cursor(bd), Filtros())
    # (20 + 12) min / 5 clientes = 6.4 min; el maximo es el mayor de todos los dias
    assert dict(m["resumen"]) == {"Permanencia promedio (min)": 6.4, "Permanencia máxima (min)": 30.0}
    zonas = {fila[0]: fila for fila in m["tablas"][1]["filas"]}
    assert zonas["Góndolas"] == ["Góndolas", 2.0, 3.0, 4.0, 67]   # promedio, maximo, total y % del tiempo
    assert zonas["Caja"][4] == 33


def test_permanencia_solo_con_datos_por_zona(bd):
    bd.responder("SELECT zona_tipo AS tipo, cliente_id AS cid", [{"tipo": "zona_nueva", "cid": 1, "seg": 60}])
    m = rd._permanencia(cursor(bd), Filtros())
    assert m["resumen"] == []
    assert m["tablas"][0]["filas"][0][0] == "zona_nueva"   # tipo sin nombre legible: se muestra tal cual


# ── Congestion ────────────────────────────────────────────────────────────────

def test_congestion_sin_datos_deja_una_nota(bd):
    m = rd._congestion(cursor(bd), Filtros())
    assert "Sin datos de ocupación" in m["notas"][0]


def test_congestion_reindexa_el_domingo_de_postgres_al_final_de_la_semana(bd):
    # Postgres: DOW 0 = domingo, 1 = lunes. La matriz va de Lun (0) a Dom (6).
    bd.responder("WITH ocupacion", [
        {"dow": 0, "hora": 18, "promedio": 9, "dias_con_datos": 2},
        {"dow": 1, "hora": 10, "promedio": 4, "dias_con_datos": 1},
    ])
    m = rd._congestion(cursor(bd), Filtros())
    grafico = m["graficos"][0]
    assert grafico["matriz"][6][18] == 9   # domingo
    assert grafico["matriz"][0][10] == 4   # lunes
    assert dict(m["resumen"]) == {"Pico más alto": "Dom 18-19hs · 9 personas", "Franjas críticas detectadas": 2}
    assert (6, 18, 18) in grafico["picos"]


# ── Espera en caja ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("x, y, esperado", [
    (150, 150, 0.0),     # dentro del poligono
    (250, 150, 50.0),    # a 50 px del borde derecho
    (100, 300, 100.0),   # debajo, a 100 px
])
def test_distancia_a_poligono(x, y, esperado):
    assert rd._dist_a_poligono(x, y, CAJA) == pytest.approx(esperado)


def test_distancia_a_poligono_con_lado_degenerado():
    assert rd._dist_a_poligono(3, 4, [[0, 0], [0, 0], [0, 0]]) == pytest.approx(5.0)


@pytest.mark.parametrize("seg, esperado", [(0, "0 s"), (59.4, "59 s"), (60, "1 min 00 s"), (125, "2 min 05 s")])
def test_formato_de_segundos_valores_limite(seg, esperado):
    assert rd._fmt_seg(seg) == esperado


def _puntos(persona, inicio, n, x=150, y=150, paso=10):
    return [{"persona_id": persona, "ts": inicio + timedelta(seconds=i * paso), "x": x, "y": y} for i in range(n)]


def _bd_espera(bd, puntos, frame_w=None):
    bd.responder("z.tipo = 'caja'", [{"camara_id": 2, "poligono": CAJA}])
    bd.responder("SELECT frame_w", [{"frame_w": frame_w}] if frame_w else [])
    bd.responder("t.centroide_x", puntos)
    return cursor(bd)


def test_espera_sin_zona_de_caja_deja_una_nota(bd):
    m = rd._espera_caja(cursor(bd), Filtros())
    assert "Sin esperas registradas" in m["notas"][0]


def test_espera_una_sola_muestra_cerca_no_cuenta(bd):
    # Valor limite: MIN_PUNTOS_ESPERA = 2 muestras seguidas; con 1 no es una espera
    m = rd._espera_caja(_bd_espera(bd, _puntos(1, datetime(2026, 10, 5, 10), 1)), Filtros())
    assert m["resumen"] == []


def test_espera_dos_muestras_seguidas_cuentan_como_una_espera(bd):
    m = rd._espera_caja(_bd_espera(bd, _puntos(1, datetime(2026, 10, 5, 10), 2), frame_w=1280), Filtros())
    resumen = dict(m["resumen"])
    assert resumen["Esperas registradas"] == 1
    assert resumen["Espera promedio"] == "20 s"   # 10 s entre muestras + 1 intervalo de muestreo


def test_espera_lejos_de_la_caja_no_cuenta(bd):
    lejos = _puntos(1, datetime(2026, 10, 5, 10), 5, x=900, y=900)
    m = rd._espera_caja(_bd_espera(bd, lejos), Filtros())
    assert m["resumen"] == []


def test_espera_un_hueco_largo_parte_la_espera_en_dos(bd):
    t0 = datetime(2026, 10, 5, 10)
    puntos = _puntos(1, t0, 2) + _puntos(1, t0 + timedelta(minutes=5), 2)   # hueco de 5 min > 3 intervalos
    m = rd._espera_caja(_bd_espera(bd, puntos), Filtros())
    assert dict(m["resumen"])["Esperas registradas"] == 2


def test_espera_franjas_con_pocas_esperas_se_omiten_y_la_distribucion_suma_100(bd):
    t0 = datetime(2026, 10, 5, 10)
    puntos = []
    for persona in range(1, 4):                       # 3 esperas a las 10 hs (llega a MIN_MUESTRA_FRANJA)
        puntos += _puntos(persona, t0 + timedelta(minutes=persona), 3)
    puntos += _puntos(9, datetime(2026, 10, 5, 15), 13)   # 1 espera de 130 s a las 15 hs: franja omitida
    m = rd._espera_caja(_bd_espera(bd, puntos), Filtros())
    franjas = m["tablas"][0]["filas"]
    assert [f[0] for f in franjas] == ["10-11hs"]
    distribucion = {f[0]: f[1] for f in m["tablas"][1]["filas"]}
    assert distribucion == {"Menos de 30 s": 0, "30 s a 1 min": 3, "1 a 2 min": 0, "2 a 5 min": 1, "Más de 5 min": 0}
    assert sum(f[2] for f in m["tablas"][1]["filas"]) == pytest.approx(100)
    assert dict(m["resumen"])["Esperas de más de 1 minuto"] == "25%"


# ── Zonas y recorridos ────────────────────────────────────────────────────────

def test_zonas_sin_trayectorias_deja_una_nota(bd):
    m = rd._zonas_y_recorridos(cursor(bd), Filtros())
    assert "Sin trayectorias" in m["notas"][0]


def test_zonas_y_recorridos_ordena_las_zonas_por_primera_visita(bd):
    bd.responder("SELECT zona_tipo AS tipo, cliente_id AS cid", [
        {"tipo": "otro", "cid": 1, "seg": 60},
        {"tipo": "gondola", "cid": 1, "seg": 180},
        {"tipo": "gondola", "cid": 2, "seg": 60},
    ]).responder("SELECT persona_id, zona_tipo AS tipo, segundos", [
        {"persona_id": 1, "tipo": "otro", "segundos": 10}, {"persona_id": 1, "tipo": "gondola", "segundos": 40},
        {"persona_id": 1, "tipo": "otro", "segundos": 10}, {"persona_id": 2, "tipo": "gondola", "segundos": 10},
    ])
    m = rd._zonas_y_recorridos(cursor(bd), Filtros())
    rutas = {r[0]: r[1] for r in m["tablas"][1]["filas"]}
    assert rutas == {"Salón → Góndolas": 1, "Góndolas": 1}   # zonas repetidas cuentan una vez, en orden
    tiempos = {r[0]: r[3] for r in m["tablas"][1]["filas"]}
    assert tiempos == {"Salón → Góndolas": 1.0, "Góndolas": 0.2}   # suma del tiempo visto de sus puntos
    resumen = dict(m["resumen"])
    assert resumen["Zona más transitada"] == "Góndolas · 100.0% de las personas"
    assert resumen["Donde más se demoran"] == "Góndolas · 2.0 min por persona"


# ── Stock ─────────────────────────────────────────────────────────────────────

def test_stock_deteccion_sin_datos_deja_una_nota(bd):
    m = rd._stock_deteccion(cursor(bd), Filtros())
    assert "Sin detecciones de productos" in m["notas"][0]


def test_stock_deteccion_resume_transacciones_y_gondolas(bd):
    bd.responder("estado_matching", [
        {"estado": "reconocido", "n": 3, "confianza": Decimal("0.9")},
        {"estado": "ambiguo", "n": 1, "confianza": Decimal("0.5")},
    ]).responder("JOIN productos pr", [
        {"sku": "SKU1", "nombre": "Coca", "categoria": "gaseosa", "detecciones": 4, "unidades": Decimal("6"),
         "confianza": Decimal("0.8")},
    ]).responder("z.tipo = 'gondola'", [
        {"camara": "Cam 2", "zona": "Góndola A", "personas": 3, "puntos": 30},
        {"camara": "Cam 2", "zona": "Góndola B", "personas": 1, "puntos": 10},
    ])
    m = rd._stock_deteccion(cursor(bd), Filtros())
    resumen = dict(m["resumen"])
    assert resumen["Productos detectados (transacciones)"] == 4
    assert resumen["Unidades detectadas"] == 6
    assert resumen["Reconocidos sin ambigüedad"] == "75%"
    assert resumen["Confianza promedio del modelo"] == 0.8   # (0.9*3 + 0.5*1) / 4
    assert resumen["Góndola más concurrida"] == "Góndola A (Cam 2)"
    assert m["tablas"][2]["filas"][0][4] == 75   # % del total de presencia


def test_stock_deteccion_solo_gondolas(bd):
    bd.responder("z.tipo = 'gondola'", [{"camara": "Cam 2", "zona": "G", "personas": 1, "puntos": 6}])
    m = rd._stock_deteccion(cursor(bd), Filtros())
    assert [g["id"] for g in m["graficos"]] == ["stock_ocupacion"]


def test_stock_faltantes_sin_catalogo_deja_una_nota(bd):
    m = rd._stock_faltantes(cursor(bd), Filtros())
    assert "No hay productos cargados" in m["notas"][0]


def test_stock_faltantes_valores_limite_del_umbral_de_stock_bajo(bd):
    # UMBRAL_STOCK_BAJO = 5: 0 -> Agotado, 5 -> Stock bajo, 6 -> no figura
    bd.responder("FROM productos ORDER BY nombre", [
        {"sku": "A", "nombre": "Agua", "categoria": "-", "cantidad": 0},
        {"sku": "B", "nombre": "Birra", "categoria": "-", "cantidad": 5},
        {"sku": "C", "nombre": "Coca", "categoria": "-", "cantidad": 6},
    ]).responder("GROUP BY sku", [
        {"sku": "C", "unidades": Decimal("4"), "primera": LUNES, "ultima": MARTES},
    ])
    m = rd._stock_faltantes(cursor(bd), Filtros())
    faltantes = {f[0]: f[4] for f in m["tablas"][0]["filas"]}
    assert faltantes == {"A": "Agotado", "B": "Stock bajo"}
    rotacion = {f[0]: f for f in m["tablas"][1]["filas"]}
    assert rotacion["C"][5] == 40.0    # 4 vendidas / (4 + 6)
    assert rotacion["C"][6] == 3.0     # 6 de stock / (4 vendidas / 2 dias)
    assert rotacion["A"][6] is None    # sin ventas no hay cobertura
    assert dict(m["resumen"])["Mayor rotación"] == "Coca (40.0%)"
    assert any("2 días considerados" in n for n in m["notas"])


@pytest.mark.parametrize("filtros, ventas, dias", [
    (Filtros(desde=LUNES, hasta=LUNES), [], "1 día considerados"),        # mismo dia: 1 (singular)
    (Filtros(desde=LUNES, hasta=MARTES + timedelta(days=8)), [], "10 días"),
    (Filtros(), [], "1 día considerados"),                                  # sin fechas ni ventas
])
def test_stock_faltantes_dias_del_periodo(bd, filtros, ventas, dias):
    bd.responder("FROM productos ORDER BY nombre", [{"sku": "A", "nombre": "Agua", "categoria": "-", "cantidad": 50}])
    m = rd._stock_faltantes(cursor(bd), filtros)
    assert any(dias in n for n in m["notas"])
    assert m["graficos"] == []          # sin ventas ni faltantes no hay graficos
    assert "Mayor rotación" not in dict(m["resumen"])


# ── Catalogo y recoleccion ────────────────────────────────────────────────────

def test_catalogo_lista_todas_las_metricas_sin_la_funcion():
    cat = rd.catalogo()
    assert [c["id"] for c in cat] == list(rd.METRICAS)
    assert all("fn" not in c for c in cat)


def test_recolectar_respeta_el_orden_del_catalogo_y_solo_lo_pedido(bd):
    resultados = rd.recolectar(bd, {"stock_faltantes", "personas_flujo"}, Filtros())
    assert [r["id"] for r in resultados] == ["personas_flujo", "stock_faltantes"]


def test_recolectar_una_metrica_que_falla_no_tumba_el_reporte(bd):
    bd.error = RuntimeError("relation transacciones does not exist")
    resultados = rd.recolectar(bd, {"stock_deteccion"}, Filtros())
    assert bd.rollbacks == 1
    assert resultados[0]["categoria"] == "Stock y Productos"
    assert "No se pudo obtener esta métrica" in resultados[0]["notas"][0]

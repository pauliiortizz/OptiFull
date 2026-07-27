"""Tests unitarios de calcular_stats() (frontend/api/stats.py) -- funcion pura,
sin BD ni red, que arma el resumen de KPIs que consume el frontend."""
from api import calcular_stats


def _row(id_, cliente_id, duracion_min, entrada="10:00:00", salida="10:05:00"):
    return {
        "id": id_,
        "cliente_id": cliente_id,
        "entrada": entrada,
        "salida": salida,
        "duracion_seg": duracion_min * 60,
        "duracion_min": duracion_min,
    }


def test_personas_totales_cuenta_filas_crudas():
    rows = [_row(1, 1, 5), _row(2, 1, 10), _row(3, 2, 3)]
    stats = calcular_stats(rows)
    assert stats["personas_totales"] == 3


def test_personas_unicas_dedupe_por_cliente_id():
    # Mismo cliente_id=1 aparece en dos filas (dos sesiones/videos distintos);
    # tiene que contar como 1 sola persona unica, no 2.
    rows = [_row(1, 1, 5), _row(2, 1, 10), _row(3, 2, 3)]
    stats = calcular_stats(rows)
    assert stats["personas_unicas"] == 2


def test_sin_permanencias_usa_rows_como_fallback():
    # Sin BD (modo CSV) no hay tabla 'visitas': calcular_stats debe recalcular
    # las metricas de tiempo sobre 'rows' tal cual, sin romper.
    rows = [_row(1, 1, 5), _row(2, 2, 15)]
    stats = calcular_stats(rows)
    assert stats["permanencia_promedio_min"] == 10.0
    assert stats["permanencia_maxima_min"] == 15


def test_permanencias_reemplaza_a_rows_para_metricas_de_tiempo():
    # Este es el bug que arreglamos: la permanencia real (sumada via
    # 'visitas', agrupada por cliente) puede ser MUY distinta de las filas
    # crudas por sesion. calcular_stats tiene que usar 'permanencias' para
    # las metricas de tiempo, e ignorar la duracion de las filas crudas.
    rows = [_row(1, 1, 20), _row(2, 1, 60)]  # cliente 1: 20min + 60min (2 videos)
    permanencias = [_row(10, 1, 80)]         # ya sumado: 80 min reales

    stats = calcular_stats(rows, permanencias)

    assert stats["personas_totales"] == 2       # 2 filas crudas
    assert stats["personas_unicas"]  == 1        # 1 cliente real
    assert stats["permanencia_promedio_min"] == 80.0
    assert stats["permanencia_maxima_min"]   == 80.0


def test_personas_validas_filtra_ruido_menor_a_30_seg():
    rows = [_row(1, 1, 0.2), _row(2, 2, 5)]  # 0.2 min = 12seg -> ruido
    stats = calcular_stats(rows)
    assert stats["personas_validas"] == 1


def test_lista_vacia_no_rompe():
    stats = calcular_stats([])
    assert stats["personas_totales"] == 0
    assert stats["personas_unicas"] == 0
    assert stats["permanencia_promedio_min"] == 0
    assert stats["permanencia_maxima_min"] == 0
    assert stats["permanencia_minima_valida_min"] == 0
    assert sum(d["count"] for d in stats["distribucion"]) == 0


def test_distribucion_bucketiza_por_rango_de_duracion():
    rows = [
        _row(1, 1, 0.5),   # 30 seg  -> "< 1 min"
        _row(2, 2, 2),     # 2 min   -> "1-5 min"
        _row(3, 3, 10),    # 10 min  -> "5-15 min"
        _row(4, 4, 30),    # 30 min  -> "15-60 min"
        _row(5, 5, 90),    # 90 min  -> "> 1 hora"
    ]
    stats = calcular_stats(rows)
    conteo = {d["rango"]: d["count"] for d in stats["distribucion"]}
    assert conteo["< 1 min"]   == 1
    assert conteo["1-5 min"]   == 1
    assert conteo["5-15 min"]  == 1
    assert conteo["15-60 min"] == 1
    assert conteo["> 1 hora"]  == 1


def test_distribucion_suma_personas_unicas_cuando_hay_permanencias():
    # La distribucion tiene que reflejar clientes reales (permanencias), no
    # filas crudas -- si no, un cliente detectado en 3 videos aparece 3 veces
    # en la distribucion en vez de 1.
    rows = [_row(1, 1, 5), _row(2, 1, 5), _row(3, 1, 5)]
    permanencias = [_row(10, 1, 15)]  # 1 cliente real, 15 min sumados

    stats = calcular_stats(rows, permanencias)
    total_distribucion = sum(d["count"] for d in stats["distribucion"])
    assert total_distribucion == 1

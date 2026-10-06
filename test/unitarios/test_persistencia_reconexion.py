"""Tests unitarios de la reconexion automatica de Persistencia (modo RTSP en vivo): si la BD se cae
(corte de internet) el analisis tiene que reconectar solo y NO perder datos. Sin BD real: conectar()
se mockea."""
from unittest.mock import MagicMock, patch

import psycopg2

from deteccion.persistencia import Persistencia


def _p(reconectar: bool) -> Persistencia:
    p = Persistencia("postgresql://x", True, True, {1: ("Cam", "Zona")})
    p.reconectar_automaticamente = reconectar
    return p


def test_sin_reconexion_automatica_no_reconecta_nunca():
    """Modos sin persistencia (webcam, pantalla, SOLO_LEER_ZONAS): 'sin conexion' es a proposito."""
    p = _p(False)
    with patch.object(p, "conectar") as conectar:
        assert p.asegurar_conexion() is False
        assert p.asegurar_conexion(forzar=True) is False
        conectar.assert_not_called()


def test_con_conexion_viva_no_hace_nada():
    p = _p(True)
    p.conn = MagicMock()
    with patch.object(p, "conectar") as conectar:
        assert p.asegurar_conexion() is True
        conectar.assert_not_called()


def test_reconecta_pero_no_mas_de_una_vez_cada_intervalo():
    p = _p(True)
    intentos = []

    def conectar_falla():
        p._ultimo_intento_conexion = __import__("time").monotonic()
        intentos.append(1)
        return False
    with patch.object(p, "conectar", side_effect=conectar_falla):
        p.asegurar_conexion()
        p.asegurar_conexion()
        p.asegurar_conexion()
        assert len(intentos) == 1, "durante el corte no debe reintentar en cada frame (frenaria el analisis)"
        p.asegurar_conexion(forzar=True)          # el cierre fuerza el reintento
        assert len(intentos) == 2


def test_operacion_se_ejecuta_apenas_vuelve_la_conexion():
    p = _p(True)
    nueva = MagicMock()

    def conectar_ok():
        p.conn = nueva
        return True
    with patch.object(p, "conectar", side_effect=conectar_ok):
        assert p._con_reconexion(lambda: "guardado" if p.conn else "sin conexion", default="x") == "guardado"


def test_sin_reconexion_automatica_una_operacion_sin_conexion_devuelve_el_default():
    p = _p(False)
    with patch.object(p, "conectar") as conectar:
        assert p._con_reconexion(lambda: "no deberia pasar" if p.conn else "sin conexion", default="x") == "sin conexion"
        conectar.assert_not_called()


def test_trayectorias_devuelven_menos_uno_si_no_se_pudieron_guardar():
    """El llamador usa esto para NO vaciar el buffer cuando la BD estaba caida."""
    p = _p(False)
    traj = [{"sid": 1, "frame": 1, "cx": 1.0, "cy": 1.0, "box": [0, 0, 1, 1], "zona_id": None}]
    import datetime
    assert p.guardar_trayectorias_parcial(traj, 2.0, datetime.datetime(2026, 1, 1), 1) == -1
    assert p.guardar_trayectorias_parcial([], 2.0, datetime.datetime(2026, 1, 1), 1) == 0   # nada que guardar != fallo


def test_error_de_psycopg2_reintenta_tras_reconectar():
    p = _p(True)
    p.conn = MagicMock()
    llamadas = {"n": 0}

    def operacion():
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise psycopg2.OperationalError("server closed the connection unexpectedly")
        return "ok"

    def conectar_ok():
        p.conn = MagicMock()
        return True
    with patch.object(p, "conectar", side_effect=conectar_ok):
        assert p._con_reconexion(operacion, default="x") == "ok"
    assert llamadas["n"] == 2

"""CashierInterfaceAgent (deteccion_productos): la cajera por consola. Se simula lo que tipea con input()."""
import pytest

from agents.cashier_interface_agent import CashierInterfaceAgent

COCA = {"sku": "SKU001", "nombre": "Coca-Cola 500ml"}
ZERO = {"sku": "SKU002", "nombre": "Coca-Cola Zero 500ml"}


@pytest.fixture
def teclea(monkeypatch):
    def preparar(*lineas):
        pendientes = list(lineas)
        monkeypatch.setattr("builtins.input", lambda _="": pendientes.pop(0))
        return pendientes
    return preparar


cajera = CashierInterfaceAgent()


# ── confirmar_producto ───────────────────────────────────────────────────────

@pytest.mark.parametrize("tecleado, esperado", [
    ("", (COCA, 1)),          # Enter = 1 unidad
    ("3", (COCA, 3)),
    (" 2 ", (COCA, 2)),
    ("0", (None, 0)),         # cancelar
    ("-1", (None, 0)),
    ("tres", (None, 0)),
])
def test_confirmar_producto(teclea, tecleado, esperado):
    teclea(tecleado)
    assert cajera.confirmar_producto(COCA, 0.9) == esperado


def test_confirmar_muestra_producto_y_confianza(teclea, capsys):
    teclea("")
    cajera.confirmar_producto(COCA, 0.87)
    salida = capsys.readouterr().out
    assert "Coca-Cola 500ml" in salida and "SKU001" in salida and "87%" in salida


def test_confirmar_y_corregir_pasa_a_carga_manual(teclea):
    teclea("C", "SKU009", "2")
    assert cajera.confirmar_producto(COCA, 0.9) == ({"sku": "SKU009", "nombre": "(cargado manualmente: SKU009)"}, 2)


# ── elegir_entre_candidatos ──────────────────────────────────────────────────

@pytest.mark.parametrize("tecleado, esperado", [
    (("2", ""), (ZERO, 1)),
    (("1", "4"), (COCA, 4)),
    (("1", "0"), (None, 0)),
    (("1", "-2"), (None, 0)),
    (("1", "x"), (None, 0)),
    (("0",), (None, 0)),
    (("3",), (None, 0)),       # fuera de rango
    (("abc",), (None, 0)),
])
def test_elegir_entre_candidatos(teclea, tecleado, esperado):
    teclea(*tecleado)
    assert cajera.elegir_entre_candidatos([COCA, ZERO]) == esperado


def test_elegir_muestra_lo_que_vio_el_sistema(teclea, capsys):
    teclea("1", "")
    cajera.elegir_entre_candidatos([COCA, ZERO], datos_llm={"marca": "Coca", "variante": "Zero",
                                                           "tamano": {"valor": 500, "unidad": "ml"}})
    salida = capsys.readouterr().out
    assert "marca=Coca" in salida and "1) Coca-Cola 500ml" in salida and "2) Coca-Cola Zero 500ml" in salida


def test_elegir_y_cargar_manual(teclea):
    teclea("m", "SKU005", "")
    assert cajera.elegir_entre_candidatos([COCA, ZERO])[0]["sku"] == "SKU005"


# ── producto_manual ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("tecleado, esperado", [
    (("SKU010", ""), ("SKU010", 1)),
    ((" SKU010 ", "5"), ("SKU010", 5)),
    (("",), (None, 0)),                 # Enter en el SKU = cancelar
    (("SKU010", "0"), (None, 0)),
    (("SKU010", "dos"), (None, 0)),
    (("SKU010", "-3"), (None, 0)),
])
def test_producto_manual(teclea, tecleado, esperado):
    teclea(*tecleado)
    producto, cantidad = cajera.producto_manual()
    assert ((producto or {}).get("sku"), cantidad) == esperado


def test_modo_por_defecto_es_consola():
    assert CashierInterfaceAgent().modo == "consola"

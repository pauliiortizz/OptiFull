"""Caja de productos (deteccion_productos) contra un Postgres real con el schema de OptiFull.

  - StockAgent: catalogo, descuento atomico de stock y registro en 'transacciones'.
  - setup_db.py: carga del catalogo desde el CSV (UPSERT).
  - DbCashierInterfaceAgent: la cajera web. Un hilo hace de navegador: espera la decision pendiente en
    caja_estado y escribe la respuesta igual que frontend/api/productos.py.
  - CheckoutOrchestrator (main.py) de punta a punta: camara y LLM falsos, con movimiento, matching y stock reales.
"""
import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest

import psycopg2
from conftest import URL

PRODUCTOS_DIR = Path(__file__).resolve().parents[2] / "deteccion_productos"

COCA = ("SKU001", "Coca-Cola 500ml", "Coca-Cola", "Original", 500, "ml", "gaseosa", 50, 1200)
ZERO = ("SKU002", "Coca-Cola Zero 500ml", "Coca-Cola", "Zero", 500, "ml", "gaseosa", 40, 1200)
MILKA = ("SKU018", "Chocolate Milka Leche 100g", "Milka", "Leche", 100, "g", "chocolate", 3, 3200)
LAYS = ("SKU016", "Papas Lays Clasicas 100g", "Lays", "Clasicas", 100, "g", "snack", 50, 1500)
LAYS_GRANDE = ("SKU099", "Papas Lays Clasicas 105g", "Lays", "Clasicas", 105, "g", "snack", 20, 1700)


def llm(marca, variante, valor, unidad, confianza=0.9):
    return {"producto_detectado": True, "marca": marca, "nombre_producto": marca, "variante": variante,
            "tamano": {"valor": valor, "unidad": unidad}, "categoria": "x", "confianza": confianza}


@pytest.fixture
def caja(conn, monkeypatch):
    """Base con productos y caja_estado limpios; DATABASE_URL apuntando a la base de prueba."""
    cur = conn.cursor()
    cur.execute("TRUNCATE productos, transacciones CASCADE")
    cur.execute("INSERT INTO caja_estado (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    cur.execute("UPDATE caja_estado SET estado = 'inactivo', pendiente = NULL, respuesta = NULL")
    cur.executemany("INSERT INTO productos (sku, nombre, marca, variante, tamano_valor, tamano_unidad, categoria, "
                    "cantidad, precio) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", [COCA, ZERO, MILKA, LAYS, LAYS_GRANDE])
    conn.commit()
    monkeypatch.setenv("DATABASE_URL", URL)
    return conn


def consultar(conn, sql, params=()):
    conn.rollback()                       # ver lo que commitearon otras conexiones
    cur = conn.cursor()
    cur.execute(sql, params)
    filas = cur.fetchall()
    conn.commit()
    return filas


def stock(conn, sku):
    return consultar(conn, "SELECT cantidad FROM productos WHERE sku = %s", (sku,))[0][0]


# ── StockAgent ───────────────────────────────────────────────────────────────

@pytest.fixture
def stock_agent(caja):
    from agents.stock_agent import StockAgent
    s = StockAgent()
    yield s
    s.close()


def test_cargar_productos_desde_la_base(stock_agent):
    productos = {p["sku"]: p for p in stock_agent.cargar_productos()}
    assert set(productos) == {"SKU001", "SKU002", "SKU018", "SKU016", "SKU099"}
    assert productos["SKU002"] == {"sku": "SKU002", "nombre": "Coca-Cola Zero 500ml", "marca": "Coca-Cola",
                                   "variante": "Zero", "tamano_valor": 500.0, "tamano_unidad": "ml",
                                   "categoria": "gaseosa", "cantidad": 40}


def test_obtener_stock(stock_agent):
    assert stock_agent.obtener_stock("SKU001") == 50
    assert stock_agent.obtener_stock("NO-EXISTE") is None


def test_descontar_baja_el_stock_y_registra_la_transaccion(stock_agent, caja):
    datos = llm("Coca-Cola", "Original", 500, "ml", confianza=0.93)
    assert stock_agent.descontar("SKU001", 3, 0.93, "reconocido", datos, confirmado_por_cajera=True) == 47
    assert stock(caja, "SKU001") == 47
    (fila,) = consultar(caja, "SELECT sku, cantidad, confianza_llm, estado_matching, confirmado_por_cajera, "
                              "datos_llm_json FROM transacciones")
    assert fila == ("SKU001", 3, 0.93, "reconocido", True, datos)


def test_descontar_nunca_deja_stock_negativo(stock_agent, caja):
    assert stock_agent.descontar("SKU018", 10, 0.9, "confirmar", {}) == 0
    assert stock(caja, "SKU018") == 0
    assert consultar(caja, "SELECT cantidad, confirmado_por_cajera FROM transacciones") == [(10, False)]


def test_descontar_sku_inexistente_no_deja_nada_a_medias(stock_agent, caja):
    with pytest.raises(ValueError, match="NO-EXISTE"):
        stock_agent.descontar("NO-EXISTE", 1, 0.9, "reconocido", {})
    assert consultar(caja, "SELECT COUNT(*) FROM transacciones") == [(0,)]
    # la conexion sigue usable despues del rollback
    assert stock_agent.descontar("SKU001", 1, 0.9, "reconocido", {}) == 49


def test_descuentos_simultaneos_no_se_pisan(caja):
    from agents.stock_agent import StockAgent
    cajas = [StockAgent() for _ in range(5)]
    hilos = [threading.Thread(target=lambda s=s: [s.descontar("SKU001", 1, 0.9, "reconocido", {}) for _ in range(4)])
             for s in cajas]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    for s in cajas:
        s.close()
    assert stock(caja, "SKU001") == 50 - 20
    assert consultar(caja, "SELECT COUNT(*) FROM transacciones") == [(20,)]


def test_datos_del_llm_con_acentos_se_guardan_tal_cual(stock_agent, caja):
    stock_agent.descontar("SKU016", 1, 0.9, "reconocido", {"variante": "Clásicas"})
    assert consultar(caja, "SELECT datos_llm_json->>'variante' FROM transacciones") == [("Clásicas",)]


def test_sin_base_carga_el_catalogo_del_csv_y_no_deja_descontar(monkeypatch, capsys):
    from agents import stock_agent as sa
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(PRODUCTOS_DIR)
    s = sa.StockAgent()
    productos = s.cargar_productos()
    assert len(productos) >= 50 and productos[0]["sku"] == "SKU001"
    assert isinstance(productos[0]["tamano_valor"], float) and isinstance(productos[0]["cantidad"], int)
    assert "NO es el real" in capsys.readouterr().out
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        s.obtener_stock("SKU001")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        s.descontar("SKU001", 1, 0.9, "reconocido", {})
    s.close()


# ── setup_db.py ──────────────────────────────────────────────────────────────

def test_setup_db_carga_el_catalogo_y_se_puede_correr_de_nuevo(caja, monkeypatch, capsys):
    import setup_db
    monkeypatch.chdir(PRODUCTOS_DIR)
    cur = caja.cursor()
    cur.execute("UPDATE productos SET nombre = 'viejo', cantidad = 1 WHERE sku = 'SKU001'")
    caja.commit()
    setup_db.main()
    setup_db.main()   # UPSERT: correrlo dos veces no duplica ni falla
    total_csv = sum(1 for _ in open(PRODUCTOS_DIR / "data" / "productos.csv", encoding="utf-8")) - 1
    assert f"{total_csv} productos cargados" in capsys.readouterr().out
    assert consultar(caja, "SELECT COUNT(*) FROM productos WHERE sku LIKE 'SKU0%%' AND sku <> 'SKU099'") \
        == [(total_csv,)]
    assert consultar(caja, "SELECT nombre, cantidad FROM productos WHERE sku = 'SKU001'") == [("Coca-Cola 500ml", 50)]


def test_setup_db_sin_database_url(monkeypatch):
    import setup_db
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        setup_db.main()


# ── DbCashierInterfaceAgent (cajera web) ─────────────────────────────────────

class Navegador:
    """Hace de cajera en el navegador: por cada decision pendiente que aparece en caja_estado, anota lo que
    se le pidio y escribe la siguiente respuesta (como POST /productos/decision). 'detener' pide apagar la caja."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.pendientes = []
        self.conn = psycopg2.connect(URL)
        self.conn.autocommit = True
        self._fin = threading.Event()
        self.hilo = threading.Thread(target=self._atender, daemon=True)

    def __enter__(self):
        self.hilo.start()
        return self

    def __exit__(self, *exc):
        self._fin.set()
        self.hilo.join(timeout=5)
        self.conn.close()

    def _atender(self):
        cur = self.conn.cursor()
        while not self._fin.is_set() and self.respuestas:
            cur.execute("SELECT estado, pendiente, respuesta FROM caja_estado WHERE id = 1")
            estado, pendiente, respuesta = cur.fetchone()
            if estado == "esperando_decision" and respuesta is None:
                self.pendientes.append(pendiente)
                r = self.respuestas.pop(0)
                if r == "detener":
                    cur.execute("UPDATE caja_estado SET estado = 'detener' WHERE id = 1")
                else:
                    cur.execute("UPDATE caja_estado SET respuesta = %s WHERE id = 1", (json.dumps(r),))
                    # esperar a que el detector tome la respuesta antes de mirar la proxima
                    while not self._fin.is_set():
                        cur.execute("SELECT respuesta FROM caja_estado WHERE id = 1")
                        if cur.fetchone()[0] is None:
                            break
                        time.sleep(0.005)
            time.sleep(0.005)


@pytest.fixture
def cajera_web(caja, monkeypatch):
    from agents import db_cashier_agent as dca
    monkeypatch.setattr(dca, "POLL_INTERVAL_SEG", 0.01)
    c = dca.DbCashierInterfaceAgent()
    yield c
    c.close()


P_COCA = {"sku": "SKU001", "nombre": "Coca-Cola 500ml"}
P_ZERO = {"sku": "SKU002", "nombre": "Coca-Cola Zero 500ml"}


def test_cajera_web_sin_database_url(monkeypatch):
    from agents.db_cashier_agent import DbCashierInterfaceAgent
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        DbCashierInterfaceAgent()


def test_al_arrancar_limpia_un_estado_viejo(caja):
    from agents.db_cashier_agent import DbCashierInterfaceAgent
    cur = caja.cursor()
    cur.execute("UPDATE caja_estado SET estado = 'detener', pendiente = '{\"tipo\": \"manual\"}', "
                "respuesta = '{\"accion\": \"cancelar\"}'")
    caja.commit()
    c = DbCashierInterfaceAgent()
    assert consultar(caja, "SELECT estado, pendiente, respuesta FROM caja_estado") == [("inactivo", None, None)]
    assert c.debe_detenerse() is False
    c.close()


@pytest.mark.parametrize("respuesta, esperado", [
    ({"accion": "confirmar", "cantidad": 2}, (P_COCA, 2)),
    ({"accion": "confirmar", "cantidad": "3"}, (P_COCA, 3)),
    ({"accion": "confirmar"}, (P_COCA, 0)),
    ({"accion": "cancelar"}, (None, 0)),
])
def test_confirmar_producto_desde_la_web(cajera_web, respuesta, esperado):
    cajera_web.meta_deteccion = {"confianza_llm": 0.91, "estado_matching": "reconocido", "datos_llm": {"m": 1}}
    with Navegador([respuesta]) as web:
        assert cajera_web.confirmar_producto(P_COCA, 0.91) == esperado
    assert web.pendientes == [{"tipo": "confirmar", "producto": P_COCA, "confianza": 0.91,
                               "meta": cajera_web.meta_deteccion}]


def test_despues_de_cada_decision_la_caja_queda_inactiva(cajera_web, caja):
    with Navegador([{"accion": "confirmar", "cantidad": 1}]):
        cajera_web.confirmar_producto(P_COCA, 0.9)
    assert consultar(caja, "SELECT estado, pendiente, respuesta FROM caja_estado") == [("inactivo", None, None)]


def test_confirmar_y_pasar_a_carga_manual(cajera_web):
    with Navegador([{"accion": "manual"}, {"accion": "cargar", "sku": "SKU018", "cantidad": 4}]) as web:
        producto, cantidad = cajera_web.confirmar_producto(P_COCA, 0.9)
    assert (producto["sku"], cantidad) == ("SKU018", 4)
    assert [p["tipo"] for p in web.pendientes] == ["confirmar", "manual"]
    assert "meta" not in web.pendientes[0]          # sin deteccion en curso no se manda meta


@pytest.mark.parametrize("respuesta, esperado", [
    ({"accion": "elegir", "indice": 1, "cantidad": 2}, ("SKU002", 2)),
    ({"accion": "elegir", "indice": 0, "cantidad": 1}, ("SKU001", 1)),
    ({"accion": "elegir", "indice": 2, "cantidad": 1}, (None, 0)),     # fuera de rango
    ({"accion": "elegir", "indice": -1, "cantidad": 1}, (None, 0)),
    ({"accion": "elegir", "cantidad": 1}, (None, 0)),                  # sin indice
    ({"accion": "cancelar"}, (None, 0)),
])
def test_elegir_entre_candidatos_desde_la_web(cajera_web, respuesta, esperado):
    datos = llm("Coca-Cola", None, 500, "ml")
    with Navegador([respuesta]) as web:
        producto, cantidad = cajera_web.elegir_entre_candidatos([P_COCA, P_ZERO], datos_llm=datos)
    assert ((producto or {}).get("sku"), cantidad) == esperado
    assert web.pendientes[0] == {"tipo": "elegir", "candidatos": [P_COCA, P_ZERO], "datos_llm": datos}


def test_elegir_y_pasar_a_carga_manual(cajera_web):
    with Navegador([{"accion": "manual"}, {"accion": "cancelar"}]):
        assert cajera_web.elegir_entre_candidatos([P_COCA, P_ZERO]) == (None, 0)


@pytest.mark.parametrize("respuesta, esperado", [
    ({"accion": "cargar", "sku": "SKU016", "cantidad": 2}, ("SKU016", 2)),
    ({"accion": "cargar", "sku": "SKU016", "cantidad": 0}, (None, 0)),
    ({"accion": "cargar", "sku": "", "cantidad": 1}, (None, 0)),
    ({"accion": "cargar", "cantidad": 1}, (None, 0)),
    ({"accion": "cancelar"}, (None, 0)),
])
def test_carga_manual_desde_la_web(cajera_web, respuesta, esperado):
    with Navegador([respuesta]):
        producto, cantidad = cajera_web.producto_manual()
    assert ((producto or {}).get("sku"), cantidad) == esperado


def test_detener_mientras_se_espera_una_decision(cajera_web):
    from agents.db_cashier_agent import DetenerCaja
    with Navegador(["detener"]):
        with pytest.raises(DetenerCaja):
            cajera_web.confirmar_producto(P_COCA, 0.9)


def test_debe_detenerse_consulta_la_base_como_mucho_una_vez_por_segundo(cajera_web, caja, monkeypatch):
    from agents import db_cashier_agent as dca
    reloj = [100.0]
    monkeypatch.setattr(dca.time, "monotonic", lambda: reloj[0])
    assert cajera_web.debe_detenerse() is False
    cur = caja.cursor()
    cur.execute("UPDATE caja_estado SET estado = 'detener'")
    caja.commit()
    reloj[0] += dca.CHEQUEO_DETENER_SEG / 2
    assert cajera_web.debe_detenerse() is False        # todavia no toca consultar
    reloj[0] += dca.CHEQUEO_DETENER_SEG
    assert cajera_web.debe_detenerse() is True


def test_debe_detenerse_sin_fila_de_estado(cajera_web, caja):
    cur = caja.cursor()
    cur.execute("DELETE FROM caja_estado")
    caja.commit()
    assert cajera_web.debe_detenerse() is False


def test_marcar_inactivo(cajera_web, caja):
    cur = caja.cursor()
    cur.execute("UPDATE caja_estado SET estado = 'detener'")
    caja.commit()
    cajera_web.marcar_inactivo()
    assert consultar(caja, "SELECT estado FROM caja_estado") == [("inactivo",)]


# ── CheckoutOrchestrator (main.py) de punta a punta ──────────────────────────

def escena(valor):
    return np.full((48, 64, 3), valor, dtype=np.uint8)


class CamaraGuionada:
    """Reemplaza al CaptureAgent: entrega 'n' frames quietos de cada escena, a 15 fps de tiempo de video."""

    def __init__(self, escenas, n=15, fps=15):
        self._frames = [(escena(v), i / fps) for i, v in enumerate(v for v in escenas for _ in range(n))]
        self.liberada = False

    def frames(self):
        yield from self._frames

    def release(self):
        self.liberada = True


class LLMGuionado:
    """Reemplaza al VisionAgent: cada analizar() devuelve la siguiente respuesta (dict o excepcion)."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = 0

    def analizar(self, frame):
        self.llamadas += 1
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class CajeraConsolaGuionada:
    """Cajera de consola con respuestas preparadas (mismo contrato que CashierInterfaceAgent)."""

    def __init__(self, *decisiones):
        self.decisiones = list(decisiones)
        self.pedidos = []

    def _decidir(self, tipo, producto):
        self.pedidos.append(tipo)
        cantidad = self.decisiones.pop(0)
        return (producto, cantidad) if cantidad else (None, 0)

    def confirmar_producto(self, producto, confianza):
        return self._decidir("confirmar", producto)

    def elegir_entre_candidatos(self, candidatos, datos_llm=None):
        return self._decidir("elegir", candidatos[0])

    def producto_manual(self):
        sku, cantidad = self.decisiones.pop(0)
        self.pedidos.append("manual")
        return ({"sku": sku, "nombre": "manual"}, cantidad) if sku else (None, 0)


@pytest.fixture
def orquestador(caja, monkeypatch):
    import main as caja_main
    assert Path(caja_main.__file__).parent == PRODUCTOS_DIR
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")

    def crear(escenas, respuestas_llm, cajera):
        o = caja_main.CheckoutOrchestrator("video.mp4", cashier=cajera)
        o.capture = CamaraGuionada(escenas)
        o.vision = LLMGuionado(respuestas_llm)
        return o
    return crear


def test_orquestador_sin_productos_en_la_base(caja, monkeypatch):
    import main as caja_main
    cur = caja.cursor()
    cur.execute("TRUNCATE productos CASCADE")
    caja.commit()
    with pytest.raises(RuntimeError, match="Base vacía"):
        caja_main.CheckoutOrchestrator("video.mp4")


def test_orquestador_por_defecto_usa_la_cajera_de_consola(orquestador):
    from agents.cashier_interface_agent import CashierInterfaceAgent
    import main as caja_main
    o = caja_main.CheckoutOrchestrator("video.mp4")
    assert isinstance(o.cashier, CashierInterfaceAgent)
    o.stock.close()


def test_consola_cada_producto_nuevo_llama_una_vez_al_llm_y_descuenta(orquestador, caja, capsys):
    cajera = CajeraConsolaGuionada(2, 1)
    o = orquestador([40, 200, 200], [llm("Coca-Cola", "Original", 500, "ml"), llm("Milka", "Leche", 100, "g")],
                    cajera)
    o.run()
    assert o.vision.llamadas == 2                     # la misma escena repetida no se vuelve a analizar
    assert cajera.pedidos == ["confirmar", "confirmar"]
    assert stock(caja, "SKU001") == 48 and stock(caja, "SKU018") == 2
    assert consultar(caja, "SELECT sku, cantidad, estado_matching, confirmado_por_cajera FROM transacciones "
                           "ORDER BY id") == [("SKU001", 2, "reconocido", True), ("SKU018", 1, "reconocido", True)]
    salida = capsys.readouterr().out
    assert "Llamadas al LLM: 2, ventas confirmadas: 2" in salida
    assert o.capture.liberada


def test_consola_ambiguo_pide_elegir_y_guarda_el_estado_del_matching(orquestador, caja):
    cajera = CajeraConsolaGuionada(1)
    o = orquestador([40], [llm("Lays", "Clasicas", 100, "g")], cajera)
    o.run()
    assert cajera.pedidos == ["elegir"]
    assert consultar(caja, "SELECT sku, estado_matching FROM transacciones") == [("SKU016", "confirmar")]


def test_consola_cancelar_no_descuenta(orquestador, caja, capsys):
    o = orquestador([40], [llm("Coca-Cola", "Original", 500, "ml")], CajeraConsolaGuionada(0))
    o.run()
    assert stock(caja, "SKU001") == 50
    assert "Cajera canceló" in capsys.readouterr().out


def test_sin_producto_o_confianza_baja_se_ignora_sin_molestar_a_la_cajera(orquestador, caja):
    cajera = CajeraConsolaGuionada()
    o = orquestador([40, 200], [{"producto_detectado": False}, llm("Milka", "Leche", 100, "g", confianza=0.3)],
                    cajera)
    o.run()
    assert cajera.pedidos == [] and o.vision.llamadas == 2
    assert consultar(caja, "SELECT COUNT(*) FROM transacciones") == [(0,)]


def test_producto_que_no_esta_en_la_base_pide_carga_manual(orquestador, caja):
    cajera = CajeraConsolaGuionada(("SKU002", 3))
    o = orquestador([40], [llm("Pantene", "Liso", 400, "ml")], cajera)
    o.run()
    assert cajera.pedidos == ["manual"]
    assert consultar(caja, "SELECT sku, cantidad, estado_matching FROM transacciones") == [
        ("SKU002", 3, "no_reconocido")]


def test_carga_manual_de_un_sku_inexistente_se_cancela(orquestador, caja, capsys):
    o = orquestador([40], [llm("Pantene", "Liso", 400, "ml")], CajeraConsolaGuionada(("NO-EXISTE", 1)))
    o.run()
    assert consultar(caja, "SELECT COUNT(*) FROM transacciones") == [(0,)]
    assert "SKU NO-EXISTE no existe en la base" in capsys.readouterr().out


def test_un_error_del_llm_no_corta_la_caja(orquestador, caja, capsys):
    cajera = CajeraConsolaGuionada(1)
    o = orquestador([40, 40, 200], [RuntimeError("529 overloaded"), llm("Coca-Cola", "Original", 500, "ml")],
                    cajera)
    o.run()
    # el frame que fallo queda marcado como analizado: no se reintenta en bucle la misma escena
    assert o.vision.llamadas == 2
    assert stock(caja, "SKU001") == 49
    assert "Error del VisionAgent: 529 overloaded" in capsys.readouterr().out


def test_un_error_inesperado_termina_ordenado(orquestador, caja, capsys):
    class Rota(CajeraConsolaGuionada):
        def confirmar_producto(self, producto, confianza):
            raise KeyError("boom")
    o = orquestador([40], [llm("Coca-Cola", "Original", 500, "ml")], Rota())
    o.run()
    salida = capsys.readouterr().out
    assert "Error inesperado" in salida and "Fin." in salida
    assert o.capture.liberada


def test_ctrl_c_termina_ordenado(orquestador, capsys):
    class Interrumpe(CajeraConsolaGuionada):
        def confirmar_producto(self, producto, confianza):
            raise KeyboardInterrupt
    o = orquestador([40], [llm("Coca-Cola", "Original", 500, "ml")], Interrumpe())
    o.run()
    assert "Interrumpido por usuario" in capsys.readouterr().out


def test_web_agrega_al_ticket_sin_descontar_y_manda_la_meta(orquestador, cajera_web, caja):
    o = orquestador([40], [llm("Coca-Cola", "Zero", 500, "ml", confianza=0.88)], cajera_web)
    with Navegador([{"accion": "confirmar", "cantidad": 2}]) as web:
        o.run()
    # en la web el stock se descuenta recien con "Confirmar venta" (endpoint de Flask), no aca
    assert stock(caja, "SKU002") == 40
    assert consultar(caja, "SELECT COUNT(*) FROM transacciones") == [(0,)]
    assert web.pendientes[0]["producto"]["sku"] == "SKU002"
    assert web.pendientes[0]["meta"]["confianza_llm"] == 0.88
    assert web.pendientes[0]["meta"]["estado_matching"] == "reconocido"
    assert consultar(caja, "SELECT estado FROM caja_estado") == [("inactivo",)]


def test_web_detener_mientras_espera_a_la_cajera(orquestador, cajera_web, caja, capsys):
    o = orquestador([40, 200], [llm("Coca-Cola", "Zero", 500, "ml"), llm("Milka", "Leche", 100, "g")], cajera_web)
    with Navegador(["detener"]):
        o.run()
    assert o.vision.llamadas == 1                      # no siguio con el segundo producto
    assert "mientras se esperaba una decisión" in capsys.readouterr().out
    assert consultar(caja, "SELECT estado FROM caja_estado") == [("inactivo",)]


def test_web_detener_entre_frames(orquestador, cajera_web, caja, capsys):
    cur = caja.cursor()
    cur.execute("UPDATE caja_estado SET estado = 'detener'")
    caja.commit()
    o = orquestador([40], [], cajera_web)
    o.run()
    assert o.vision.llamadas == 0
    assert "Detenido desde la web." in capsys.readouterr().out


def test_main_por_linea_de_comandos(caja, monkeypatch):
    """El bloque __main__ de main.py: --roi se parsea a una tupla y --web elige la cajera de la base."""
    import sys
    import main as caja_main
    creados = {}

    class OrquestadorEspia:
        def __init__(self, source, roi=None, cashier=None):
            creados.update(source=source, roi=roi, cajera=type(cashier).__name__)
            cashier.close()

        def run(self):
            creados["corrio"] = True
    monkeypatch.setattr(sys, "argv", ["main.py", "--source", "0", "--roi", "1,2,3,4", "--web"])
    texto = Path(caja_main.__file__).read_text(encoding="utf-8")
    bloque = "if True:" + texto.split('if __name__ == "__main__":', 1)[1]
    exec(compile(bloque, caja_main.__file__, "exec"), {**vars(caja_main), "CheckoutOrchestrator": OrquestadorEspia})
    assert creados == {"source": "0", "roi": (1, 2, 3, 4), "cajera": "DbCashierInterfaceAgent", "corrio": True}

"""Tests de POST /api/login (frontend/api/login.py): validacion de campos, mensajes genericos, bloqueo por intentos,
cuentas inactivas y respuesta sin datos sensibles. La base de datos se simula (no se necesita conexion)."""
import pytest

from frontend.api import app
from frontend.api import login as m

CLAVE = "admin1234"
HASH = m.hashear_clave(CLAVE)       # un solo hash para todos los tests (hashear cuesta ~0.3 s)

ADMIN = {"id": 1, "usuario": "agosblason", "email": "agosblason@gmail.com", "nombre": "Agostina Blason",
         "clave_hash": HASH, "activo": True, "cargo": "dueno", "rol": "administrador"}
EMPLEADO = {"id": 3, "usuario": "pauliiortizz", "email": "paulinaortizilr5@gmail.com", "nombre": "Paulina Ortiz Noseda",
            "clave_hash": HASH, "activo": True, "cargo": "empleado", "rol": "usuario"}
INACTIVO = {**EMPLEADO, "id": 9, "usuario": "baja", "email": "baja@x.com", "activo": False}
SUCURSALES = [{"id": 1, "nombre": "YPF Strumia", "localidad": "Piquillín"}]


class _Cursor:
    def __init__(self, conn):
        self.conn, self._res = conn, None

    def execute(self, sql, params=None):
        self.conn.sqls.append(sql)
        if "FROM usuarios u JOIN roles" in sql:
            ident = params["u"].lower()
            self._res = next((u for u in self.conn.usuarios
                              if u["usuario"].lower() == ident or (u["email"] or "").lower() == ident), None)
        elif "FROM usuarios_sucursales" in sql:
            self._res = self.conn.sucursales
        else:
            self._res = None

    def fetchone(self):
        return self._res

    def fetchall(self):
        return self._res

    def close(self):
        pass


class _Conn:
    def __init__(self, usuarios, sucursales):
        self.usuarios, self.sucursales, self.sqls, self.confirmado, self.cerrada = usuarios, sucursales, [], False, False

    def cursor(self, cursor_factory=None):
        return _Cursor(self)

    def commit(self):
        self.confirmado = True

    def close(self):
        self.cerrada = True


@pytest.fixture
def bd(monkeypatch):
    conn = _Conn([ADMIN, EMPLEADO, INACTIVO], SUCURSALES)
    monkeypatch.setattr(m, "_get_conn", lambda: conn)
    return conn


@pytest.fixture(autouse=True)
def limpio():
    m.reiniciar_limitador()
    yield
    m.reiniciar_limitador()


@pytest.fixture
def reloj(monkeypatch):
    t = {"ahora": 1000.0}
    monkeypatch.setattr(m, "_ahora", lambda: t["ahora"])
    return t


def entrar(usuario, clave):
    return app.test_client().post("/api/login", json={"usuario": usuario, "clave": clave})


# ── campos vacios ────────────────────────────────────────────────────────────────────────────────────────

def test_ambos_campos_vacios_marca_los_dos(bd):
    r = entrar("", "")
    assert r.status_code == 400
    d = r.get_json()
    assert d["ok"] is False
    assert d["campos"] == {"usuario": m.MSG_USUARIO_VACIO, "clave": m.MSG_CLAVE_VACIA}
    assert bd.sqls == []                               # ni siquiera consulta la base


def test_falta_solo_el_usuario(bd):
    d = entrar("   ", CLAVE).get_json()                # solo espacios cuenta como vacio
    assert list(d["campos"]) == ["usuario"] and d["error"] == m.MSG_USUARIO_VACIO


def test_falta_solo_la_clave(bd):
    r = entrar("agosblason", "")
    assert r.status_code == 400
    assert list(r.get_json()["campos"]) == ["clave"] and r.get_json()["error"] == m.MSG_CLAVE_VACIA


def test_cuerpo_ausente_o_invalido(bd):
    c = app.test_client()
    assert c.post("/api/login").status_code == 400
    assert c.post("/api/login", data="no-json", content_type="text/plain").status_code == 400
    assert c.post("/api/login", json={"usuario": None, "clave": None}).status_code == 400


# ── mensaje generico ─────────────────────────────────────────────────────────────────────────────────────

def test_usuario_inexistente_y_clave_incorrecta_dan_exactamente_la_misma_respuesta(bd):
    inexistente = entrar("nadie", CLAVE)
    mal_clave = entrar("agosblason", "otra-clave")
    assert inexistente.status_code == mal_clave.status_code == 401
    assert inexistente.get_json() == mal_clave.get_json() == {"ok": False, "error": m.MSG_INVALIDO}


def test_el_mensaje_no_dice_cual_de_los_dos_esta_mal():
    assert "email" in m.MSG_INVALIDO and "contraseña" in m.MSG_INVALIDO
    for prohibido in ("no existe", "inexistente", "no encontrado"):
        assert prohibido not in m.MSG_INVALIDO.lower()


def test_usuario_inexistente_igual_verifica_una_clave_para_no_delatarse_por_tiempo(bd, monkeypatch):
    llamadas = []
    real = m.verificar_clave
    monkeypatch.setattr(m, "verificar_clave", lambda c, h: llamadas.append(h) or real(c, h))
    entrar("nadie", CLAVE)
    assert llamadas == [m._HASH_RELLENO]


def test_cuenta_desactivada_da_el_mismo_mensaje_aunque_la_clave_sea_correcta(bd):
    r = entrar("baja", CLAVE)
    assert r.status_code == 401 and r.get_json() == {"ok": False, "error": m.MSG_INVALIDO}


def test_texto_excesivamente_largo_se_rechaza_sin_consultar(bd):
    assert entrar("a" * 500, CLAVE).status_code == 401
    assert entrar("agosblason", "x" * 500).status_code == 401
    assert bd.sqls == []


# ── ingreso correcto ─────────────────────────────────────────────────────────────────────────────────────

def test_ingreso_correcto_del_administrador(bd):
    r = entrar("agosblason", CLAVE)
    assert r.status_code == 200
    d = r.get_json()
    assert d == {"ok": True, "usuario": "agosblason", "nombre": "Agostina Blason", "email": "agosblason@gmail.com",
                 "rol": "administrador", "cargo": "dueno", "sucursales": SUCURSALES}
    assert bd.confirmado and bd.cerrada
    assert any("ultimo_acceso" in s for s in bd.sqls)


def test_ingreso_correcto_del_empleado_tiene_rol_usuario(bd):
    d = entrar("pauliiortizz", CLAVE).get_json()
    assert d["ok"] is True and d["rol"] == "usuario" and d["cargo"] == "empleado"


def test_se_puede_ingresar_con_el_email(bd):
    d = entrar("paulinaortizilr5@gmail.com", CLAVE).get_json()
    assert d["ok"] is True and d["usuario"] == "pauliiortizz"


def test_no_distingue_mayusculas_en_usuario_ni_email(bd):
    assert entrar("AgosBlason", CLAVE).status_code == 200
    assert entrar("AGOSBLASON@GMAIL.COM", CLAVE).status_code == 200


def test_la_clave_si_distingue_mayusculas(bd):
    assert entrar("agosblason", CLAVE.upper()).status_code == 401


def test_espacios_alrededor_del_usuario_se_ignoran_pero_los_de_la_clave_no(bd):
    assert entrar("  agosblason  ", CLAVE).status_code == 200
    assert entrar("agosblason", f" {CLAVE}").status_code == 401


def test_la_respuesta_nunca_incluye_el_hash_ni_la_clave(bd):
    for r in (entrar("agosblason", CLAVE), entrar("agosblason", "mal"), entrar("nadie", "x")):
        texto = r.get_data(as_text=True)
        assert HASH not in texto and "clave_hash" not in texto and "pbkdf2" not in texto and CLAVE not in texto


# ── bloqueo por intentos fallidos ────────────────────────────────────────────────────────────────────────

def test_se_bloquea_tras_los_intentos_fallidos_y_no_deja_pasar_ni_con_la_clave_correcta(bd, reloj):
    for _ in range(m.LIMITE_FALLOS):
        assert entrar("agosblason", "mal").status_code == 401
    r = entrar("agosblason", CLAVE)
    assert r.status_code == 429
    d = r.get_json()
    assert d["bloqueado"] is True and 0 < d["reintentar_en"] <= m.BLOQUEO_SEG
    assert "5 minutos" in d["error"]


def test_el_bloqueo_vence_con_el_tiempo(bd, reloj):
    for _ in range(m.LIMITE_FALLOS):
        entrar("agosblason", "mal")
    assert entrar("agosblason", CLAVE).status_code == 429
    reloj["ahora"] += m.BLOQUEO_SEG + 1
    assert entrar("agosblason", CLAVE).status_code == 200


def test_un_ingreso_correcto_reinicia_el_contador(bd, reloj):
    for _ in range(m.LIMITE_FALLOS - 1):
        entrar("agosblason", "mal")
    assert entrar("agosblason", CLAVE).status_code == 200
    for _ in range(m.LIMITE_FALLOS - 1):                # arranca de cero: todavia no se bloquea
        assert entrar("agosblason", "mal").status_code == 401
    assert entrar("agosblason", CLAVE).status_code == 200


def test_el_bloqueo_de_un_usuario_no_afecta_a_otro(bd, reloj):
    for _ in range(m.LIMITE_FALLOS):
        entrar("agosblason", "mal")
    assert entrar("pauliiortizz", CLAVE).status_code == 200


def test_tambien_se_bloquea_un_usuario_inexistente_sin_revelar_que_no_existe(bd, reloj):
    for _ in range(m.LIMITE_FALLOS):
        entrar("fantasma", "mal")
    r = entrar("fantasma", "mal")
    assert r.status_code == 429                         # igual que si existiera


def test_el_bloqueo_no_distingue_mayusculas(bd, reloj):
    for _ in range(m.LIMITE_FALLOS):
        entrar("AgosBlason", "mal")
    assert entrar("agosblason", CLAVE).status_code == 429


def test_los_campos_vacios_no_cuentan_como_intento_fallido(bd, reloj):
    for _ in range(m.LIMITE_FALLOS + 2):
        entrar("agosblason", "")
    assert entrar("agosblason", CLAVE).status_code == 200


# ── fallas del servidor ──────────────────────────────────────────────────────────────────────────────────

def test_sin_conexion_a_la_base_da_503_con_otro_mensaje(monkeypatch):
    monkeypatch.setattr(m, "_get_conn", lambda: None)
    r = entrar("agosblason", CLAVE)
    assert r.status_code == 503 and r.get_json() == {"ok": False, "error": m.MSG_SIN_SERVIDOR}


def test_error_inesperado_de_la_base_da_503_y_cierra_la_conexion(monkeypatch):
    class Rota(_Conn):
        def cursor(self, cursor_factory=None):
            raise RuntimeError("se cayo la base")
    conn = Rota([], [])
    monkeypatch.setattr(m, "_get_conn", lambda: conn)
    r = entrar("agosblason", CLAVE)
    assert r.status_code == 503 and "se cayo" not in r.get_data(as_text=True)
    assert conn.cerrada


def test_una_falla_del_servidor_no_cuenta_como_intento_fallido(monkeypatch, reloj):
    monkeypatch.setattr(m, "_get_conn", lambda: None)
    for _ in range(m.LIMITE_FALLOS + 2):
        entrar("agosblason", CLAVE)
    conn = _Conn([ADMIN], SUCURSALES)
    monkeypatch.setattr(m, "_get_conn", lambda: conn)
    assert entrar("agosblason", CLAVE).status_code == 200


# ── hash de claves ───────────────────────────────────────────────────────────────────────────────────────

def test_el_hash_no_es_la_clave_y_cada_hash_lleva_su_propia_sal():
    h1, h2 = m.hashear_clave(CLAVE), m.hashear_clave(CLAVE)
    assert CLAVE not in h1 and h1 != h2
    assert m.verificar_clave(CLAVE, h1) and m.verificar_clave(CLAVE, h2)
    assert not m.verificar_clave("otra", h1)

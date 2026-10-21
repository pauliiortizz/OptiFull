"""Tests de la sesion del lado del servidor (frontend/api/sesion.py), regresion de DEF-004: la API
respondia a cualquiera, sin verificar el login. Estos tests usan la cookie real (sin la sesion de
prueba de conftest.py)."""
import time

import pytest

from api import app, login, productos, sesion

pytestmark = pytest.mark.sin_sesion

CLAVE = "clave-segura-1"
USUARIO = {"id": 4, "usuario": "agos", "email": "agos@x.com", "nombre": "Agostina", "activo": True,
           "cargo": "dueña", "rol": "administrador", "clave_hash": login.hashear_clave(CLAVE)}


@pytest.fixture
def cliente():
    login.reiniciar_limitador()
    return app.test_client()


@pytest.fixture
def con_usuario(monkeypatch, bd):
    bd.responder("FROM usuarios u JOIN roles", [USUARIO]).responder("FROM usuarios_sucursales", [])
    monkeypatch.setattr(login, "_get_conn", lambda: bd)
    return bd


def entrar(cliente, mantener=None):
    body = {"usuario": "agos", "clave": CLAVE}
    if mantener is not None:
        body["mantener"] = mantener
    return cliente.post("/api/login", json=body)


def cookie_de(r):
    return next(h for h in r.headers.getlist("Set-Cookie") if h.startswith(f"{sesion.COOKIE}="))


# ── Sin sesion ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("metodo, ruta", [
    ("get", "/api/personas"), ("get", "/api/alertas"), ("get", "/api/reportes/opciones"),
    ("get", "/api/export/csv"), ("get", "/api/sessions"), ("get", "/api/video/a.mp4"),
    ("get", "/api/productos/stock"), ("post", "/api/productos/venta"), ("post", "/api/personas/1/empleado"),
    ("post", "/api/alertas/1/resolver"), ("post", "/api/productos/iniciar"), ("get", "/api/sesion"),
])
def test_sin_sesion_la_api_responde_401(cliente, metodo, ruta):
    r = getattr(cliente, metodo)(ruta, json={})
    assert r.status_code == 401
    assert r.get_json() == {"error": "Iniciá sesión para continuar."}


@pytest.mark.parametrize("metodo, ruta, no_esperado", [
    ("get", "/api/health", 401),
    ("post", "/api/leads", 401),                      # formulario de la landing (responde 400: body vacio)
    ("get", "/api/stats", 401),                       # numeros de la landing
    ("get", "/api/heatmap/camara/4", 401),            # mapa de calor de la landing
    ("get", "/api/heatmap/image/no_existe.png", 401),
    ("post", "/api/login", 401),                      # responde 400: campos vacios
    ("post", "/api/logout", 401),
])
def test_endpoints_publicos_no_piden_sesion(cliente, monkeypatch, metodo, ruta, no_esperado):
    from api import db, heatmap, stats
    monkeypatch.setattr(db, "_get_conn", lambda: None)
    monkeypatch.setattr(heatmap, "_db_connect", lambda: None)
    monkeypatch.setattr(stats, "cargar_db", lambda *a, **k: [])
    assert getattr(cliente, metodo)(ruta, json={}).status_code != no_esperado


# ── Login y cookie ────────────────────────────────────────────────────────────

def test_login_deja_una_cookie_httponly_samesite_que_da_acceso_a_la_api(cliente, con_usuario, monkeypatch, bd):
    r = entrar(cliente)
    assert r.status_code == 200
    cookie = cookie_de(r)
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert "Max-Age" not in cookie and "Secure" not in cookie   # sin "mantener": se borra al cerrar el navegador
    assert sesion.COOKIE not in r.get_data(as_text=True)          # el token no viaja en el body
    monkeypatch.setattr(productos, "_get_conn", lambda: bd)
    assert cliente.get("/api/productos/stock").status_code == 200
    assert cliente.get("/api/sesion").get_json() == {"usuario": "agos", "rol": "administrador"}


def test_mantener_sesion_dura_30_dias(cliente, con_usuario):
    assert f"Max-Age={30 * 24 * 3600}" in cookie_de(entrar(cliente, mantener=True))


def test_mantener_solo_acepta_true(cliente, con_usuario):
    assert "Max-Age" not in cookie_de(entrar(cliente, mantener="si"))


def test_en_qa_y_produccion_la_cookie_es_secure(cliente, con_usuario, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert "Secure" in cookie_de(entrar(cliente))


def test_login_fallido_no_deja_cookie(cliente, con_usuario):
    r = cliente.post("/api/login", json={"usuario": "agos", "clave": "otra"})
    assert r.status_code == 401
    assert not [h for h in r.headers.getlist("Set-Cookie") if h.startswith(sesion.COOKIE)]


def test_logout_borra_la_cookie(cliente, con_usuario):
    entrar(cliente)
    assert cliente.post("/api/logout").get_json() == {"ok": True}
    assert cliente.get("/api/sesion").status_code == 401


# ── Cookie adulterada o vencida ───────────────────────────────────────────────

def _token(datos, hace_seg=0, monkeypatch=None):
    ahora = time.time()
    monkeypatch.setattr(time, "time", lambda: ahora - hace_seg)
    token = sesion._firmador.dumps(datos)
    monkeypatch.setattr(time, "time", lambda: ahora)
    return token


def test_cookie_adulterada_no_da_acceso(cliente, monkeypatch):
    token = _token({"id": 1, "usuario": "x", "rol": "usuario", "dur": 3600}, monkeypatch=monkeypatch)
    adulterado = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")   # cualquier cambio rompe la firma
    cliente.set_cookie(sesion.COOKIE, adulterado)
    assert cliente.get("/api/sesion").status_code == 401


def test_cookie_firmada_con_otra_clave_no_da_acceso(cliente):
    from itsdangerous import URLSafeTimedSerializer
    falso = URLSafeTimedSerializer("clave-de-un-atacante", salt="optifull-sesion")
    cliente.set_cookie(sesion.COOKIE, falso.dumps({"id": 1, "usuario": "x", "rol": "administrador"}))
    assert cliente.get("/api/sesion").status_code == 401


@pytest.mark.parametrize("dur, hace_horas, status", [
    (sesion.DURACION_SEG, 11, 200),             # sesion normal (12 h): todavia vale
    (sesion.DURACION_SEG, 13, 401),             # ...vencida
    (sesion.DURACION_MANTENER_SEG, 13, 200),    # "mantener sesion": vale 30 dias
    (sesion.DURACION_MANTENER_SEG, 31 * 24, 401),
])
def test_vencimiento_de_la_sesion(cliente, monkeypatch, dur, hace_horas, status):
    token = _token({"id": 1, "usuario": "x", "rol": "administrador", "dur": dur}, hace_horas * 3600, monkeypatch)
    cliente.set_cookie(sesion.COOKIE, token)
    assert cliente.get("/api/sesion").status_code == status


def test_sin_secret_key_usa_una_clave_temporal(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert len(sesion._clave_secreta()) == 64
    monkeypatch.setenv("SECRET_KEY", "fija")
    assert sesion._clave_secreta() == "fija"

"""Prueba E2E del flujo principal de OptiFull, con un navegador real (Playwright + Chromium) contra un despliegue.

Recorre lo mismo que hace un usuario: landing publica -> login -> la seccion inicial de su rol con los datos
de la base (administrador: dashboard y un reporte descargado; empleado: Productos con el stock) -> alertas ->
cerrar sesion. En QA eso atraviesa todo el sistema: el frontend servido por Render, la API Flask y la base de
datos y el Storage de Supabase.

Ademas de lo que se ve en pantalla, durante todo el recorrido se vigila que ningun pedido a /api/* responda 5xx
y que la pagina no tire errores de JavaScript.

  BASE_URL=https://optifull-qa.onrender.com QA_USUARIO=... QA_CLAVE=... pytest -c test/pytest.ini test/e2e
  E2E_CANAL=msedge   (opcional) usar un navegador instalado en vez del Chromium de Playwright

Requiere `pip install playwright` y `playwright install chromium`. Si BASE_URL no esta definida se saltea.
"""
import os
import re
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect

BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
USUARIO = os.environ.get("QA_USUARIO")
CLAVE = os.environ.get("QA_CLAVE")
CANAL = os.environ.get("E2E_CANAL") or None
SALIDA = Path(os.environ.get("E2E_SALIDA", "test-results/e2e"))
# Render (plan gratuito) puede tardar en despertar y los reportes en generarse.
TIMEOUT_MS = 90_000

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not BASE_URL, reason="BASE_URL no definida")]


@pytest.fixture(scope="module")
def navegador():
    with playwright_api.sync_playwright() as p:
        b = p.chromium.launch(channel=CANAL)
        yield b
        b.close()


@pytest.fixture
def pagina(navegador, request):
    """Pagina nueva por test. Junta los 5xx de la API y los errores de JS, y al terminar deja una captura y la
    traza de Playwright en test-results/e2e/ (se abre con `playwright show-trace <archivo>`)."""
    SALIDA.mkdir(parents=True, exist_ok=True)
    contexto = navegador.new_context(base_url=BASE_URL, accept_downloads=True, locale="es-AR")
    contexto.set_default_timeout(TIMEOUT_MS)
    contexto.tracing.start(screenshots=True, snapshots=True)
    pg = contexto.new_page()
    pg.problemas = []
    pg.on("response", lambda r: "/api/" in r.url and r.status >= 500
          and pg.problemas.append(f"{r.status} {r.request.method} {r.url}"))
    pg.on("pageerror", lambda e: pg.problemas.append(f"error de JS: {e}"))
    yield pg
    pg.screenshot(path=SALIDA / f"{request.node.name}.png", full_page=True)
    contexto.tracing.stop(path=SALIDA / f"{request.node.name}-traza.zip")
    contexto.close()


def iniciar_sesion(pg):
    """Inicia sesion y devuelve el rol de la cuenta ('administrador' o 'usuario')."""
    pg.goto("/login")
    pg.get_by_label("Email o usuario").fill(USUARIO)
    pg.get_by_label("Contraseña", exact=True).fill(CLAVE)
    with pg.expect_response(lambda r: r.url.endswith("/api/login")) as login:
        pg.get_by_role("button", name="Ingresar").click()
    assert login.value.status == 200, f"El login fallo: {login.value.status} (revisar QA_USUARIO / QA_CLAVE)"
    expect(pg).to_have_url(re.compile(r"/dashboard$"))
    return login.value.json()["rol"]


def ir_a(pg, seccion):
    # Items del menu lateral; "Alertas" puede llevar al lado el numero de pendientes.
    pg.get_by_role("navigation").get_by_role("link", name=re.compile(rf"^{seccion}\b")).first.click()


def test_landing_publica_con_estadisticas(pagina):
    with pagina.expect_response(lambda r: "/api/stats" in r.url) as stats:
        pagina.goto("/")
    assert stats.value.status == 200
    expect(pagina.get_by_role("button", name="Ya soy cliente")).to_be_visible()
    assert pagina.problemas == []


def test_flujo_completo_login_panel_alertas_logout(pagina):
    """El recorrido depende del rol de la cuenta (frontend/src/components/permisos.js):
    administrador -> dashboard con datos y un reporte descargado; usuario (empleado) -> Productos con el stock
    de la base y sin acceso a Dashboard ni Reportes. Los dos siguen con alertas y logout."""
    if not (USUARIO and CLAVE):
        pytest.fail("Faltan QA_USUARIO y QA_CLAVE: sin una cuenta no se puede recorrer el panel")

    # 1. Login -> la seccion inicial del rol, con datos de la base
    seccion_inicial = ("/api/stats", "/api/productos/stock")
    with pagina.expect_response(lambda r: r.request.method == "GET" and any(s in r.url for s in seccion_inicial)) as datos:
        rol = iniciar_sesion(pagina)
    assert datos.value.status == 200, f"{datos.value.url} respondio {datos.value.status}"
    menu = pagina.get_by_role("navigation")

    if rol == "administrador":
        assert "/api/stats" in datos.value.url
        assert datos.value.json()["fuente"] == "db"
        expect(pagina.get_by_role("heading", name="Operaciones")).to_be_visible()

        # 2. Reportes: todas las metricas en CSV, se genera y se descarga
        with pagina.expect_response(lambda r: "/api/reportes/opciones" in r.url) as opciones:
            ir_a(pagina, "Reportes")
        assert opciones.value.status == 200
        pagina.get_by_role("switch", name=re.compile("^Seleccionar todo")).check()
        pagina.get_by_role("radiogroup", name="Formato de exportación").locator("input[value=csv]").check(force=True)
        with pagina.expect_download() as descarga:
            pagina.get_by_role("button", name="Generar y descargar reporte").click()
        archivo = SALIDA / descarga.value.suggested_filename
        descarga.value.save_as(archivo)
        assert archivo.stat().st_size > 0
        expect(pagina.get_by_role("status")).to_contain_text("se descargó correctamente")
    else:
        # 2. Empleado: arranca en Productos con el stock de la base y no ve las secciones de analisis
        assert rol == "usuario", f"rol inesperado: {rol}"
        assert "/api/productos/stock" in datos.value.url
        expect(menu.get_by_role("link", name=re.compile(r"^Productos\b"))).to_have_attribute("aria-current", "page")
        for oculta in ("Dashboard", "Reportes", "Configuración"):
            expect(menu.get_by_role("link", name=re.compile(rf"^{oculta}\b"))).to_have_count(0)

    # 3. Alertas (lista desde la base)
    with pagina.expect_response(lambda r: re.search(r"/api/alertas(\?|$)", r.url)) as alertas:
        ir_a(pagina, "Alertas")
    assert alertas.value.status == 200

    # 4. Logout: el boton pide confirmacion ("¿Deseás cerrar sesión?"); con "Sí, cerrar sesión" vuelve a la
    # landing y la cookie deja de valer. El panel no espera la respuesta de /api/logout para cambiar de pantalla,
    # y es esa respuesta la que borra la cookie: hay que esperarla (en QA, con la latencia de Render, la consulta
    # de abajo llegaba antes y todavia viajaba con la cookie).
    pagina.get_by_role("button", name="Cerrar sesión").click()
    confirmar = pagina.get_by_role("alertdialog", name="¿Deseás cerrar sesión?")
    expect(confirmar).to_be_visible()
    with pagina.expect_response(lambda r: r.url.endswith("/api/logout")) as salida:
        confirmar.get_by_role("button", name="Sí, cerrar sesión").click()
    assert salida.value.status == 200
    expect(pagina.get_by_role("button", name="Ya soy cliente")).to_be_visible()
    assert pagina.request.get("/api/personas").status == 401

    assert pagina.problemas == [], "Hubo errores durante el recorrido:\n" + "\n".join(pagina.problemas)

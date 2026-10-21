"""Vulnerabilidades que marco SonarQube Cloud (y una que no) en la API: DEF-023 a DEF-027.

Cada test reproduce el ataque contra la app Flask real; los subprocesos y las conexiones HTTP se reemplazan.
La revision completa de las 10 observaciones (cuales eran reales y por que las otras no) esta en
docs/calidad/defectos.md.
"""
import subprocess

import pytest

from api import app
from api import productos, video


@pytest.fixture
def cliente():
    return app.test_client()


# ── DEF-023: el proxy de la camara del celular sirve para pedir URLs internas (SSRF) ──
# /api/productos/camara solo aceptaba IPs "privadas", pero ipaddress.is_private incluye 127.0.0.1 (servicios del
# propio servidor) y 169.254.169.254 (metadatos de la nube). En Render, ademas, la camara del celular del local
# nunca es alcanzable: el endpoint solo servia para eso.

@pytest.fixture
def sin_red(monkeypatch):
    pedidos = []

    def urlopen(pedido, timeout=None):
        pedidos.append(pedido.full_url)
        raise OSError("sin red en los tests")
    monkeypatch.setattr(productos.urllib.request, "urlopen", urlopen)
    return pedidos


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8080/api/health",          # el propio servidor
    "http://169.254.169.254/latest/meta-data/",  # metadatos de la nube
    "http://0.0.0.0:5432/",
    "http://[::1]/",
])
def test_def023_camara_rechaza_loopback_y_metadatos(cliente, sin_red, url):
    r = cliente.get("/api/productos/camara", query_string={"url": url})
    assert r.status_code == 400
    assert sin_red == []                         # ni siquiera intenta conectarse


@pytest.mark.parametrize("entorno", ["qa", "production"])
def test_def023_en_la_nube_el_proxy_de_la_camara_no_existe(cliente, sin_red, monkeypatch, entorno):
    monkeypatch.setenv("APP_ENV", entorno)
    r = cliente.get("/api/productos/camara", query_string={"url": "http://192.168.0.10:8081/video"})
    assert r.status_code == 404
    assert sin_red == []


def test_def023_en_el_local_la_camara_de_la_red_sigue_andando(cliente, sin_red, monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    r = cliente.get("/api/productos/camara", query_string={"url": "http://192.168.0.10:8081/video"})
    assert r.status_code == 502                  # llego a intentar la conexion (en el test no hay red)
    assert sin_red == ["http://192.168.0.10:8081/video"]


# ── DEF-024: los archivos del frontend permiten averiguar que archivos hay en el servidor ──
# GET /<ruta> respondia 404 si la ruta salia de frontend/dist/ hacia un archivo que EXISTE y 200 (la SPA) si no
# existia: sin iniciar sesion, desde internet, se podia saber si hay un .env, que modulos tiene la API, etc.

@pytest.mark.parametrize("existe, no_existe", [
    ("/../api/paths.py", "/../api/no_existe.py"),
    ("/../../README.md", "/../../NO_EXISTE.md"),
    ("/assets/../../api/db.py", "/assets/../../api/nada.py"),
])
def test_def024_salir_de_dist_responde_igual_exista_o_no_el_archivo(cliente, existe, no_existe):
    a, b = cliente.get(existe), cliente.get(no_existe)
    assert (a.status_code, a.data) == (b.status_code, b.data)


def test_def024_los_archivos_del_build_se_siguen_sirviendo(cliente, tmp_path, monkeypatch):
    import api
    (tmp_path / "index.html").write_text("<html>OptiFull</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setattr(api, "DIST", str(tmp_path))
    assert cliente.get("/assets/app.js").data == b"console.log(1)"
    assert cliente.get("/reportes/alguna-ruta").data == b"<html>OptiFull</html>"   # fallback de la SPA


# ── DEF-025: /productos/iniciar lanza la caja con cualquier 'source' y 'roi' ───────────
# Cualquier cuenta con sesion (tambien un empleado) podia hacer que el servidor abriera como "video" un archivo
# cualquiera del disco o una URL cualquiera (ffmpeg/OpenCV la piden). Ahora solo se aceptan los videos de las
# carpetas del sistema y camaras de la red local, y el roi tiene que ser x1,y1,x2,y2.

class ProcesoFalso:
    pid = 4321

    def poll(self):
        return 0


@pytest.fixture
def caja(monkeypatch, tmp_path):
    """Carpeta de deteccion_productos/ y de videos en tmp; Popen falso."""
    dp = tmp_path / "deteccion_productos"
    (dp / "data" / "videos").mkdir(parents=True)
    (dp / "data" / "videos" / "prueba.mp4").write_bytes(b"mp4")
    videos = tmp_path / "videos"
    videos.mkdir()
    (videos / "caja.mp4").write_bytes(b"mp4")
    (tmp_path / "secreto.env").write_text("CLAVE=1")
    lanzados = []
    monkeypatch.setattr(productos, "DETECCION_PRODUCTOS_DIR", str(dp))
    monkeypatch.setattr(productos, "VIDEOS_DIR", str(videos), raising=False)
    monkeypatch.setattr(productos, "_proceso_caja", None)
    monkeypatch.setattr(subprocess, "Popen", lambda comando, **kw: lanzados.append(comando) or ProcesoFalso())
    return lanzados


@pytest.mark.parametrize("source", [
    "../secreto.env",                            # un archivo cualquiera del disco
    "../videos/../secreto.env",
    "data/videos/no_existe.mp4",
    "http://8.8.8.8/stream",                     # una URL de internet
    "http://127.0.0.1:8080/api/health",
    "rtsp://169.254.169.254/x",
    "file:///etc/passwd",
    "--help",
])
def test_def025_iniciar_rechaza_fuentes_que_no_son_videos_ni_camaras_locales(cliente, caja, source):
    r = cliente.post("/api/productos/iniciar", json={"source": source})
    assert r.status_code == 400
    assert caja == []


@pytest.mark.parametrize("roi", ["0,0,100", "a,b,c,d", "0,0,100,100 --help", "-1,0,10,10"])
def test_def025_iniciar_rechaza_un_roi_mal_formado(cliente, caja, roi):
    r = cliente.post("/api/productos/iniciar", json={"source": "data/videos/prueba.mp4", "roi": roi})
    assert r.status_code == 400
    assert caja == []


@pytest.mark.parametrize("source", [
    "data/videos/prueba.mp4",                    # videos de deteccion_productos/data/videos
    "../videos/caja.mp4",                        # lo que manda la caja web (ProductosPage.jsx)
    "http://admin:admin@192.168.0.10:8081/video",  # el celular por la red local
    "rtsp://10.0.0.7:554/stream",                # una camara IP del local
])
def test_def025_iniciar_acepta_los_videos_y_las_camaras_del_local(cliente, caja, source):
    r = cliente.post("/api/productos/iniciar", json={"source": source, "roi": "0,0,640,480"})
    assert r.status_code == 200, r.get_json()
    assert caja[0][caja[0].index("--source") + 1] == source


# ── DEF-026: el panel se puede incrustar en otro sitio (clickjacking) ──────────────────
# Ninguna respuesta decia que no se podia mostrar dentro de un <iframe> ajeno. SonarQube Cloud lo marco por el lado
# de TweaksPanel.jsx, que acepta mensajes postMessage de cualquier origen; ademas, ese listener ahora solo existe en
# desarrollo.

@pytest.mark.parametrize("ruta", ["/", "/api/health", "/reportes/x"])
def test_def026_ninguna_respuesta_se_puede_incrustar_en_otro_sitio(cliente, ruta):
    r = cliente.get(ruta)
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"


# ── DEF-027: /api/video/<archivo> sale a carpetas vecinas cuyo nombre empieza igual ─────
# Lo encontro la revision, no SonarQube Cloud: se comparaba con startswith('.../videos'), asi que
# '../videos_privado/x.mp4' (= '.../videos_privado/x.mp4') pasaba el control.

def test_def027_video_no_sale_a_una_carpeta_vecina_con_el_mismo_prefijo(cliente, tmp_path, monkeypatch):
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos_privado").mkdir()
    (tmp_path / "videos_privado" / "camara_banio.mp4").write_bytes(b"privado")
    monkeypatch.setattr(video, "VIDEOS_DIR", str(tmp_path / "videos"))
    r = cliente.get("/api/video/../videos_privado/camara_banio.mp4")
    assert r.status_code in (403, 404)
    assert b"privado" not in r.data

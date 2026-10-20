"""Pruebas de carga de OptiFull con Locust: stress y esfuerzo sostenido contra un despliegue.

Cada usuario virtual hace lo que hace alguien con el panel abierto: inicia sesion una vez y despues mira el
dashboard (stats, personas, mapa de calor), las alertas y las opciones de reportes, con pausas de 1 a 3 s.
Solo lecturas: no escribe nada en la base.

El perfil se elige con CARGA_PERFIL (ver PERFILES):
  stress     sube de a escalones hasta 40 usuarios para ver donde se degrada (6 min)
  sostenida  15 usuarios constantes durante 10 min: memoria, conexiones a la BD, estabilidad

  BASE_URL=... QA_USUARIO=... QA_CLAVE=... CARGA_PERFIL=stress \\
    locust -f test/carga/locustfile.py --headless --host $BASE_URL --csv test-results/carga/stress \\
    --html test-results/carga/stress.html
  python test/carga/verificar_umbrales.py stress test-results/carga/stress_stats.csv

Los umbrales que tiene que cumplir cada perfil estan en verificar_umbrales.py.
"""
import os

from locust import HttpUser, LoadTestShape, between, task

USUARIO = os.environ.get("QA_USUARIO")
CLAVE = os.environ.get("QA_CLAVE")

# (segundos desde el inicio, usuarios, usuarios nuevos por segundo): cada tramo dura hasta su segundo final.
PERFILES = {
    "stress": [(60, 5, 1), (120, 10, 1), (180, 20, 2), (240, 30, 2), (300, 40, 2), (360, 40, 2)],
    "sostenida": [(600, 15, 1)],
}


class UsuarioDelPanel(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        if not (USUARIO and CLAVE):
            raise RuntimeError("Faltan QA_USUARIO y QA_CLAVE: la API exige sesion")
        with self.client.post("/api/login", json={"usuario": USUARIO, "clave": CLAVE},
                              name="POST /api/login", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"login {r.status_code}")

    @task(4)
    def stats(self):
        self.client.get("/api/stats", name="GET /api/stats")

    @task(3)
    def personas(self):
        self.client.get("/api/personas", name="GET /api/personas")

    @task(3)
    def alertas(self):
        self.client.get("/api/alertas", name="GET /api/alertas")

    @task(2)
    def mapa_de_calor(self):
        with self.client.get("/api/heatmap/latest", name="GET /api/heatmap/latest", catch_response=True) as r:
            if r.status_code == 404:      # todavia no hay mapas de calor: no es un error del servicio
                r.success()

    @task(1)
    def opciones_de_reportes(self):
        self.client.get("/api/reportes/opciones", name="GET /api/reportes/opciones")

    @task(1)
    def health(self):
        self.client.get("/api/health", name="GET /api/health")

    @task(1)
    def frontend(self):
        self.client.get("/", name="GET / (frontend)")


# Locust usa la forma de carga siempre que el archivo define una: por eso solo existe si se eligio un perfil
# (sin CARGA_PERFIL valen -u/-r/-t de la linea de comandos, util para probar a mano).
if os.environ.get("CARGA_PERFIL") in PERFILES:
    class Perfil(LoadTestShape):
        tramos = PERFILES[os.environ["CARGA_PERFIL"]]

        def tick(self):
            t = self.get_run_time()
            for fin, usuarios, ritmo in self.tramos:
                if t < fin:
                    return usuarios, ritmo
            return None

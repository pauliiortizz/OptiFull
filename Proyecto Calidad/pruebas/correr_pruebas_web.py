"""Corre las pruebas del módulo de interfaz web de OptiFull (frontend/) y muestra un resumen.

Pensado para ejecutarlo delante del docente. Desde la raíz del repositorio:

  python "Proyecto Calidad/pruebas/correr_pruebas_web.py"            # API + panel, con cobertura
  python "Proyecto Calidad/pruebas/correr_pruebas_web.py" --smoke    # + smoke contra QA (no necesita clave)
  python "Proyecto Calidad/pruebas/correr_pruebas_web.py" --qa       # + smoke, integración y E2E contra QA

Qué corre:
  1. API (frontend/api): los tests unitarios de la API, con cobertura de sentencia y decisión.
  2. Persistencia: el pool de conexiones contra un Postgres real, solo si está TEST_DATABASE_URL.
  3. Panel (frontend/src): los tests de Vitest, con cobertura.
  4. Opcional: smoke, integración y E2E contra QA en Render.

Variables para --qa: QA_USUARIO y QA_CLAVE (la cuenta con la que se inicia sesión). BASE_URL es opcional (por
defecto, QA). El E2E necesita además `pip install -r test/requirements-qa.txt` y `python -m playwright install
chromium`.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
QA_POR_DEFECTO = "https://optifull-qa.onrender.com"

# Tests de la API del módulo web (los demás archivos de test/unitarios son de los pipelines de video y de caja).
TESTS_API = [
    "test_api_basica", "test_calcular_stats", "test_export", "test_health", "test_heatmap", "test_leads",
    "test_login", "test_plano_calor", "test_productos", "test_rango_fechas", "test_reportes",
    "test_reportes_datos", "test_reportes_export", "test_reportes_formatos", "test_seguridad", "test_sesion",
    "test_video",
]


def titulo(texto):
    print(f"\n{'=' * 78}\n  {texto}\n{'=' * 78}", flush=True)


def correr(nombre, comando, cwd=RAIZ, env=None):
    """Ejecuta un comando mostrando su salida en vivo; devuelve (ok, segundos, salida)."""
    titulo(nombre)
    print("$ " + " ".join(comando), flush=True)
    inicio = time.monotonic()
    proceso = subprocess.Popen(comando, cwd=cwd, env={**os.environ, **(env or {})}, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    lineas = []
    for linea in proceso.stdout:
        print(linea, end="", flush=True)
        lineas.append(linea)
    proceso.wait()
    return proceso.returncode == 0, time.monotonic() - inicio, "".join(lineas)


def resumen_pytest(salida):
    m = re.findall(r"(\d+ (?:passed|failed|error).*?) in [\d.]+s", salida)
    return m[-1] if m else "sin resumen"


def cobertura_python(salida):
    m = re.search(r"^TOTAL\s+.*?(\d+%)\s*$", salida, re.M)
    return m.group(1) if m else "—"


def resumen_vitest(salida):
    limpio = re.sub(r"\x1b\[[0-9;]*m", "", salida)
    tests = re.search(r"Tests\s+(.+?)\s*$", limpio, re.M)
    cobertura = re.search(r"Statements\s*:\s*([\d.]+%)", limpio)
    return (tests.group(1) if tests else "sin resumen"), (cobertura.group(1) if cobertura else "—")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--smoke", action="store_true", help="también el smoke contra QA (no necesita clave)")
    p.add_argument("--qa", action="store_true", help="también smoke, integración y E2E contra QA (QA_USUARIO, QA_CLAVE)")
    p.add_argument("--sin-panel", action="store_true", help="no correr los tests del panel (Vitest)")
    args = p.parse_args()

    py = sys.executable
    filas = []   # (etapa, ok, detalle, segundos)

    # 1. API
    archivos = [f"test/unitarios/{t}.py" for t in TESTS_API]
    ok, seg, salida = correr("1. API del módulo web (frontend/api): tests unitarios con cobertura",
                             [py, "-m", "pytest", "-c", "test/pytest.ini", *archivos, "-p", "no:cacheprovider",
                              "-W", "ignore::DeprecationWarning", "--cov=frontend/api", "--cov-branch",
                              "--cov-report=term"])
    filas.append(("API (pytest)", ok, f"{resumen_pytest(salida)} - cobertura {cobertura_python(salida)}", seg))

    # 2. Persistencia (opcional)
    if os.environ.get("TEST_DATABASE_URL"):
        ok, seg, salida = correr("2. Persistencia: pool de conexiones contra Postgres real",
                                 [py, "-m", "pytest", "-c", "test/pytest.ini", "test/bd/test_pool.py",
                                  "-p", "no:cacheprovider", "-v"])
        filas.append(("Persistencia (pool)", ok, resumen_pytest(salida), seg))
    else:
        filas.append(("Persistencia (pool)", None, "omitida: falta TEST_DATABASE_URL", 0))

    # 3. Panel
    if not args.sin_panel:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            filas.append(("Panel (Vitest)", False, "no se encontró npm", 0))
        else:
            if not (RAIZ / "frontend" / "node_modules").is_dir():
                correr("3a. Instalando dependencias del panel (npm ci)", [npm, "ci"], cwd=RAIZ / "frontend")
            ok, seg, salida = correr("3. Panel web (frontend/src): Vitest con cobertura",
                                     [npm, "run", "test:coverage"], cwd=RAIZ / "frontend")
            tests, cobertura = resumen_vitest(salida)
            filas.append(("Panel (Vitest)", ok, f"{tests} - cobertura {cobertura}", seg))

    # 4. Contra QA (opcional)
    if args.smoke or args.qa:
        env = {"BASE_URL": os.environ.get("BASE_URL", QA_POR_DEFECTO)}
        ok, seg, salida = correr(f"4. Smoke contra {env['BASE_URL']}",
                                 [py, "-m", "pytest", "-c", "test/pytest.ini", "test/integracion", "-m", "smoke",
                                  "-p", "no:cacheprovider", "-v"], env=env)
        filas.append(("Smoke en QA", ok, resumen_pytest(salida), seg))
    if args.qa:
        if not (os.environ.get("QA_USUARIO") and os.environ.get("QA_CLAVE")):
            filas.append(("Integración y E2E en QA", False, "faltan QA_USUARIO y QA_CLAVE", 0))
        else:
            env = {"BASE_URL": os.environ.get("BASE_URL", QA_POR_DEFECTO)}
            ok, seg, salida = correr("5. Integración contra QA",
                                     [py, "-m", "pytest", "-c", "test/pytest.ini", "test/integracion",
                                      "-m", "not smoke", "-p", "no:cacheprovider", "-v"], env=env)
            filas.append(("Integración en QA", ok, resumen_pytest(salida), seg))
            ok, seg, salida = correr("6. E2E contra QA (Playwright)",
                                     [py, "-m", "pytest", "-c", "test/pytest.ini", "test/e2e",
                                      "-p", "no:cacheprovider", "-v"], env=env)
            filas.append(("E2E en QA", ok, resumen_pytest(salida), seg))

    titulo("RESUMEN - módulo de interfaz web")
    for etapa, ok, detalle, seg in filas:
        marca = "OK   " if ok else ("--   " if ok is None else "FALLA")
        print(f"  [{marca}] {etapa:<24} {detalle}" + (f"  ({seg:.0f} s)" if seg else ""))
    fallo = any(ok is False for _, ok, _, _ in filas)
    print("\n  " + ("Hubo fallas." if fallo else "Todo en verde."))
    sys.exit(1 if fallo else 0)


if __name__ == "__main__":
    main()

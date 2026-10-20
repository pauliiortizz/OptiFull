"""Quality gate de OptiFull sobre el analisis de SonarQube Cloud.

El plan gratuito de SonarQube Cloud trae un unico quality gate fijo ("Sonar way").
Este script aplica los umbrales que pide la consigna, consultando la API de Sonar
sobre el analisis que acaba de subir el pipeline:

  - Bugs criticos (severidad BLOCKER o CRITICAL) abiertos  = 0
  - Duplicacion de lineas                                 <= 5 %
  - Cobertura sobre codigo nuevo                          >= 80 %

Escribe el resultado en el resumen de la ejecucion de GitHub Actions y en
test-results/quality-gate.json, y termina con codigo 1 (pipeline en rojo) si
alguna condicion no se cumple. El estado de "Sonar way" se informa, sin bloquear.

Uso (desde la raiz del repo, despues del scanner):
  SONAR_TOKEN=... python .github/scripts/quality_gate.py
"""
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

MAX_BUGS_CRITICOS = int(os.environ.get("QG_MAX_BUGS_CRITICOS", "0"))
MAX_DUPLICACION = float(os.environ.get("QG_MAX_DUPLICACION", "5"))
MIN_COBERTURA_NUEVA = float(os.environ.get("QG_MIN_COBERTURA_NUEVA", "80"))

REPORT_TASK = Path(os.environ.get("SONAR_REPORT_TASK", ".scannerwork/report-task.txt"))
SALIDA_JSON = Path("test-results/quality-gate.json")
ESPERA_MAX_SEG = 300


def leer_report_task(path):
    """report-task.txt lo deja el scanner: projectKey, serverUrl, ceTaskId, ..."""
    datos = {}
    for linea in path.read_text(encoding="utf-8").splitlines():
        if "=" in linea:
            k, v = linea.split("=", 1)
            datos[k.strip()] = v.strip()
    return datos


def api(server, ruta, token, **params):
    url = f"{server.rstrip('/')}{ruta}?{urllib.parse.urlencode(params)}"
    auth = base64.b64encode(f"{token}:".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def esperar_analisis(server, token, ce_task_id):
    """Sonar procesa el reporte en segundo plano: se espera a que termine."""
    limite = time.monotonic() + ESPERA_MAX_SEG
    while time.monotonic() < limite:
        tarea = api(server, "/api/ce/task", token, id=ce_task_id)["task"]
        if tarea["status"] == "SUCCESS":
            return tarea["analysisId"]
        if tarea["status"] in ("FAILED", "CANCELED"):
            raise RuntimeError(f"SonarQube Cloud no pudo procesar el analisis: {tarea['status']}")
        time.sleep(5)
    raise TimeoutError(f"El analisis no termino en {ESPERA_MAX_SEG} s")


def valor_medida(medida):
    """Las metricas de codigo nuevo vienen en 'period'/'periods', las demas en 'value'."""
    if "value" in medida:
        return float(medida["value"])
    periodo = medida.get("period") or (medida.get("periods") or [{}])[0]
    return float(periodo["value"]) if "value" in periodo else None


def obtener_medidas(server, token, proyecto):
    claves = "coverage,new_coverage,new_lines_to_cover,duplicated_lines_density,bugs,ncloc"
    resp = api(server, "/api/measures/component", token, component=proyecto, metricKeys=claves)
    return {m["metric"]: valor_medida(m) for m in resp["component"]["measures"]}


def contar_bugs_criticos(server, token, proyecto):
    resp = api(server, "/api/issues/search", token, componentKeys=proyecto, types="BUG",
               severities="BLOCKER,CRITICAL", resolved="false", ps=1)
    return int(resp["total"])


def evaluar(medidas, bugs_criticos):
    """Devuelve la lista de condiciones [(nombre, valor, umbral, ok)]."""
    duplicacion = medidas.get("duplicated_lines_density") or 0.0
    cobertura_nueva = medidas.get("new_coverage")
    hay_codigo_nuevo = (medidas.get("new_lines_to_cover") or 0) > 0
    return [
        ("Bugs criticos abiertos", f"{bugs_criticos}", f"<= {MAX_BUGS_CRITICOS}",
         bugs_criticos <= MAX_BUGS_CRITICOS),
        ("Duplicacion de lineas", f"{duplicacion:.1f} %", f"<= {MAX_DUPLICACION:g} %",
         duplicacion <= MAX_DUPLICACION),
        ("Cobertura sobre codigo nuevo",
         f"{cobertura_nueva:.1f} %" if cobertura_nueva is not None else "sin codigo nuevo",
         f">= {MIN_COBERTURA_NUEVA:g} %",
         not hay_codigo_nuevo or (cobertura_nueva or 0.0) >= MIN_COBERTURA_NUEVA),
    ]


def resumen_markdown(condiciones, medidas, sonar_way, url_proyecto):
    aprobado = all(ok for *_, ok in condiciones)
    lineas = [
        f"## Quality gate OptiFull: {'✅ APROBADO' if aprobado else '❌ RECHAZADO'}",
        "",
        "| Condicion | Valor | Umbral | Resultado |",
        "|---|---|---|---|",
        *[f"| {n} | {v} | {u} | {'✅' if ok else '❌'} |" for n, v, u, ok in condiciones],
        "",
        f"- Cobertura total (codigo existente): **{medidas.get('coverage') or 0:.1f} %**",
        f"- Lineas de codigo analizadas: {int(medidas.get('ncloc') or 0)}",
        f"- Bugs totales: {int(medidas.get('bugs') or 0)}",
        f"- Quality gate \"Sonar way\" (informativo): {sonar_way}",
        f"- Detalle: {url_proyecto}",
    ]
    return "\n".join(lineas) + "\n"


def main():
    token = os.environ.get("SONAR_TOKEN")
    if not token:
        sys.exit("Falta la variable SONAR_TOKEN")
    task = leer_report_task(REPORT_TASK)
    server, proyecto = task["serverUrl"], task["projectKey"]

    analysis_id = esperar_analisis(server, token, task["ceTaskId"])
    medidas = obtener_medidas(server, token, proyecto)
    bugs_criticos = contar_bugs_criticos(server, token, proyecto)
    sonar_way = api(server, "/api/qualitygates/project_status", token,
                    analysisId=analysis_id)["projectStatus"]["status"]

    condiciones = evaluar(medidas, bugs_criticos)
    texto = resumen_markdown(condiciones, medidas, sonar_way, task.get("dashboardUrl", server))
    print(texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(texto)

    SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_JSON.write_text(json.dumps({
        "aprobado": all(ok for *_, ok in condiciones),
        "condiciones": [{"condicion": n, "valor": v, "umbral": u, "ok": ok} for n, v, u, ok in condiciones],
        "medidas": medidas,
        "sonar_way": sonar_way,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    if not all(ok for *_, ok in condiciones):
        sys.exit(1)


if __name__ == "__main__":
    main()

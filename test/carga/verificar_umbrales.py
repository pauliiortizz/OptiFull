"""Compara los resultados de una corrida de Locust con los umbrales del perfil y frena el pipeline si no se cumplen.

Lee <prefijo>_stats.csv (totales por endpoint) y <prefijo>_stats_history.csv (evolucion segundo a segundo), que
Locust escribe con --csv <prefijo>. Escribe una tabla en el resumen de GitHub Actions (GITHUB_STEP_SUMMARY) y
<prefijo>_umbrales.json, y termina con codigo 1 si algun umbral no se cumple.

  python test/carga/verificar_umbrales.py stress test-results/carga/stress
  python test/carga/verificar_umbrales.py sostenida test-results/carga/sostenida

Umbrales (milisegundos y porcentajes). Por que estos valores, en docs/calidad/pruebas-de-carga.md:
  stress     el sistema puede degradarse, pero no caerse: errores <= 5 %, p95 <= 5 s, p99 <= 10 s
  sostenida  15 usuarios es la carga esperada de una tienda con su equipo: errores <= 1 %, p95 <= 2 s,
             p99 <= 5 s, y el p95 del ultimo tercio no puede ser mas del doble que el del primero (degradacion
             con el tiempo = memoria o conexiones que no se liberan)
"""
import csv
import json
import os
import statistics
import sys
from pathlib import Path

UMBRALES = {
    "stress": {"max_errores_pct": 5.0, "max_p95_ms": 5000, "max_p99_ms": 10000, "min_pedidos": 500},
    "sostenida": {"max_errores_pct": 1.0, "max_p95_ms": 2000, "max_p99_ms": 5000, "min_pedidos": 1500,
                  "max_degradacion_p95": 2.0},
}


def numero(texto):
    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def leer_totales(path):
    """Fila 'Aggregated' (todos los endpoints) y una fila por endpoint."""
    with open(path, newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    total = next(f for f in filas if f["Name"] == "Aggregated")
    return total, [f for f in filas if f["Name"] != "Aggregated"]


def degradacion_p95(path_historia):
    """p95 mediano del ultimo tercio de la corrida dividido el del primer tercio (sin el arranque)."""
    with open(path_historia, newline="", encoding="utf-8") as f:
        p95 = [numero(f["95%"]) for f in csv.DictReader(f) if f["Name"] == "Aggregated"]
    p95 = [v for v in p95 if v]
    if len(p95) < 30:
        return None
    p95 = p95[len(p95) // 10:]   # el primer 10 % es el arranque: los logins de cada usuario inflan el p95
    tercio = len(p95) // 3
    inicio, fin = statistics.median(p95[:tercio]), statistics.median(p95[-tercio:])
    return fin / inicio if inicio else None


def evaluar(perfil, prefijo):
    u = UMBRALES[perfil]
    total, endpoints = leer_totales(f"{prefijo}_stats.csv")
    pedidos = int(total["Request Count"])
    errores_pct = 100 * int(total["Failure Count"]) / pedidos if pedidos else 100.0
    medidas = {
        "pedidos": pedidos,
        "errores_pct": round(errores_pct, 2),
        "p50_ms": numero(total["50%"]),
        "p95_ms": numero(total["95%"]),
        "p99_ms": numero(total["99%"]),
        "pedidos_por_seg": round(numero(total["Requests/s"]) or 0, 2),
    }
    chequeos = [
        ("Pedidos realizados", medidas["pedidos"], f">= {u['min_pedidos']}", pedidos >= u["min_pedidos"]),
        ("Errores (%)", medidas["errores_pct"], f"<= {u['max_errores_pct']}", errores_pct <= u["max_errores_pct"]),
        ("p95 (ms)", medidas["p95_ms"], f"<= {u['max_p95_ms']}", (medidas["p95_ms"] or 0) <= u["max_p95_ms"]),
        ("p99 (ms)", medidas["p99_ms"], f"<= {u['max_p99_ms']}", (medidas["p99_ms"] or 0) <= u["max_p99_ms"]),
    ]
    if "max_degradacion_p95" in u:
        d = degradacion_p95(f"{prefijo}_stats_history.csv")
        medidas["degradacion_p95"] = round(d, 2) if d else None
        chequeos.append(("p95 final / p95 inicial", medidas["degradacion_p95"], f"<= {u['max_degradacion_p95']}",
                         d is not None and d <= u["max_degradacion_p95"]))
    return medidas, chequeos, endpoints


def resumen_markdown(perfil, medidas, chequeos, endpoints):
    lineas = [f"## Carga: perfil `{perfil}`", "", "| Umbral | Medido | Exigido | |", "|---|---|---|---|"]
    lineas += [f"| {n} | {v} | {e} | {'✅' if ok else '❌'} |" for n, v, e, ok in chequeos]
    lineas += ["", f"{medidas['pedidos_por_seg']} pedidos/s, mediana {medidas['p50_ms']} ms.", "",
               "| Endpoint | Pedidos | Fallas | p50 ms | p95 ms | p99 ms |", "|---|---|---|---|---|---|"]
    lineas += [f"| {e['Name']} | {e['Request Count']} | {e['Failure Count']} | {e['50%']} | {e['95%']} | {e['99%']} |"
               for e in endpoints]
    return "\n".join(lineas) + "\n"


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in UMBRALES:
        sys.exit(f"Uso: {sys.argv[0]} {{{'|'.join(UMBRALES)}}} <prefijo de --csv de Locust>")
    perfil, prefijo = sys.argv[1], sys.argv[2]
    medidas, chequeos, endpoints = evaluar(perfil, prefijo)
    texto = resumen_markdown(perfil, medidas, chequeos, endpoints)
    sys.stdout.reconfigure(encoding="utf-8")   # la consola de Windows no imprime los ✅/❌ con su codificacion
    print(texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(texto)
    cumple = all(ok for *_, ok in chequeos)
    Path(f"{prefijo}_umbrales.json").write_text(json.dumps(
        {"perfil": perfil, "cumple": cumple, "medidas": medidas, "umbrales": UMBRALES[perfil]}, indent=2),
        encoding="utf-8")
    if not cumple:
        print(f"::error::La prueba de carga '{perfil}' no cumple los umbrales")
        sys.exit(1)


if __name__ == "__main__":
    main()

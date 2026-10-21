# Alcance de la medición de calidad

El TP de Calidad de Software se enfoca en el **módulo de interfaz web** de OptiFull, `frontend/`: el backend web
(API Flask, módulo 6 del informe de la tesis) y el panel React (módulo 7). Es la parte del sistema que usa el
personal del local, la que se despliega en Render (QA y producción) y la que se conecta con los sistemas externos
(Supabase, Render).

Los otros dos procesos de OptiFull, el pipeline de video (`deteccion/`) y el de caja (`deteccion_productos/`),
siguen teniendo sus tests y corren en el mismo pipeline (si fallan, el pipeline frena), pero **no se miden**: no
entran en la cobertura, en SonarQube Cloud ni en el quality gate.

La configuración que aplica este alcance está en:

- `pyproject.toml`: cobertura de Python (`[tool.coverage]`, `omit`).
- `sonar-project.properties`: SonarQube Cloud (`sonar.sources`).
- `.github/workflows/pipeline.yml`: el reporte de complejidad y estilo de Ruff recorre `frontend/`.

## Qué se mide

| Carpeta | Qué es | Se mide |
|---|---|---|
| `frontend/api/` | Backend web: API Flask desplegada en Render (QA y producción) | ✅ |
| `frontend/src/` | Panel web React (dashboard, reportes, alertas, caja web, landing, login) | ✅ |

## Qué no se mide y por qué

| Carpeta / archivo | Motivo |
|---|---|
| `deteccion/` | Pipeline de video (YOLO, tracking, Re-ID, heatmaps). Fuera del alcance del TP; sus tests corren igual. |
| `deteccion_productos/` | Pipeline de caja (reconocimiento de productos). Fuera del alcance del TP; sus tests corren igual. |
| `frontend/serve_dashboard.py` | Script para levantar el sistema en desarrollo. En el despliegue se usa `gunicorn`. |
| `test/`, `frontend/src/**/*.test.*` | Son los propios tests: se analizan como tests, no como código a cubrir. |
| `db/`, `docker/`, `.github/` | Infraestructura: esquema de base de datos, imagen Docker y pipeline. |
| `.agents/`, `.aider-desk/`, `.claude/` | Skills de herramientas de IA que usa el equipo. No son código del producto. |

## Cómo se mide

- **Cobertura de Python:** sentencia y decisión (`branch = true`), con `pytest-cov`.
- **Cobertura del frontend:** Vitest con V8 (`npm run test:coverage`), reporte LCOV.
- **Análisis estático:** Ruff en cada push (bloquea por errores probables: reglas `E9`, `F` y `B`, en todo el
  repositorio) y SonarQube Cloud en cada push a `main` (solo `frontend/`).
- **Quality gate** (`.github/scripts/quality_gate.py`): frena el pipeline si hay bugs críticos abiertos, si la
  duplicación supera el 5 % o si la cobertura sobre código nuevo es menor al 80 %.

## Evolución del módulo web

La línea base es el commit ef77d4e (20/10/2026), cuando se incorporaron el análisis estático y el quality gate,
antes de escribir los tests. Las dos columnas se midieron igual: pipeline (Python 3.12, Postgres de prueba) y
`ruff check frontend`.

| Medida | Línea base (ef77d4e) | 21/10/2026 |
|---|---|---|
| Tests de Python del módulo web (API) | — (la API casi no tenía tests) | 441, todos pasan |
| Tests del frontend | 7 (solo `permisos.test.js`) | 367, todos pasan |
| Cobertura de la API (sentencia + decisión) | 26 % | 98 % |
| Cobertura del frontend (sentencias / ramas) | solo `permisos.js` | 92,7 % / 87,9 % |
| Observaciones de Ruff que bloquean | 0 | 0 |
| Observaciones de complejidad y estilo (no bloquean) | 107 | 118 |
| Funciones con complejidad > 10 | 7 | 8 |
| Función más compleja | `generar_pdf()` (`reportes_formatos.py`), 21 | la misma, 21 |
| Defectos encontrados y corregidos | — | 20 (ver [defectos.md](defectos.md)) |
| Stress de 40 usuarios en QA, p95 | 7600 ms | 2400 ms (ver [pruebas-de-carga.md](pruebas-de-carga.md)) |

**Lectura.** La cobertura y la cantidad de defectos encontrados cambiaron mucho; la complejidad no. Las
funciones complejas del módulo web (los generadores de PDF y Excel de los reportes, los tramos del plano de
calor) ya existían y tienen tests que cubren sus ramas, pero no se refactorizaron. La que se sumó a la lista es
`session_clip()` (`video.py`, 13): subió con las validaciones de `t` y `dur` que corrigieron DEF-005 a DEF-007, un
caso en el que se aceptó más complejidad a cambio de no responder 500. Las observaciones de estilo suben con el
código nuevo (el pool de conexiones, las validaciones de seguridad, el aviso por email). La mejora medida antes y
después del módulo web es la de desempeño: el pool de conexiones a Supabase.

## SonarQube Cloud en `main`

Hasta el 21/10/2026, SonarQube Cloud medía todo el repositorio. Desde el primer análisis con el alcance nuevo,
mide solo `frontend/`: los números de abajo no son comparables con esos análisis anteriores.

Último análisis con el alcance anterior (876f0cb, 21/10, la primera ejecución completa del pipeline en verde,
[39657822881](https://github.com/pauliiortizz/OptiFull/actions/runs/39657822881)): gate OK, cobertura 94,6 %,
86,0 % sobre código nuevo, duplicación 0,8 %, 0 bugs críticos.

En ese período `main` pasó por un quality gate en rojo (67935ce, 20/10): el código nuevo de la landing y los
gráficos (módulo web) llegó sin tests y la cobertura sobre código nuevo bajó a 73 %. Volvió a pasar cuando
entraron los tests de `Pau` (ba9b344).

Los números con el alcance del módulo web se completan con el primer análisis de `main` después de este cambio.

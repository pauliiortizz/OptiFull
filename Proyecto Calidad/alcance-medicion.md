# Alcance de la medición de calidad

**Qué se prueba y se mide:** todo OptiFull. El pipeline corre los tests de los tres procesos del sistema y
SonarQube Cloud, la cobertura y el quality gate miden todo el código del producto (tabla de abajo).

**En qué se enfoca el TP:** el **módulo de interfaz web**, `frontend/`, formado por el backend web (API Flask,
módulo 6 del informe de la tesis) y el panel React (módulo 7). Es la parte del sistema que usa el personal del
local, la que se despliega en Render (QA y producción) y la que se conecta con los sistemas externos (Supabase,
Render). Los números del TP son los de la carpeta `frontend/` dentro de esos mismos reportes, así que coinciden
con el pipeline y con SonarQube Cloud:

- **SonarQube Cloud:** pestaña *Code* (o *Measures*) del proyecto, carpeta `frontend` (y `frontend/api`,
  `frontend/src`).
- **Cobertura de Python:** las filas `frontend/api/*` del reporte del job build-test.
- **Cobertura del panel:** el reporte de Vitest del mismo job (es todo del módulo web).

Los pipelines de video (`deteccion/`) y de caja (`deteccion_productos/`) siguen con sus tests y su medición, pero
sus resultados no forman parte del TP.

La configuración de la medición está en `pyproject.toml` (Ruff y `[tool.coverage]`) y en
`sonar-project.properties`.

## Qué se mide

| Carpeta | Qué es | Se mide | En el TP |
|---|---|---|---|
| `frontend/api/` | Backend web: API Flask desplegada en Render (QA y producción) | ✅ | ✅ |
| `frontend/src/` | Panel web React (dashboard, reportes, alertas, caja web, landing, login) | ✅ | ✅ |
| `deteccion/` | Pipeline de video: YOLO, tracking, Re-ID, heatmaps, persistencia | ✅ (incluido `main.py`) | — |
| `deteccion_productos/` | Pipeline de caja: reconocimiento de productos | ✅ | — |

## Qué no se mide y por qué

| Carpeta / archivo | Motivo |
|---|---|
| `deteccion/mantenimiento/` | Scripts de corrección de datos que se ejecutan una sola vez a mano. No forman parte del flujo del sistema. |
| `deteccion_productos/test_*.py` | Scripts de prueba manuales (se corren con `python test_x.py`). No son código del producto. |
| `frontend/serve_dashboard.py` | Script para levantar el sistema en desarrollo. En el despliegue se usa `gunicorn`. |
| `test/`, `frontend/src/**/*.test.*` | Son los propios tests: se analizan como tests, no como código a cubrir. |
| `db/`, `docker/`, `.github/` | Infraestructura: esquema de base de datos, imagen Docker y pipeline. |
| `.agents/`, `.aider-desk/`, `.claude/` | Skills de herramientas de IA que usa el equipo. No son código del producto. |
| `ultralytics` | Librería de terceros (YOLO). Se instala con pip, no está copiada en el repo. |

## Cómo se mide

- **Cobertura de Python:** sentencia y decisión (`branch = true`), con `pytest-cov`.
- **Cobertura del frontend:** Vitest con V8 (`npm run test:coverage`), reporte LCOV.
- **Análisis estático:** Ruff en cada push (bloquea por errores probables: reglas `E9`, `F` y `B`) y SonarQube
  Cloud en cada push a `main`.
- **Quality gate** (`.github/scripts/quality_gate.py`): frena el pipeline si hay bugs críticos abiertos, si la
  duplicación supera el 5 % o si la cobertura sobre código nuevo es menor al 80 %. Se aplica al proyecto entero,
  así que también vale para el módulo web.

## Evolución del módulo web

La línea base es el commit ef77d4e (20/10/2026), cuando se incorporaron el análisis estático y el quality gate,
antes de escribir los tests. Las dos columnas se midieron igual: pipeline (Python 3.12, Postgres de prueba) y
`ruff check frontend` (el reporte del pipeline recorre todo el repositorio; acá se filtra el módulo web).

| Medida | Línea base (ef77d4e) | 21/10/2026 |
|---|---|---|
| Tests de Python del módulo web (API) | — (la API casi no tenía tests) | 435, todos pasan |
| Tests del frontend | 7 (solo `permisos.test.js`) | 382, todos pasan |
| Cobertura de la API (sentencia + decisión) | 26 % | 98 % (SonarQube Cloud: 98,0 %) |
| Cobertura del frontend (sentencias / ramas, Vitest) | solo `permisos.js` | 92,7 % / 87,9 % (SonarQube Cloud: 91,6 %, que combina líneas y ramas) |
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

Análisis del commit e540c94 (21/10/2026). El quality gate se evalúa sobre el proyecto entero; las columnas del
módulo web son las de la carpeta `frontend/` del mismo análisis.

| Medida | Proyecto entero | Módulo web (`frontend/`) | `frontend/api` | `frontend/src` |
|---|---|---|---|---|
| Quality gate de OptiFull | OK | — | — | — |
| Cobertura (sentencia + decisión) | 94,6 % | 94,5 % | 98,0 % | 91,6 % |
| Cobertura de líneas / de ramas | — | 96,8 % / 90,2 % | 98,5 % / 96,0 % | 94,7 % / 87,9 % |
| Duplicación | 0,8 % | 1,0 % | 2,7 % | 0,0 % |
| Bugs abiertos (críticos) | 14 (0) | 13 (0) | 0 | 13 (0) |
| Vulnerabilidades abiertas | 0 | 0 | 0 | 0 |
| Líneas de código | 15 415 | 10 451 | 3 529 | 6 922 |

Los 13 bugs del módulo web son del panel (`frontend/src`) y ninguno es crítico: elementos con `onClick` sin manejo
de teclado, una promesa sin `.catch` y una propiedad CSS duplicada. Las 10 vulnerabilidades que había se
revisaron el 21/10: 5 se corrigieron (DEF-023 a DEF-026) y 5 quedaron marcadas con su justificación (ver
[defectos.md](defectos.md)).

Antes de eso, `main` pasó por un quality gate en rojo (67935ce, 20/10): el código nuevo de la landing y los
gráficos (módulo web) llegó sin tests y la cobertura sobre código nuevo bajó a 73 %. Volvió a pasar cuando
entraron los tests de `Pau` (ba9b344). Es una de las ejecuciones fallidas del módulo web que detectaron un
problema real; la otra es el stress en rojo de [39643083288](https://github.com/pauliiortizz/OptiFull/actions/runs/39643083288)
(ver [pruebas-de-carga.md](pruebas-de-carga.md)).

Primera ejecución completa del pipeline en verde: [39657822881](https://github.com/pauliiortizz/OptiFull/actions/runs/39657822881)
(876f0cb).

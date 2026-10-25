# Proyecto Calidad · TP Integrador de Calidad de Software

Trabajo práctico integrador de la materia Calidad de Software (Mag. Pablo Virgolini), aplicado al TFG
**OptiFull**. Es un proyecto aparte de la tesis: todo lo del TP está en esta carpeta, y el código de la tesis no se
modifica para el TP.

| | |
|---|---|
| **Nivel declarado** | Nivel 3, prototipo avanzado: el sistema está desplegado en Render (QA y producción), usa Supabase como base de datos en la nube y el flujo principal funciona de punta a punta. |
| **Módulo** | **Interfaz web** de OptiFull, `frontend/`: el backend web (API Flask, módulo 6 del informe de la tesis) y el panel React (módulo 7). |
| **Integración externa** | Supabase (Postgres y Storage) y Render (hosting de QA y producción). Ver [integracion-externa.md](integracion-externa.md). |
| **Fecha de entrega** | 26/10/2026 |

## Por qué el módulo de interfaz web

Es la única parte de OptiFull expuesta a internet, la que usa el personal del local todos los días y la que se
conecta con los sistemas externos. Los otros dos procesos de la tesis (el pipeline de video y el de caja) se
siguen probando y midiendo en el mismo pipeline, pero no forman parte del TP.

## Índice: un documento por eje de la consigna

| # | Eje | Documento |
|---|---|---|
| 1 | Introducción a la calidad | [01-introduccion-calidad.md](01-introduccion-calidad.md): objetivos de calidad del usuario, el equipo y la organización; plan de contingencia |
| 2 | Fundamentos del testing | [02-fundamentos-testing.md](02-fundamentos-testing.md): pruebas en AAA, criterio de aceptación previo, defectos rojo/verde, los siete principios |
| 3 | Modelos de calidad y niveles de prueba | [03-modelos-calidad-y-niveles.md](03-modelos-calidad-y-niveles.md): matriz ISO/IEC 25010, top 3, mapa de niveles, despliegue verificado |
| 4 | Métricas y análisis estático | [04-metricas-y-analisis-estatico.md](04-metricas-y-analisis-estatico.md): métricas interpretadas, de proceso y de proyecto, hallazgos, flujo de control, mejora medida |
| 5 | Pruebas dinámicas | [05-pruebas-dinamicas.md](05-pruebas-dinamicas.md): casos con clases de equivalencia, valores límite, tabla de decisión y transición de estados; cobertura |
| 6 | Aseguramiento de la calidad | [06-aseguramiento-calidad.md](06-aseguramiento-calidad.md) y [plan-de-pruebas.md](plan-de-pruebas.md): plan, riesgos, QA y QC, plantillas |
| 7 | Automatización del testing | [07-automatizacion.md](07-automatizacion.md): pirámide, API e integración, smoke, pipeline, regresión |
| 8 | Herramientas del ecosistema | [08-herramientas.md](08-herramientas.md): mapa de herramientas, SonarCloud con los cinco pasos, Jira, stress |
| — | Documentación y análisis (transversal) | Este README, [metas-nivel-3.md](metas-nivel-3.md) y [uso-de-ia.md](uso-de-ia.md) |

Documentos de apoyo: [alcance-medicion.md](alcance-medicion.md) · [defectos.md](defectos.md) (y
[defectos-jira.csv](defectos-jira.csv)) · [plantillas.md](plantillas.md) ·
[pruebas-de-carga.md](pruebas-de-carga.md) · [herramienta-sonarcloud.md](herramienta-sonarcloud.md).

## Entregables de la consigna

| Entregable | Dónde está |
|---|---|
| Plan de pruebas versionado, con la matriz ISO 25010 y la trazabilidad | [plan-de-pruebas.md](plan-de-pruebas.md) (tabla de versiones al principio) y [03-modelos-calidad-y-niveles.md](03-modelos-calidad-y-niveles.md) |
| Código de las pruebas (unitarias, integración, smoke, stress y esfuerzo), ejecutables con un comando | `test/unitarios`, `test/bd`, `test/integracion`, `test/e2e`, `test/carga` y `frontend/src/**/*.test.*`. Comandos en [07-automatizacion.md](07-automatizacion.md#un-comando-por-nivel) |
| Pipeline de CI como archivo de configuración, con una ejecución completa en verde y una fallida que detectó un problema real | `.github/workflows/pipeline.yml`. En verde: [39657822881](https://github.com/pauliiortizz/OptiFull/actions/runs/39657822881). Fallidas: [39643083288](https://github.com/pauliiortizz/OptiFull/actions/runs/39643083288) (stress: la API abría una conexión por pedido) y [39495492793](https://github.com/pauliiortizz/OptiFull/actions/runs/39495492793) (quality gate: código nuevo del panel sin tests) |
| Reportes automáticos de cobertura, análisis estático y stress generados por el pipeline | Resumen y artefactos de cada ejecución (`test-results`, `quality-gate`, `carga-qa`) y [SonarQube Cloud](https://sonarcloud.io/project/overview?id=pauliiortizz_OptiFull) |
| Documentación de la integración externa | [integracion-externa.md](integracion-externa.md) |
| Registro de defectos con los datos completos | [defectos.md](defectos.md) y Jira, proyecto [KAN](https://optifull.atlassian.net/issues?jql=project%3DKAN%20ORDER%20BY%20key%20ASC) |
| Documento de la herramienta incorporada y la matriz de decisión | [herramienta-sonarcloud.md](herramienta-sonarcloud.md) |
| Informe en PDF | Se arma a partir de estos documentos (nivel, metas, evolución de métricas, análisis crítico y conclusiones) |
| Demostración con un despliegue nuevo | Un push a `main` dispara el pipeline completo: build-test → quality gate → system-check → deploy a QA → smoke e integración → E2E → carga → deploy a producción + smoke |

## Cómo correr todo

**Para la demostración delante del docente:** `python "Proyecto Calidad/pruebas/correr_pruebas_web.py"` corre solo
las pruebas del módulo web (431 de la API y 367 del panel) y muestra un resumen. Guía completa, con el rojo/verde
de un defecto y cómo lanzar un despliegue nuevo: [pruebas/README.md](pruebas/README.md).

Cada nivel por separado:

Desde la raíz del repositorio:

```
pip install -r test/requirements.txt                                        # dependencias de las pruebas
pytest -c test/pytest.ini test/unitarios                                    # unitarios de la API (y del resto del sistema)
cd frontend && npm ci && npm run test:coverage                              # panel web, con cobertura
TEST_DATABASE_URL=postgresql://... pytest -c test/pytest.ini test/bd/test_pool.py   # persistencia de la API
BASE_URL=https://optifull-qa.onrender.com QA_USUARIO=... QA_CLAVE=... pytest -c test/pytest.ini test/integracion
BASE_URL=... QA_USUARIO=... QA_CLAVE=... pytest -c test/pytest.ini test/e2e
CARGA_PERFIL=stress locust -f test/carga/locustfile.py --headless --host $BASE_URL --csv test-results/carga/stress
```

Las pruebas que van contra QA necesitan `pip install -r test/requirements-qa.txt` y, para el E2E,
`python -m playwright install chromium`.

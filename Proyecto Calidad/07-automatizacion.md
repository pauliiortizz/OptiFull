# 7 · Automatización del testing

## Pirámide de pruebas automatizadas del módulo web

```
                        ┌───────────────────────────┐
                        │  Carga: 2 perfiles        │  Locust, contra QA
                        ├───────────────────────────┤
                        │  E2E: 2                   │  Playwright + Chromium, contra QA
                    ┌───┴───────────────────────────┴───┐
                    │  API e integración: 22            │  pytest + requests contra el contenedor y QA
                    │  (12 integración + 10 del pool)   │  (incluye 4 de smoke) y Postgres real
            ┌───────┴───────────────────────────────────┴───────┐
            │  Unitarias y de componentes: 798                  │  pytest (API) y Vitest (panel),
            │  (431 de la API + 367 del panel)                  │  con dobles de prueba
            └───────────────────────────────────────────────────┘
```

Cuanto más abajo, más rápidas y baratas: las 798 de la base corren en menos de un minuto en cada push a la rama de
trabajo; las de arriba dependen de Render y de Supabase, y con ellas el pipeline completo tarda unos 34 minutos
(media de las ejecuciones en verde de `main`): por eso corren solo en `main`.

## Pruebas de API e integración con la plataforma externa

Las pruebas de API se hacen con pytest y `requests` (cumplen el papel que en la clase cumplió Postman con
Newman): le pegan por HTTP a la API, como caja negra, y comparan el código de estado y el JSON.

| Prueba | Contra qué | Qué verifica |
|---|---|---|
| `test/integracion/` en system-check | La imagen Docker del módulo, conectada a la base de QA en **Supabase** | Que la imagen que se va a desplegar arranca, se conecta y responde: login, sesión, stats, personas, alertas, reportes, export CSV |
| `test/integracion/` en integration-qa | El módulo desplegado en **Render** (QA), con **Supabase** | Lo mismo, ahora en la plataforma real, y que corre el commit esperado |
| `test/bd/test_pool.py` | Un Postgres 16 real (el mismo motor que Supabase) | Que el pool de conexiones reutiliza, descarta las rotas y no deja transacciones a medias |
| `test/e2e/` | QA en Render con Supabase, con un navegador | El recorrido de un usuario de punta a punta |

Detalle de cada integración, sus datos y sus límites en [integracion-externa.md](integracion-externa.md).

## Smoke en cada despliegue

`pytest -m smoke` son 4 pruebas: el servicio está vivo y con base (`/api/health`), corre el commit esperado, sirve
el frontend y la API exige sesión. Corren:

- **Después del deploy a QA**, antes que el resto de las pruebas de QA (si el smoke falla, no tiene sentido seguir).
- **Después del deploy a producción**, como única prueba (no escriben nada).

## Pipeline de CI/CD

Archivo: `.github/workflows/pipeline.yml`. Primero lo rápido y barato, después lo lento y costoso:

```
 push a Pau ───────► build-test ─► (fin: 1,6 min de media)

 push a main ──────► build-test ─► calidad ─► system-check ─► deploy-qa ─► integration-qa ─► e2e-qa ─► carga-qa ─► deploy-prod
                     │             │          │               │            │                 │         │           │
                     compila,      SonarQube  BD de QA +      Render,      smoke +           Playwright Locust:    Render +
                     Ruff,         Cloud +    contenedor +    espera el    integración                 stress y    smoke
                     tests +       quality    integración     commit                                   sostenida
                     cobertura     gate
```

Si una etapa falla, el pipeline se corta ahí y no se despliega lo que sigue. Ejecución completa en verde:
[39657822881](https://github.com/pauliiortizz/OptiFull/actions/runs/39657822881). Ejecución fallida que detectó un
problema real: [39643083288](https://github.com/pauliiortizz/OptiFull/actions/runs/39643083288) (el stress mostró
que la API abría una conexión por pedido).

**Reportes que deja cada ejecución:** resumen con la cobertura de Python, el reporte de Ruff, el quality gate y las
tablas de carga; artefactos `test-results` (cobertura XML y LCOV, resultados JUnit), `quality-gate`, `e2e-qa`
(capturas y trazas de Playwright) y `carga-qa` (reportes HTML de Locust con sus gráficos y los CSV).

## Una prueba de regresión por cada defecto corregido

| Defecto | Test de regresión |
|---|---|
| DEF-001 | `test_reportes_formatos.py` (genera los PDF con tablas con la versión de fpdf2 que instala el CI) |
| DEF-002 | `test_heatmap.py::test_no_sirve_archivos_que_no_son_imagenes_de_heatmap` |
| DEF-003 | `test_heatmap.py::test_sin_base_de_datos_responde_503` |
| DEF-004 | `test_sesion.py` y el smoke `test_la_api_exige_sesion` |
| DEF-005, 006, 007 | `test_video.py` (Range de sufijo, Range más largo que el archivo, parámetros del clip) |
| DEF-008 | `test_api_basica.py::test_exportar_con_la_base_vacia_genera_el_reporte_sin_filas` |
| DEF-015 | `App.test.jsx` › "un error 500 de congestion-horaria no deja el panel en blanco" |
| DEF-016, 017 | `LandingPage.test.jsx` |
| DEF-018 | `Sidebar.test.jsx` |
| DEF-020 | `seguir.test.js` › "DEF-020: sin Web Animations no hace nada y no tira error" |
| DEF-021 | `ReportMetrics.test.jsx` › "conversión con un solo día usa singular" |
| DEF-022 | `LandingPage.test.jsx` › "sin conexión avisa que no se pudo enviar" |
| DEF-023 a 027 | `test_seguridad.py::test_def023_*` a `test_def027_*` |

Las 20 corren en cada push.

## Punto de equilibrio

Estimación para la regresión del módulo antes de cada deploy:

- **A mano:** recorrer el panel con los dos roles, exportar un reporte, probar los endpoints principales con un
  cliente HTTP y repetir los casos de los 20 defectos: unas 4 h por deploy.
- **Automatizada:** escribir las suites llevó unas 40 h; mantenerlas, unos 30 min por deploy (revisar una falla,
  ajustar un test a un cambio visual, como pasó con el rediseño de `main`).
- **Equilibrio:** 40 ÷ (4 − 0,5) ≈ **11,4 deploys**. Entre el 20 y el 21/10 el pipeline de `main` corrió 9 veces y
  el de la rama de trabajo 41: la inversión se pagó en la primera semana.

## Lo que no se automatiza

| Qué | Por qué |
|---|---|
| Usabilidad del panel para el personal del local | Requiere criterio humano: se valida a mano, mostrando el panel |
| Pruebas exploratorias de pantallas nuevas | Un guion fijo las anula; se hacen antes de escribir el test |
| La validación de los datos reales contra lo que pasó en el local | Necesita a alguien que estuvo ahí |

### Un comando por nivel

```
pytest -c test/pytest.ini test/unitarios                                   # unitarios (incluye los de la API)
cd frontend && npm test                                                    # panel web
TEST_DATABASE_URL=postgresql://... pytest -c test/pytest.ini test/bd/test_pool.py   # persistencia
BASE_URL=... QA_USUARIO=... QA_CLAVE=... pytest -c test/pytest.ini test/integracion   # integración (-m smoke: smoke)
BASE_URL=... QA_USUARIO=... QA_CLAVE=... pytest -c test/pytest.ini test/e2e           # E2E
CARGA_PERFIL=stress locust -f test/carga/locustfile.py --headless --host $BASE_URL --csv test-results/carga/stress
CARGA_PERFIL=sostenida locust -f test/carga/locustfile.py --headless --host $BASE_URL --csv test-results/carga/sostenida
```

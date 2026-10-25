# Plan de pruebas del módulo de interfaz web de OptiFull

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0 | 20/10/2026 | Primera versión: alcance, niveles, criterios, riesgos, ISO/IEC 25010 y trazabilidad |
| 1.1 | 21/10/2026 | Merge de `main` en `Pau`: DEF-020 a DEF-022 en la trazabilidad y riesgo de merge |
| 1.2 | 21/10/2026 | Revisión de las vulnerabilidades de SonarQube Cloud: DEF-023 a DEF-027 |
| 2.0 | 21/10/2026 | El TP se enfoca en el módulo de interfaz web (`frontend/`): pirámide, riesgos, ISO 25010, tabla de decisión y trazabilidad reescritos para ese módulo |
| 2.1 | 21/10/2026 | La medición sigue cubriendo todo el sistema; los números del TP son los de `frontend/` en esos mismos reportes |
| 3.0 | 21/10/2026 | Pasa a `Proyecto Calidad/` como parte del TP. Riesgo R9 (pedidos de demo en el disco de Render) y riesgos de proyecto ; la matriz ISO 25010 pasa a [03-modelos-calidad-y-niveles.md](03-modelos-calidad-y-niveles.md) |

Este documento está versionado junto con el código: cada cambio de alcance, criterio o umbral se hace en el
mismo commit que el cambio en las pruebas o en el pipeline, y se agrega una fila a la tabla de arriba.

Documentos relacionados: [alcance de la medición](alcance-medicion.md) · [registro de defectos](defectos.md) ·
[plantillas](plantillas.md) · [pruebas de carga](pruebas-de-carga.md) ·
[herramienta incorporada](herramienta-sonarcloud.md) · [aseguramiento de la calidad](06-aseguramiento-calidad.md) ·
pipeline en `.github/workflows/pipeline.yml`.

## 1. Objetivo y alcance

Verificar en cada cambio, de forma automática y antes de que llegue a producción, que el **módulo de interfaz web**
de OptiFull cumple los requisitos de la tesis que le corresponden (sección 8).

**Entra** (`frontend/`, módulos 6 y 7 del informe de la tesis):
- El **backend web** (`frontend/api/`): la API Flask que expone los datos de los pipelines, el login y la sesión,
  los reportes, las alertas, los mapas de calor, los videos y el control de la caja.
- El **panel web** (`frontend/src/`): dashboard, reportes, alertas, caja web, configuración, landing y login.
- Su **despliegue** en Render (QA y producción) y sus **integraciones externas**: Supabase (Postgres y Storage) y
  Render.

**No entra:** el pipeline de video (`deteccion/`) y el de caja (`deteccion_productos/`). Se siguen probando y
midiendo en el mismo pipeline (lo frenan si fallan), pero no forman parte de este plan: el TP reporta los números
del módulo web dentro de esos mismos reportes (ver [alcance-medicion.md](alcance-medicion.md)). Para el módulo
web son productores de datos: escriben en la base que la API lee.

## 2. Niveles de prueba y pirámide

| Nivel | Qué prueba | Dónde | Herramienta | Cantidad | Cuándo corre |
|---|---|---|---|---|---|
| Unitario de la API | Endpoints y funciones aislados; base de datos, procesos y HTTP con dobles de prueba | `test/unitarios/` (archivos de la API) | pytest | 435 | Cada push y PR (build-test) |
| Unitario y de componentes del panel | Componentes React con Testing Library, `fetch` simulado | `frontend/src/**/*.test.*` | Vitest + jsdom | 382 | Cada push y PR (build-test) |
| Persistencia | El pool de conexiones de la API contra un Postgres real | `test/bd/test_pool.py` | pytest + Postgres 16 | 10 | Cada push y PR (build-test) |
| Integración de sistema | La imagen Docker del módulo web contra la base de QA | `test/integracion/` | pytest + requests | 12 | Push a `main` (system-check) |
| Smoke | Lo mínimo de un despliegue: vivo, con base, commit esperado, frontend servido, API con sesión | `test/integracion/` (`-m smoke`) | pytest | 4 | Tras el deploy a QA y a producción |
| Integración en QA | La API desplegada en Render con Supabase | `test/integracion/` | pytest + requests | 8 | Tras el deploy a QA |
| E2E | El recorrido de un usuario según su rol, con un navegador real | `test/e2e/` | Playwright + Chromium | 2 | Tras el deploy a QA |
| Carga | Stress y esfuerzo sostenido con umbrales | `test/carga/` | Locust | 2 perfiles | Tras el E2E en QA |

Archivos de la API en `test/unitarios/`: `test_api_basica`, `test_calcular_stats`, `test_export`, `test_health`,
`test_heatmap`, `test_leads`, `test_login`, `test_plano_calor`, `test_productos`, `test_rango_fechas`,
`test_reportes`, `test_reportes_datos`, `test_reportes_export`, `test_reportes_formatos`, `test_seguridad`,
`test_sesion` y `test_video`.

La base es ancha a propósito: las 808 pruebas unitarias del módulo corren en menos de un minuto y dan el
diagnóstico más preciso; las de arriba son pocas, lentas y dependen de Render y de Supabase, por eso prueban
recorridos y no casos. Cada defecto corregido suma un test de regresión en el nivel más bajo que lo reproduce.

Un comando por nivel (desde la raíz del repo):

```
pytest -c test/pytest.ini test/unitarios                                   # unitarios (incluye los de la API)
cd frontend && npm test                                                    # panel web
TEST_DATABASE_URL=postgresql://... pytest -c test/pytest.ini test/bd/test_pool.py   # persistencia
BASE_URL=... QA_USUARIO=... QA_CLAVE=... pytest -c test/pytest.ini test/integracion   # integración (-m smoke: smoke)
BASE_URL=... QA_USUARIO=... QA_CLAVE=... pytest -c test/pytest.ini test/e2e           # E2E
CARGA_PERFIL=stress locust -f test/carga/locustfile.py --headless --host $BASE_URL --csv test-results/carga/stress
```

## 3. Entornos y datos

| Entorno | Para qué | Datos |
|---|---|---|
| Local / CI build-test | Unitarias y persistencia | Dobles de prueba; Postgres temporal vacío por test (nunca Supabase) |
| Contenedor en CI (system-check) | Integración del módulo empaquetado | Base de QA en Supabase, solo lectura |
| QA en Render (`optifull-qa`) | Smoke, integración, E2E, carga | Base de QA en Supabase; cuenta `QA_USUARIO` (rol empleado) creada con `db/crear_usuario.py` |
| Producción en Render (`optifull-prod`) | Solo smoke (no escribe nada) | Datos reales |

## 4. Criterios

### Entrada (para empezar a probar un cambio)
- El backend compila (`compileall`) y Ruff no tiene observaciones bloqueantes (`E9`, `F`, `B`).
- Las dependencias se instalan de cero desde los `requirements`: así se detectan versiones que rompen algo, como
  la de fpdf2 (DEF-001).
- Para los niveles en QA: el deploy terminó y `/api/health` responde con el commit que se está probando.

### Salida (para desplegar a producción)
Todos se verifican en el pipeline; si uno falla, no hay deploy a producción.

| Criterio | Umbral | Dónde se verifica |
|---|---|---|
| Pruebas unitarias, de componentes y de persistencia | 100 % pasan | build-test |
| Cobertura sobre código existente (proyecto y módulo web) | ≥ 80 % (sentencia + decisión) | build-test y SonarQube Cloud (carpeta `frontend/`) |
| Cobertura sobre código nuevo | ≥ 80 % | quality gate |
| Bugs críticos abiertos | 0 | quality gate |
| Duplicación | ≤ 5 % | quality gate |
| Smoke, integración y E2E en QA | 100 % pasan | integration-qa, e2e-qa |
| Carga | Umbrales de [pruebas-de-carga.md](pruebas-de-carga.md) | carga-qa |
| Defectos | Ninguno crítico o alto abierto; cada corregido tiene su test de regresión | Revisión del registro |

### Suspensión y reanudación
- QA no levanta en 15 minutos o Supabase no responde (`db/check_connection.py` falla): se suspenden las pruebas
  contra QA; se reanudan volviendo a correr el pipeline cuando el servicio vuelve. No cuenta como defecto del
  módulo salvo que el error sea nuestro.
- Un test inestable (pasa y falla sin cambios) se arregla o se elimina en el día; no se reintenta en el pipeline.

## 5. Riesgos

Probabilidad (P) e impacto (I) de 1 a 5; exposición = P × I. Ordenados de mayor a menor.

| # | Riesgo | P | I | P×I | Mitigación (pruebas) | Evidencia |
|---|---|---|---|---|---|---|
| R1 | Una versión nueva de una dependencia (fpdf2, Playwright, Locust, el SDK de un servicio) rompe una función sin tocar nuestro código | 4 | 4 | 16 | CI instala de cero en cada push; versiones fijas en `requirements-qa.txt`; tests que generan los PDF reales | DEF-001 |
| R2 | Exposición de datos: el panel está en internet (Render) y muestra personas, alertas y video | 3 | 5 | 15 | Tests de sesión y de rutas (`test_sesion.py`, `test_seguridad.py`); smoke `test_la_api_exige_sesion` en QA y producción; revisión de las vulnerabilidades de SonarQube Cloud | DEF-002, DEF-004, DEF-023 a DEF-027 |
| R3 | Supabase (base o Storage) caído o lento | 3 | 5 | 15 | Los endpoints responden 503 y no 500; el pool descarta las conexiones rotas; el panel muestra "—" en vez de datos inventados | DEF-003, DEF-008, `test_pool.py` |
| R4 | El panel queda en blanco o muestra datos inventados ante un error de la API | 3 | 3 | 9 | Tests de componentes con respuestas de error | DEF-015, DEF-016, DEF-021 |
| R5 | Degradación bajo carga en Render gratuito (0,1 CPU, 512 MB, un worker) | 3 | 3 | 9 | Stress y esfuerzo sostenido con umbrales en cada deploy | Stress en rojo con 4 y 8 hilos; en verde con el pool |
| R6 | Un cambio visual de una rama rompe un flujo de otra al mergear | 3 | 3 | 9 | Traer `main` a la rama y correr todas las suites antes del PR; los tests de componentes verifican datos con movimiento reducido | DEF-020, DEF-021, DEF-022 |
| R7 | Un empleado ve secciones de análisis (reportes, configuración) que no le corresponden | 2 | 4 | 8 | Tabla de decisión de permisos (sección 7) cubierta completa; el E2E con la cuenta de empleado verifica el menú | `permisos.test.js`, `test/e2e/` |
| R8 | Arranque en frío de Render (el plan gratuito duerme el servicio) | 5 | 1 | 5 | Timeouts de 90 s en las pruebas contra QA; el deploy espera al commit correcto | `deploy_render.sh` |
| R9 | Con Resend caído, los pedidos de demo quedan solo en `leads.jsonl`, que Render borra en cada deploy, y el reintento que pide la landing los duplica | 2 | 3 | 6 | `test_leads.py` verifica que el pedido se guarde aunque el email falle; **abierto**: la solución (guardarlos en Supabase) es un cambio de la tesis | Plan de contingencia ([01-introduccion-calidad.md](01-introduccion-calidad.md)) |

Los riesgos de arriba son **de producto**: afectan lo que se entrega. Los **de proyecto** afectan a cómo se hace
el TP:

| # | Riesgo de proyecto | P | I | P×I | Mitigación |
|---|---|---|---|---|---|
| RP1 | El plan gratuito de una herramienta (GitHub Actions, SonarQube Cloud, Render) cambia o se queda sin cupo antes de la entrega | 2 | 5 | 10 | Todo corre también localmente con un comando; la imagen Docker se puede levantar fuera de Render |
| RP2 | Poco tiempo hasta la entrega (26/10) para las pruebas contra QA, que tardan unos 40 minutos por corrida | 4 | 3 | 12 | Las suites unitarias se corren primero en la rama de trabajo (1,6 min); a `main` solo llega lo que ya pasó localmente |
| RP3 | Un integrante cambia código de la tesis y rompe lo que el TP mide (por ejemplo, el rediseño visual de 08e12e6) | 3 | 3 | 9 | Traer `main` y correr todas las suites antes de cada PR (riesgo R6) |
| RP4 | Dependencia de un único integrante para operar las cuentas (Render, Supabase, Jira) | 3 | 4 | 12 | Accesos compartidos con el equipo y pasos documentados en este plan y en el README |
| RP5 | Uso de IA que genera pruebas o texto que nadie del equipo entiende | 2 | 4 | 8 | Cada cambio se revisa y se ejecuta antes de subirlo; ver [uso-de-ia.md](uso-de-ia.md) |

## 6. Matriz ISO/IEC 25010

La matriz de las 8 características del módulo web (si se vio comprometida, la evidencia, la práctica que la previene
y el estado) y el top 3 justificado están en [03-modelos-calidad-y-niveles.md](03-modelos-calidad-y-niveles.md).
Top 3, de mayor a menor impacto: **Seguridad**, **Fiabilidad** y **Eficiencia de desempeño**.

## 7. Técnicas de diseño de casos

Los casos que no son obvios a partir del nombre del test se documentan con la [plantilla](plantillas.md).

- **Clases de equivalencia y valores límite:** parámetros de los endpoints (rangos de fechas, `t` y `dur` de los
  clips, cabecera `Range` de los videos, `source` y `roi` de la caja, URLs de cámaras), clave mínima de 8
  caracteres del login. Ejemplo completo: CP-VID-01 en [plantillas.md](plantillas.md).
- **Tabla de decisión:** qué sección ve cada rol (`frontend/src/components/permisos.js`). Condiciones: el rol de
  la sesión y el tipo de sección pedida.

  | Regla | Rol | Sección pedida | Resultado | Test |
  |---|---|---|---|---|
  | 1 | Administrador | Cualquiera del panel (Dashboard, Productos, Reportes, Alertas, Config) | Se muestra | "el administrador ve todas las secciones" |
  | 2 | Empleado | Operativa (Productos, Alertas) | Se muestra | "el empleado solo ve productos y alertas"; E2E con la cuenta de empleado |
  | 3 | Empleado | De análisis o sistema (Dashboard, Reportes, Config) | Redirige a Productos (no aparece en el menú) | "paginaPermitida redirige a la inicial…"; E2E |
  | 4 | Desconocido, vacío o ausente | Cualquiera | No se muestra nada | "un rol desconocido, vacío o ausente no ve nada" |
  | 5 | Cualquiera | Una que no existe | No se muestra | "una sección inexistente nunca está permitida" |

  Los tests están en `permisos.test.js`; la sección inicial de cada rol (Dashboard o Productos) la verifica
  "cada rol arranca en una sección que sí puede ver".
- **Transición de estados y casos de uso:** el formulario de pedido de demo de la landing, el bloqueo del login y los
  recorridos del administrador y del empleado. Todos los casos documentados, con su test, están en
  [05-pruebas-dinamicas.md](05-pruebas-dinamicas.md).
- **Cobertura de sentencia y de decisión:** `pytest-cov` con `branch = true` y Vitest con V8. El reporte de cada
  ejecución está en el resumen del job build-test y en SonarQube Cloud.

## 8. Trazabilidad requisito → caso → defecto

Requisitos de la tesis que se cumplen en el módulo web.

| Requisito | Casos de prueba (archivos) | Nivel | Defectos |
|---|---|---|---|
| RF-04 Confirmar empleados desde el panel | `test_reportes.py` (posibles empleados), `test_api_basica.py` (`POST /api/personas/<id>/empleado`), `SectionPages.test.jsx` (alerta de posible empleado) | U | — |
| RF-06 Mapa de calor por sesión y período | `test_heatmap.py`, `test_plano_calor.py`, `FloorPlan.test.jsx` | U | DEF-002, DEF-003 |
| RF-09 Alerta de POSIBLE_HURTO visible en la interfaz | `test_api_basica.py` (alertas), `SectionPages.test.jsx`, `useAlertas.test.js`, E2E | U, E2E | — |
| RF-11 La cajera confirma el producto y se descuenta stock | `test_productos.py`, `ProductosPage.test.jsx`, E2E (empleado) | U, E2E | DEF-025 |
| RF-13 Reportes CSV y PDF | `test_reportes*.py`, `test_export.py`, `ReportsV2Page.test.jsx`, integración (`exportar_csv`), E2E (administrador) | U, I, E2E | DEF-001, DEF-008 |
| RF-14 Tablero web | `App.test.jsx`, `FloorPlan.test.jsx`, `Sidebar.test.jsx`, `ReportMetrics.test.jsx`, `LoginPage.test.jsx`, `seguir.test.js`, `permisos.test.js`, `test_sesion.py`, E2E | U, E2E | DEF-004, DEF-015, DEF-018, DEF-020, DEF-026 |
| RF-15 Feed de alertas y reportes sin recarga | `SectionPages.test.jsx`, `test_video.py`, `ReportsV2Page.test.jsx`, E2E | U, E2E | DEF-005, DEF-006, DEF-007, DEF-027 |
| RNF-03 Desacoplamiento | La API no importa código de los pipelines; la imagen de Render no incluye `deteccion/` ni `deteccion_productos/` | — | — |
| RNF-04 Sin datos inventados | `FloorPlan.test.jsx`, `LandingPage.test.jsx`, `ReportMetrics.test.jsx`, `test_api_basica.py` (base vacía) | U | DEF-008, DEF-016, DEF-021 |
| Seguridad del servidor (R2) | `test_seguridad.py`, `test_sesion.py`, `test_heatmap.py`, smoke | U, Smoke | DEF-002, DEF-004, DEF-023, DEF-024, DEF-026, DEF-027 |
| Desempeño (R5) | `test/carga/`, `test_pool.py` | Carga, P | — (ver [pruebas-de-carga.md](pruebas-de-carga.md)) |
| Landing comercial (sin RF en la tesis) | `LandingPage.test.jsx`, `test_leads.py` | U | DEF-016, DEF-017, DEF-022 |

U = unitario o de componentes · P = persistencia · I = integración · E2E = navegador.

Para ver los tests de un requisito o de un defecto: `git grep -n "DEF-023"` o abrir los archivos de la tabla.

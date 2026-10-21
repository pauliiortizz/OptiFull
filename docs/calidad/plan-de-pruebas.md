# Plan de pruebas del módulo de interfaz web de OptiFull

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0 | 20/10/2026 | Primera versión: alcance, niveles, criterios, riesgos, ISO/IEC 25010 y trazabilidad |
| 1.1 | 21/10/2026 | Merge de `main` en `Pau`: DEF-020 a DEF-022 en la trazabilidad y riesgo de merge |
| 1.2 | 21/10/2026 | Revisión de las vulnerabilidades de SonarQube Cloud: DEF-023 a DEF-027 |
| 2.0 | 21/10/2026 | El TP se enfoca en el módulo de interfaz web (`frontend/`): pirámide, riesgos, ISO 25010, tabla de decisión y trazabilidad reescritos para ese módulo |
| 2.1 | 21/10/2026 | La medición sigue cubriendo todo el sistema; los números del TP son los de `frontend/` en esos mismos reportes |

Este documento está versionado junto con el código: cada cambio de alcance, criterio o umbral se hace en el
mismo commit que el cambio en las pruebas o en el pipeline, y se agrega una fila a la tabla de arriba.

Documentos relacionados: [alcance de la medición](alcance-medicion.md) · [registro de defectos](defectos.md) ·
[plantillas](plantillas.md) · [pruebas de carga](pruebas-de-carga.md) ·
[herramienta incorporada](herramienta-sonarcloud.md) · pipeline en `.github/workflows/pipeline.yml`.

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
| Unitario de la API | Endpoints y funciones aislados; base de datos, procesos y HTTP con dobles de prueba | `test/unitarios/` (archivos de la API) | pytest | 431 | Cada push y PR (build-test) |
| Unitario y de componentes del panel | Componentes React con Testing Library, `fetch` simulado | `frontend/src/**/*.test.*` | Vitest + jsdom | 367 | Cada push y PR (build-test) |
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

## 6. Matriz ISO/IEC 25010

Las 8 características del modelo de calidad del producto (versión 2011, la que se trabajó en la materia),
aplicadas al módulo de interfaz web.

| Característica | Qué significa para el módulo web | Evidencia | Estado |
|---|---|---|---|
| **Adecuación funcional** | Muestra, filtra y exporta lo que dicen los RF del panel | 808 pruebas unitarias del módulo; trazabilidad de la sección 8; E2E del recorrido de cada rol contra QA; integración de la API en QA | ✅ |
| **Eficiencia de desempeño** | El panel responde rápido con el equipo de una tienda usándolo | Carga sostenida (15 usuarios) con p95 de 140 ms; stress (40 usuarios) con p95 de 2,4 s después del pool de conexiones (antes 7,6 s) | ✅ |
| **Compatibilidad** | Interopera con Supabase y Render y funciona en los navegadores del local | Integración, smoke y E2E contra QA en Render con Supabase; E2E en Chromium (CI) y Edge (equipo); DEF-020 (navegadores sin Web Animations) | ✅ |
| **Usabilidad** | El personal de la tienda usa el panel sin capacitación, incluso con teclado | Tests de componentes por rol accesible (Testing Library); DEF-018 (menú con teclado); mensajes claros en los formularios (DEF-017, DEF-022); RNF-04, "—" en vez de datos inventados (DEF-016, DEF-021) | 🟡 quedan observaciones menores de accesibilidad en SonarQube Cloud; el detalle por hora del mapa de congestión solo se ve con el mouse |
| **Fiabilidad** | Una falla de Supabase o de un endpoint no tira abajo el panel | 503 sin base (DEF-003, DEF-008); el panel no queda en blanco (DEF-015); el pool descarta conexiones rotas; carga sostenida sin degradación (0,58); smoke en cada deploy | ✅ |
| **Seguridad** | Nadie sin sesión ve datos; nadie con sesión llega a archivos o redes internas del servidor | DEF-002, DEF-004 y DEF-023 a DEF-027 corregidos con regresión; las 10 vulnerabilidades de SonarQube Cloud revisadas (5 reales, 5 justificadas, 0 abiertas, calificación A); cabeceras anti-framing; cookie de sesión firmada, `HttpOnly`, `SameSite=Lax`, `Secure` en QA y producción; claves con pbkdf2 | ✅ |
| **Mantenibilidad** | El equipo puede cambiar el código del módulo sin miedo | Cobertura en SonarQube Cloud: 98,0 % de la API y 91,6 % del panel (94,5 % el módulo); duplicación 1,0 %; Ruff y quality gate en el pipeline | 🟡 8 funciones con complejidad mayor a 10 (la mayor, `generar_pdf()`, 21) sin refactorizar |
| **Portabilidad** | Se despliega igual en CI, en QA y en producción | Imagen Docker única para QA y producción; el mismo contenedor se prueba en CI (system-check); tests en Linux (CI, Python 3.12) y Windows (equipo, Python 3.14) | ✅ |

### Top 3

1. **Seguridad.** El módulo web es la única parte de OptiFull expuesta a internet: está en Render y muestra
   personas, alertas y video de un comercio real. Los dos defectos críticos encontrados (DEF-002, DEF-004) y las
   cinco vulnerabilidades reales de SonarQube Cloud eran de este módulo, y el riesgo de exposición (R2) es de los
   de mayor impacto.
2. **Fiabilidad.** El personal del local trabaja con el panel abierto y la caja web descuenta stock: si una falla
   de Supabase lo deja en blanco o con datos falsos, se toman decisiones con información equivocada. Dos riesgos de
   los más altos (R3, R4) son de fiabilidad.
3. **Adecuación funcional.** El valor del módulo es que cada rol vea las alertas, los reportes y el stock que le
   corresponden, correctos. Un reporte mal calculado o un permiso mal aplicado (R7) es justo lo que el cliente paga
   por evitar.

Eficiencia de desempeño queda cuarta: importa, y de hecho fue la que más cambió (el pool de conexiones), pero la
carga real es la de un equipo chico y está acotada con umbrales en cada deploy.

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

# Plan de pruebas de OptiFull

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0 | 20/10/2026 | Primera versión: alcance, niveles, criterios, riesgos, ISO/IEC 25010 y trazabilidad |

Este documento está versionado junto con el código: cada cambio de alcance, criterio o umbral se hace en el
mismo commit que el cambio en las pruebas o en el pipeline, y se agrega una fila a la tabla de arriba.

Documentos relacionados: [alcance de la medición](alcance-medicion.md) · [registro de defectos](defectos.md) ·
[plantillas](plantillas.md) · [pruebas de carga](pruebas-de-carga.md) ·
[herramienta incorporada](herramienta-sonarcloud.md) · pipeline en `.github/workflows/pipeline.yml`.

## 1. Objetivo y alcance

Verificar que OptiFull cumple los requisitos de la tesis (RF-01 a RF-15, RNF-01 a RNF-06, sección 2 del informe)
en cada cambio, de forma automática, antes de que llegue a producción.

**Entra:** backend Flask (`frontend/api/`), panel React (`frontend/src/`), análisis de cámaras (`deteccion/`),
caja de productos (`deteccion_productos/`), base de datos (`db/schema.sql`), despliegue en Render (QA y
producción) y las integraciones externas: Supabase (Postgres y Storage), Render, y las APIs de Gemini, Groq y
Anthropic.

**No entra:** la precisión de los modelos de terceros (YOLO, los LLM) como tal: se prueba lo que OptiFull hace con
sus respuestas, incluidas las mal formadas. Los scripts de mantenimiento de un solo uso, según
[alcance-medicion.md](alcance-medicion.md). El nodo de captura instalado en la tienda (RNF-05, RNF-06) se
valida a mano en el sitio.

## 2. Niveles de prueba y pirámide

| Nivel | Qué prueba | Dónde | Herramienta | Cantidad | Cuándo corre |
|---|---|---|---|---|---|
| Unitario (backend y detección) | Funciones y endpoints aislados; BD, cámaras y LLM con dobles de prueba | `test/unitarios/` | pytest | 899 | Cada push y PR (build-test) |
| Unitario y de componentes (frontend) | Componentes React con Testing Library, `fetch` simulado | `frontend/src/**/*.test.*` | Vitest + jsdom | 362 | Cada push y PR (build-test) |
| Persistencia | El código real contra un Postgres creado con `schema.sql` (incluye `main.py` y la caja de punta a punta con video sintético) | `test/bd/` | pytest + Postgres 16 | 131 | Cada push y PR (build-test) |
| Integración de sistema | El sistema completo en un contenedor Docker contra la BD de QA | `test/integracion/` | pytest + requests | 12 | Push a `main` (system-check) |
| Smoke | Lo mínimo de un despliegue: vivo, con BD, commit esperado, frontend servido, API con sesión | `test/integracion/` (`-m smoke`) | pytest | 4 | Tras el deploy a QA y a producción |
| Integración en QA | La API desplegada en Render con Supabase | `test/integracion/` | pytest + requests | 8 | Tras el deploy a QA |
| E2E | El flujo de un usuario con un navegador real | `test/e2e/` | Playwright + Chromium | 2 | Tras el deploy a QA |
| Carga | Stress y esfuerzo sostenido con umbrales | `test/carga/` | Locust | 2 perfiles | Tras el E2E en QA |

La base es ancha a propósito: 1261 pruebas unitarias corren en menos de dos minutos y dan el diagnóstico más
preciso; las de arriba son pocas, lentas y dependen de servicios externos, por eso prueban recorridos y no
casos. Cada defecto corregido suma un test de regresión en el nivel más bajo que lo reproduce.

Un comando por nivel (desde la raíz del repo):

```
pytest -c test/pytest.ini test/unitarios                                   # unitarios backend
cd frontend && npm test                                                    # unitarios frontend
TEST_DATABASE_URL=postgresql://... pytest -c test/pytest.ini test/bd       # persistencia
BASE_URL=... QA_USUARIO=... QA_CLAVE=... pytest -c test/pytest.ini test/integracion   # integración (-m smoke: smoke)
BASE_URL=... QA_USUARIO=... QA_CLAVE=... pytest -c test/pytest.ini test/e2e           # E2E
CARGA_PERFIL=stress locust -f test/carga/locustfile.py --headless --host $BASE_URL --csv test-results/carga/stress
```

## 3. Entornos y datos

| Entorno | Para qué | Datos |
|---|---|---|
| Local / CI build-test | Unitarias y persistencia | Dobles de prueba; Postgres temporal vacío por test (nunca Supabase) |
| Contenedor en CI (system-check) | Integración del sistema empaquetado | BD de QA en Supabase, solo lectura |
| QA en Render (`optifull-qa`) | Smoke, integración, E2E, carga | BD de QA en Supabase; cuenta `QA_USUARIO` creada con `db/crear_usuario.py` |
| Producción en Render (`optifull-prod`) | Solo smoke (no escribe nada) | Datos reales |

## 4. Criterios

### Entrada (para empezar a probar un cambio)
- El backend compila (`compileall`) y Ruff no tiene observaciones bloqueantes (`E9`, `F`, `B`).
- Las dependencias se instalan de cero desde los `requirements` (así se detectó DEF-019).
- Para los niveles en QA: el deploy terminó y `/api/health` responde con el commit que se está probando.

### Salida (para desplegar a producción)
Todos se verifican en el pipeline; si uno falla, no hay deploy a producción.

| Criterio | Umbral | Dónde se verifica |
|---|---|---|
| Pruebas unitarias, de componentes y de persistencia | 100 % pasan | build-test |
| Cobertura sobre código existente | ≥ 80 % (sentencia + decisión) | build-test y SonarQube Cloud |
| Cobertura sobre código nuevo | ≥ 80 % | quality gate |
| Bugs críticos abiertos | 0 | quality gate |
| Duplicación | ≤ 5 % | quality gate |
| Smoke, integración y E2E en QA | 100 % pasan | integration-qa, e2e-qa |
| Carga | Umbrales de [pruebas-de-carga.md](pruebas-de-carga.md) | carga-qa |
| Defectos | Ninguno crítico o alto abierto; cada corregido tiene su test de regresión | Revisión del registro |

### Suspensión y reanudación
- QA no levanta en 15 minutos o Supabase no responde (`db/check_connection.py` falla): se suspenden las pruebas
  contra QA; se reanudan volviendo a correr el pipeline cuando el servicio vuelve. No cuenta como defecto de
  OptiFull salvo que el error sea nuestro.
- Un test inestable (pasa y falla sin cambios) se arregla o se elimina en el día; no se reintenta en el pipeline.

## 5. Riesgos

Probabilidad (P) e impacto (I) de 1 a 5; exposición = P × I. Ordenados de mayor a menor.

| # | Riesgo | P | I | P×I | Mitigación (pruebas) | Evidencia |
|---|---|---|---|---|---|---|
| R1 | Un cambio en una dependencia externa (SDK de un LLM, librería de PDF) rompe un módulo sin tocar nuestro código | 4 | 4 | 16 | CI instala de cero en cada push; versiones fijas en `requirements-qa.txt`; tests que construyen los clientes reales | DEF-001, DEF-019 |
| R2 | Una respuesta mal formada del LLM corta la caja | 4 | 4 | 16 | Tests con respuestas raras (null, texto, listas, tamaños en 0) | DEF-013, DEF-014 |
| R3 | Exposición de datos: video de personas, credenciales de la BD, API sin login | 3 | 5 | 15 | Tests de sesión y de rutas; smoke `test_la_api_exige_sesion` en QA y producción | DEF-002, DEF-004 |
| R4 | Supabase (BD o Storage) caído | 3 | 5 | 15 | Los endpoints responden 503 y no 500; reconexión de la persistencia; mapas de calor pendientes en disco | DEF-003, DEF-008, `test_persistencia_reconexion.py` |
| R5 | Un refactor cambia el comportamiento (p. ej. `main()` de complejidad 91) | 3 | 4 | 12 | Test de punta a punta de `main.py` escrito antes del refactor y no tocado después | `test/bd/test_main_e2e.py` |
| R6 | Clasificación de visitas errónea (falsas alertas de hurto o hurtos sin alerta) | 3 | 4 | 12 | Tabla de decisión de RF-08 cubierta completa; validación manual con videos reales | `test_eventos.py`, `test_main_e2e.py` |
| R7 | API de LLM caída o sin cuota | 3 | 4 | 12 | Tres proveedores de Re-ID con dobles de cada SDK; reintentos; la caja permite elegir el producto a mano | `test_reid.py`, `test_caja_vision.py` |
| R8 | El panel queda en blanco o muestra datos inventados ante un error de la API | 3 | 3 | 9 | Tests de componentes con respuestas de error | DEF-015, DEF-016 |
| R9 | Degradación bajo carga en Render gratuito (512 MB, un worker) | 3 | 3 | 9 | Stress y esfuerzo sostenido con umbrales en cada deploy | `carga-qa` |
| R10 | Arranque en frío de Render (el plan gratuito duerme el servicio) | 5 | 1 | 5 | Timeouts de 90 s en las pruebas contra QA; el deploy espera al commit correcto | `deploy_render.sh` |

## 6. Matriz ISO/IEC 25010

Las 8 características del modelo de calidad del producto (versión 2011, la que se trabajó en la materia).

| Característica | Qué significa para OptiFull | Evidencia | Estado |
|---|---|---|---|
| **Adecuación funcional** | Detecta, clasifica y reporta lo que dicen los RF | 1392 pruebas automatizadas; trazabilidad de la sección 8; E2E del flujo principal; `test_main_e2e.py` (una visita completa termina en COMPRA_NORMAL con todo persistido) | ✅ |
| **Eficiencia de desempeño** | El panel responde rápido con el equipo de una tienda usándolo; la caja identifica un producto en ~1,5 s | Umbrales de p95 en stress y carga sostenida; medición de latencia de la caja (de ~1,8 s a ~1,45 s por producto, ver `vision_agent.py`) | ✅ |
| **Compatibilidad** | Convive e interopera con Supabase, Render, cámaras RTSP y tres APIs de LLM | Integración y E2E contra QA; dobles de cada SDK de Re-ID; la caja probada con el SDK de Anthropic 0.x y 1.x (DEF-019) | ✅ |
| **Usabilidad** | El personal de la tienda usa el panel sin capacitación, incluso con teclado | Tests de componentes por rol accesible (Testing Library); DEF-018 (menú con teclado); RNF-04 ("—" en vez de datos inventados, DEF-016) | 🟡 quedan 12 observaciones menores de accesibilidad en SonarQube Cloud |
| **Fiabilidad** | Funciona desatendido; una falla externa no tira abajo todo | 503 sin BD (DEF-003, DEF-008); la caja no se corta (DEF-013, DEF-014); reconexión de la persistencia; degradación ≤ 2× en carga sostenida; smoke en cada deploy | ✅ |
| **Seguridad** | Nadie ajeno ve video, personas ni credenciales; no hay biometría | DEF-002 y DEF-004 corregidos con regresión; cookie de sesión firmada, `HttpOnly`, `SameSite=Lax`, `Secure` en QA y producción; claves con pbkdf2; RNF-01 por diseño (Re-ID por descriptores de ropa) | ✅ |
| **Mantenibilidad** | El equipo puede cambiar el código sin miedo | Cobertura 96 % backend / 98,75 % frontend; duplicación 0,9 %; `main()` de complejidad 91 a ≤ 9; Re-ID de 1285 a 809 líneas; Ruff y quality gate en el pipeline | ✅ |
| **Portabilidad** | Se instala igual en la PC del local, en CI y en Render | Imagen Docker única para QA y producción; tests en Linux (CI, Python 3.12) y Windows (equipo, Python 3.14); OpenCV *headless* en CI | ✅ |

### Top 3

1. **Seguridad.** OptiFull procesa video de personas reales dentro de un comercio y guarda credenciales de una
   base en la nube. Los dos defectos críticos encontrados (DEF-002, DEF-004) eran de seguridad, y el impacto de
   una filtración (datos personales, la base de producción) es el más alto de la tabla de riesgos.
2. **Fiabilidad.** El sistema corre sin nadie mirándolo (RNF-06) y la caja descuenta stock: si se corta, la
   tienda pierde ventas o registra mal el inventario. Tres riesgos de la tabla (R2, R4, R7) son de fiabilidad.
3. **Adecuación funcional.** El valor del producto son las alertas de posible hurto y los reportes: una
   clasificación equivocada genera falsas alarmas o hurtos sin detectar (R6), que es justo lo que el cliente
   paga por evitar.

Eficiencia de desempeño queda cuarta: importa, pero la carga real es la de un equipo chico y está acotada con
umbrales en cada deploy.

## 7. Técnicas de diseño de casos

Los casos que no son obvios a partir del nombre del test se documentan con la [plantilla](plantillas.md).

- **Clases de equivalencia y valores límite:** parámetros de los endpoints (rangos de fechas, `t` y `dur` de los
  clips, cabecera `Range` de los videos), umbrales del matching de la caja (confianza, tamaños), clave mínima de
  8 caracteres del login. Ejemplo completo: CP-VID-01 en [plantillas.md](plantillas.md).
- **Tabla de decisión:** clasificación de una visita (RF-08, `deteccion/pipeline/eventos.py`). `paso_por_caja`
  es la condición dominante:

  | Regla | Pasó por caja (con alguien en la caja) | Tomó un producto | Resultado | Alerta | Test |
  |---|---|---|---|---|---|
  | 1 | Sí | Sí | COMPRA_NORMAL | No | `test_escenario_a_compra_normal_tomo_producto_y_se_acerco_a_caja` |
  | 2 | Sí | No | COMPRA_NORMAL (compra en el mostrador) | No | `test_escenario_a_compra_en_el_mostrador_sin_tomar_producto_de_gondola` |
  | 3 | No | Sí | POSIBLE_HURTO | Alta | `test_escenario_b_hurto_tomo_producto_sin_acercarse_a_caja` |
  | 4 | No | No | TRANSITO_SIN_COMPRA | No | `test_escenario_c_ni_tomo_producto_ni_se_acerco_a_pagar` |

- **Cobertura de sentencia y de decisión:** `pytest-cov` con `branch = true` y Vitest con V8. El reporte de cada
  ejecución está en el resumen del job build-test y en SonarQube Cloud.

## 8. Trazabilidad requisito → caso → defecto

| Requisito | Casos de prueba (archivos) | Nivel | Defectos |
|---|---|---|---|
| RF-01 Detección de personas sin biometría | `test_video_source.py`, `test_utils_y_pantalla.py`, `bd/test_main_e2e.py` | U, P | DEF-011, DEF-012 |
| RF-02 Track ID por persona | `test_tracking_identidad.py`, `test_tracking_eventos.py` | U | — |
| RF-03 Re-ID entre cámaras | `test_reid.py`, `bd/test_persistencia_correcciones.py` (fusiones) | U, P | DEF-009 |
| RF-04 Clientes vs. empleados | `test_tracking_identidad.py`, `bd/test_persistencia_correcciones.py` (reglas de empleados) | U, P | — |
| RF-05 Mapa de calor | `test_heatmap_metricas_storage.py`, `test_heatmap.py`, `test_plano_calor.py` | U | DEF-002 |
| RF-06 Mapa de calor por sesión y período | `test_heatmap.py`, `test_plano_calor.py`, `FloorPlan.test.jsx` | U | DEF-002, DEF-003 |
| RF-07 Secuencia de zonas por visita | `test_tracking_eventos.py`, `test_eventos.py` | U | — |
| RF-08 Clasificación de visitas | `test_eventos.py` (tabla de decisión), `bd/test_main_e2e.py` | U, P | — |
| RF-09 Alerta de POSIBLE_HURTO | `test_evidencia.py`, `test_api_basica.py` (alertas), `SectionPages.test.jsx`, `useAlertas.test.js`, E2E | U, E2E | — |
| RF-10 Identificar el producto en la caja | `test_caja_vision.py`, `test_caja_captura.py`, `test_caja_motion.py`, `bd/test_caja.py` | U, P | DEF-013, DEF-019 |
| RF-11 Matching contra el catálogo y descuento de stock | `test_caja_matching.py`, `test_caja_cajera_consola.py`, `test_productos.py`, `bd/test_caja.py`, `ProductosPage.test.jsx` | U, P | DEF-013, DEF-014 |
| RF-12 Persistencia relacional | `bd/test_persistencia_registro.py`, `bd/test_persistencia_correcciones.py`, `test_persistencia_reconexion.py` | U, P | DEF-010 |
| RF-13 Reportes CSV y PDF | `test_reportes*.py`, `test_export.py`, `ReportsV2Page.test.jsx`, integración (`exportar_csv`), E2E | U, I, E2E | DEF-001, DEF-008 |
| RF-14 Tablero web | `App.test.jsx`, `FloorPlan.test.jsx`, `Sidebar.test.jsx`, `ReportMetrics.test.jsx`, `test_sesion.py`, E2E | U, E2E | DEF-004, DEF-015, DEF-018 |
| RF-15 Feed de alertas y reportes sin recarga | `SectionPages.test.jsx`, `test_video.py`, `ReportsV2Page.test.jsx`, E2E | U, E2E | DEF-005, DEF-006, DEF-007 |
| RNF-01 Privacidad | `test_reid.py` (el Re-ID compara descriptores de ropa, complexión, cabello y accesorios; no hay reconocimiento facial en el código) | U | — |
| RNF-02 Costo operativo | `test_caja_motion.py` (el LLM solo se llama con la escena estable y nueva) | U | — |
| RNF-03 Desacoplamiento | Cada módulo se prueba y se despliega por separado (la imagen de Render no incluye `deteccion/`) | — | — |
| RNF-04 Sin datos inventados | `FloorPlan.test.jsx`, `LandingPage.test.jsx`, `test_api_basica.py` (base vacía) | U | DEF-008, DEF-016 |
| RNF-05 Acceso remoto sin abrir puertos | Validación manual en el sitio | Manual | — |
| RNF-06 Operación desatendida | `test_persistencia_reconexion.py`, `bd/test_main_e2e.py` (cámara caída, RTSP) | U, P | — |

U = unitario o de componentes · P = persistencia · I = integración · E2E = navegador. DEF-017 (formulario de la
landing) no corresponde a un RF de la tesis: la landing es comercial.

Para ver los tests de un requisito o de un defecto: `git grep -n "DEF-013"` o abrir los archivos de la tabla.

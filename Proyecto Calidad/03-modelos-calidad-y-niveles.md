# 3 · Modelos de calidad y niveles de prueba

## Matriz ISO/IEC 25010 del módulo de interfaz web

Las 8 características del modelo de calidad del producto, con el formato del caso Knight Capital de la clase del
24/08: si se vio comprometida durante el TP, con qué evidencia concreta, qué práctica la previene, y cómo quedó.

| Característica | ¿Comprometida? | Evidencia concreta | Práctica que la previene o la detecta | Estado al 21/10 |
|---|---|---|---|---|
| **Adecuación funcional** | Sí | Exportar un PDF fallaba con algunas versiones de fpdf2 (DEF-001); videos y clips respondían 500 ante pedidos válidos o mal escritos (DEF-005 a 007); la conversión mostraba un 0 % inventado (DEF-021) | Tests unitarios y de componentes por requisito (trazabilidad del plan); E2E del recorrido de cada rol contra QA | ✅ Corregidos; 808 pruebas unitarias del módulo y E2E en cada deploy |
| **Eficiencia de desempeño** | Sí | Stress de 40 usuarios en QA con p95 de 7,6 s: la API abría una conexión a Supabase por pedido | Pruebas de carga con umbrales en cada deploy (job `carga-qa`) | ✅ Pool de conexiones: p95 de 2,4 s en stress y 140 ms en carga sostenida |
| **Compatibilidad** | Sí | Sin Web Animations (navegadores viejos) no se podía iniciar sesión (DEF-020) | Tests de componentes en jsdom (que no tiene esa API); E2E en Chromium; integración contra Supabase y Render en QA | ✅ Corregido |
| **Usabilidad** | Parcial | El menú lateral no se podía usar con el teclado (DEF-018); mensajes confusos en el formulario de la landing (DEF-017, DEF-022); el detalle por hora del mapa de congestión solo se ve con el mouse | Tests por rol accesible (Testing Library); observaciones de accesibilidad de SonarQube Cloud | 🟡 Corregidos los defectos; quedan 11 observaciones menores de accesibilidad |
| **Fiabilidad** | Sí | Sin base de datos varios endpoints respondían 500 en vez de 503 (DEF-003, DEF-008); un error de reportes dejaba el Dashboard en blanco (DEF-015) | Tests con la base simulada caída y respuestas de error; smoke en cada deploy; plan de contingencia | ✅ Corregidos; carga sostenida sin degradación (0,58) |
| **Seguridad** | Sí | Se podía descargar el `.env` (DEF-002); la API no exigía login (DEF-004); SSRF, oráculo de archivos, fuente de la caja sin validar, clickjacking y carpetas vecinas (DEF-023 a 027) | Smoke de sesión en QA y producción; `test_seguridad.py`; revisión de cada vulnerabilidad de SonarQube Cloud | ✅ 0 vulnerabilidades abiertas, calificación A |
| **Mantenibilidad** | Parcial | 8 funciones con complejidad ciclomática mayor a 10, la mayor `generar_pdf()` con 21; complejidad cognitiva de 40 en la misma función | Cobertura ≥ 80 % y quality gate en el pipeline; reporte de complejidad de Ruff | 🟡 Cubiertas por tests, sin refactorizar (ver [04-metricas-y-analisis-estatico.md](04-metricas-y-analisis-estatico.md#hallazgos)) |
| **Portabilidad** | No | La misma imagen Docker corre en CI, en QA y en producción; los tests corren en Linux (CI) y en Windows (equipo) | Job system-check: prueba la imagen antes de cada deploy | ✅ |

### Top 3 (de mayor a menor impacto)

1. **Seguridad.** Es la única característica que tuvo defectos críticos (DEF-002 y DEF-004), y el módulo web es la
   única parte de OptiFull expuesta a internet: muestra personas, alertas y video de un comercio real. Una
   filtración tiene el mayor impacto de toda la tabla de riesgos (R2: impacto 5).
2. **Fiabilidad.** El personal trabaja con el panel abierto y la caja web descuenta stock. Si una falla de Supabase
   lo deja en blanco o con datos falsos, se toman decisiones equivocadas. Dos de los riesgos más altos (R3, R4)
   son de fiabilidad, y la dependencia de un servicio externo (Supabase) no la controlamos.
3. **Eficiencia de desempeño.** Fue la característica que la prueba de carga mostró comprometida con más claridad
   (p95 de 7,6 s) y la que llevó a la mejora más grande del TP. Queda por encima de la adecuación funcional porque
   sus defectos funcionales eran casos borde (rangos de video, parámetros mal escritos) con impacto bajo, mientras
   que la lentitud afectaba a todos los usuarios a la vez.

## Calidad interna, externa y en uso

| Vista | Qué se mide en el módulo | Dónde |
|---|---|---|
| **Interna** (el código) | Cobertura 94,5 %, duplicación 1,0 %, complejidad ciclomática y cognitiva, 0 bugs críticos | SonarQube Cloud, reporte de Ruff |
| **Externa** (el sistema funcionando) | Respuestas de la API en QA, tiempos de respuesta bajo carga, comportamiento sin base de datos | Integración, smoke y carga contra QA |
| **En uso** (la persona usándolo) | Recorrido completo de cada rol con un navegador real, sin errores de JavaScript ni pantallas en blanco | E2E con Playwright; la usabilidad percibida se valida a mano con el personal del local (no se automatiza) |

## Mapa de niveles de prueba

| Nivel | Qué se prueba en el módulo web | Pruebas | Cantidad | Tipo |
|---|---|---|---|---|
| **Componente** | Cada endpoint de la API y cada componente del panel, aislados con dobles de prueba | `test/unitarios/` (archivos de la API), `frontend/src/**/*.test.*` | 431 + 367 | Funcional, regresión |
| **Integración** | La API con un Postgres real (pool de conexiones); la imagen Docker contra la base de QA; la API desplegada contra Supabase | `test/bd/test_pool.py`, `test/integracion/` (system-check e integration-qa) | 10 + 12 | Funcional, integración |
| **Sistema** | El módulo completo desplegado en Render, recorrido con un navegador | `test/e2e/` | 2 | Funcional (E2E), compatibilidad |
| **Aceptación** | Lo que tiene que cumplirse para pasar a producción: el recorrido de cada rol, los umbrales de carga y el smoke en producción | `test/e2e/`, `test/carga/`, `test/integracion -m smoke` | 2 + 2 perfiles + 4 | Aceptación, carga y estrés, smoke |

**Tipos de prueba usados.** Funcionales: regresión (un test por defecto), smoke (en QA y en producción),
compatibilidad (navegadores, Web Animations). No funcionales: carga y estrés (Locust), recuperación (el servicio
sin base de datos y la reconexión del pool), configuración (`APP_ENV` local/QA/producción, como en DEF-023) y
estructurales (cobertura de sentencia y decisión). Las exploratorias y las de usabilidad se hacen a mano.

## Despliegue verificado en cada instancia

Cada instancia se verifica antes de pasar a la siguiente, y el pipeline exige que corra **el mismo commit**:

| Instancia | Cómo se despliega | Cómo se verifica | Si falla |
|---|---|---|---|
| **Contenedor en CI** (job system-check) | `docker build` de `docker/Dockerfile-optifull`, la misma imagen que usa Render | Comprobación de la base (`db/check_connection.py`), `/api/health` y las 12 pruebas de integración contra el contenedor | No hay deploy a QA |
| **QA** (`optifull-qa.onrender.com`) | Deploy Hook de Render con el SHA exacto; `deploy_render.sh` espera hasta que `/api/health` responda **ese** commit | Smoke (con `EXPECTED_COMMIT`), integración, E2E y carga | No hay deploy a producción |
| **Producción** (`optifull-prod`) | Mismo mecanismo y mismo SHA; puede pedir aprobación manual (environment `production`) | Smoke con `EXPECTED_COMMIT` | El job queda en rojo y se sabe en el momento |

Así no puede pasar lo del caso Knight Capital (un servidor con una versión vieja): si una instancia no corre el
commit esperado, el pipeline lo detecta.

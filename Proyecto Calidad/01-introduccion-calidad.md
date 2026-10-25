# 1 · Introducción a la calidad

En la materia definimos la calidad de software como la capacidad del software para cumplir con los requisitos
especificados, satisfacer las expectativas del usuario, ofrecer un rendimiento eficiente y ser mantenible en el
tiempo (conformidad, satisfacción, eficiencia, mantenibilidad). Como la calidad cambia según quién la mire, los
objetivos del módulo de interfaz web se fijaron desde tres miradas: la del **usuario**, la del **equipo** y la de
la **organización**. Cada uno es medible, tiene un umbral, una práctica de proceso que lo sostiene y el valor
medido al 21/10/2026.

## Objetivos de calidad medibles

### Usuario: el personal del local que usa el panel

| # | Objetivo | Cómo se mide | Umbral | Práctica que lo sostiene | Medido |
|---|---|---|---|---|---|
| U1 | El panel responde rápido con el equipo de una tienda conectado | p95 de la carga sostenida (15 usuarios, 10 min) contra QA | ≤ 2 s | Job `carga-qa` en cada deploy; frena producción si no se cumple | 140 ms ✅ |
| U2 | El panel nunca muestra datos inventados | Componentes de métricas con test de estado vacío y de error | 100 % | Test de componentes con respuestas vacías y 500 (RNF-04) | Cubiertos; defectos DEF-016 y DEF-021 corregidos ✅ |
| U3 | Ningún recorrido termina en una pantalla en blanco o un error | Errores de JavaScript y respuestas 5xx durante el E2E | 0 | El E2E falla si aparece cualquiera de los dos | 0 en la última ejecución ✅ |
| U4 | Todo se puede usar con teclado | Observaciones de accesibilidad de SonarQube Cloud (S1082: elementos con clic sin teclado) | 0 | Análisis en cada push a `main`; DEF-018 corrigió el menú | 11 abiertas 🟡 |

### Equipo: quienes desarrollan y mantienen el módulo

| # | Objetivo | Cómo se mide | Umbral | Práctica que lo sostiene | Medido |
|---|---|---|---|---|---|
| E1 | El código del módulo está probado | Cobertura de `frontend/` en SonarQube Cloud (sentencia + decisión) | ≥ 80 %, también sobre código nuevo | Quality gate en el pipeline | 94,5 % (API 98,0 %, panel 91,6 %) ✅ |
| E2 | El pipeline avisa rápido si algo se rompe | Duración de build-test en la rama de trabajo | ≤ 5 min | Tests unitarios con dobles de prueba, sin servicios externos | 1,6 min de media ✅ |
| E3 | Un defecto corregido no vuelve | Defectos del módulo con test de regresión | 100 % | Regla del plan: primero el test que falla, después el arreglo | 20 de 20 ✅ |
| E4 | No se acumula riesgo conocido | Bugs críticos y vulnerabilidades abiertas en `frontend/` | 0 | Quality gate y revisión de cada observación de SonarQube Cloud | 0 y 0 ✅ |

### Organización: OptiFull como producto

| # | Objetivo | Cómo se mide | Umbral | Práctica que lo sostiene | Medido |
|---|---|---|---|---|---|
| O1 | A producción solo llega lo verificado | Deploys a producción que no pasaron todo el pipeline | 0 | `deploy-prod` depende de todos los jobs anteriores; Render no despliega solo (`autoDeploy: false`) | 0 ✅ |
| O2 | Los datos del local no quedan expuestos | Endpoints con datos accesibles sin sesión | 0 | Smoke `test_la_api_exige_sesion` en QA y en producción en cada deploy | 0 ✅ |
| O3 | El proceso de calidad no cuesta dinero | Costo mensual de las herramientas de calidad e infraestructura | 0 USD | Planes gratuitos: GitHub Actions, SonarQube Cloud, Render, Supabase, Jira | 0 USD ✅ |
| O4 | Si `main` se rompe, se recupera rápido | Tiempo entre la primera ejecución fallida de `main` y la siguiente en verde | ≤ 1 día | Cada falla se analiza y se corrige con su test antes de seguir | 26 h la primera vez (20/10 16:52 → 21/10 19:00) ❌; desde entonces, cada falla se resolvió en el día |

Sobre O4: las seis ejecuciones fallidas de `main` entre el 20 y el 21/10 tuvieron una causa concreta (ver
[04-metricas-y-analisis-estatico.md](04-metricas-y-analisis-estatico.md#métrica-de-proceso)), y ninguna llegó a
producción: el pipeline hizo su trabajo. El objetivo no se cumplió la primera vez porque había que escribir los
tests que faltaban.

## Plan de contingencia ante la caída de una dependencia crítica

El módulo web depende de servicios que no controlamos. Para cada uno: cómo nos enteramos, qué le pasa al usuario,
qué se hace en el momento y qué prueba respalda ese comportamiento.

| Dependencia | Cómo se detecta | Qué ve el usuario | Respuesta inmediata | Recuperación | Respaldo en pruebas |
|---|---|---|---|---|---|
| **Supabase (base de datos)** | `/api/health` responde `db: error`; el smoke falla; `db/check_connection.py` falla en el pipeline | El panel carga, pero los datos se muestran como "—" y las acciones responden 503 ("sin conexión a la base de datos") | Se suspenden los deploys (criterio de suspensión del plan); nadie despliega hasta que vuelva | Si el proyecto gratuito se pausó por inactividad, reactivarlo desde el panel de Supabase; si es una caída de Supabase, esperar y volver a correr el pipeline | DEF-003 y DEF-008 (503 en vez de 500); el pool descarta conexiones rotas (`test_pool.py`); estados vacíos del panel (RNF-04) |
| **Supabase (Storage)** | Mapas de calor que no cargan | Sin imagen de mapa de calor en el plano | Ninguna en el módulo web: el pipeline de video guarda el mapa en `heatmaps_pendientes/` y la API lo sirve desde ahí | Se suben cuando Storage vuelve | DEF-002 (solo se sirven imágenes de esa carpeta) |
| **Render (hosting)** | El smoke del pipeline no responde; Render muestra el servicio caído | El panel no abre | Levantar la misma imagen Docker en la PC del local (`docker build -f docker/Dockerfile-optifull` y `docker run` con `DATABASE_URL`, como hace el job system-check) | Volver a desplegar en Render cuando vuelva; la imagen es la misma | El job system-check prueba esa misma imagen en cada push a `main` |
| **Render (arranque en frío)** | La primera respuesta tarda hasta ~1 min | Una primera carga lenta | Ninguna: es el comportamiento del plan gratuito | — | Timeouts de 90 s en las pruebas contra QA (riesgo R8) |
| **GitHub Actions** | El pipeline no corre | Nada: producción sigue con el último commit verificado | No se despliega. Si hay una urgencia, se corren las suites localmente (comandos del README) y se usa el Deploy Hook de Render a mano, dejándolo registrado | Volver a correr el pipeline cuando GitHub vuelva | — |
| **SonarQube Cloud** | El quality gate no puede consultar el análisis | Nada | El gate falla cerrado (`quality_gate.py` termina con error si no obtiene las medidas): no se despliega sin análisis | Volver a correr el job `calidad` | — |
| **Resend (aviso por email de los pedidos de demo)** | `POST /api/leads` responde 502; queda `aviso_email: false` en el registro | "No se pudo enviar el pedido. Probá de nuevo en un momento." | El pedido igual se guarda en `leads.jsonl` | Revisar `leads.jsonl` y avisar a mano a quienes pidieron la demo | `test_leads.py::test_si_el_email_falla_responde_502_pero_guarda` |

**Riesgo abierto detectado al armar este plan.** `leads.jsonl` se guarda en el disco del servidor, y en Render
gratuito ese disco se borra en cada deploy. Si Resend está caído, los pedidos de demo de ese período se pierden con
el siguiente deploy, y como la landing pide reintentar, los que sí se guardan pueden quedar duplicados. Queda
registrado como riesgo del plan de pruebas (R9 en [plan-de-pruebas.md](plan-de-pruebas.md)) y como hallazgo en
[04-metricas-y-analisis-estatico.md](04-metricas-y-analisis-estatico.md#hallazgos); la solución (guardar los
pedidos en Supabase) es un cambio de la tesis y no del TP.

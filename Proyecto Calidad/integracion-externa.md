# Integración externa del módulo de interfaz web

El módulo web se conecta con cuatro servicios externos. Para cada uno: qué usa, cuál es el contrato, cómo se prueba
(con dobles de prueba o contra el servicio real) y en qué paso del pipeline.

| Servicio | Para qué lo usa el módulo | Configuración |
|---|---|---|
| **Supabase: Postgres** | Base de datos de todo OptiFull: la API lee lo que escriben los pipelines de video y de caja (personas, visitas, alertas, mapas de calor, productos, usuarios) y escribe el login, las alertas resueltas, los empleados confirmados y el stock | `DATABASE_URL` (secret del environment `qa` y `production` en GitHub y variable del servicio en Render) |
| **Supabase: Storage** | Imágenes de los mapas de calor y de la evidencia de las alertas: la API devuelve sus URLs públicas | URLs guardadas en la base (`imagen_path`) |
| **Render** | Hosting de QA (`optifull-qa`) y producción (`optifull-prod`) con la misma imagen Docker | `render.yaml`; `RENDER_DEPLOY_HOOK_URL` (secret); `autoDeploy: false` |
| **Resend** | Aviso por email de cada pedido de demo de la landing | `RESEND_API_KEY` (variable del servicio en Render) |

## Supabase (Postgres)

**Contrato.** El esquema es `db/schema.sql`; la API se conecta con `psycopg2` a través de un pool de hasta 5
conexiones (`frontend/api/db.py`). Si la base no responde, `_get_conn()` devuelve `None` y cada endpoint responde
**503** con `{"error": "sin conexión a la base de datos"}`, nunca 500 (DEF-003, DEF-008).

**Cómo se prueba:**

| Nivel | Cómo | Dónde |
|---|---|---|
| Unitario (con doble de prueba) | `BDFalsa` en `test/conftest.py`: responde cada consulta según un fragmento del SQL; también simula la base caída y los errores | Todos los tests de la API, en build-test |
| Persistencia (real) | Postgres 16 temporal en el job build-test, creado con `db/schema.sql` en cada ejecución (nunca Supabase) | `test/bd/test_pool.py` |
| Integración (real) | El contenedor del módulo conectado a la **base de QA en Supabase** | `test/integracion/` en el job system-check |
| Integración en la plataforma (real) | El módulo desplegado en Render contra Supabase | `test/integracion/`, `test/e2e/` y `test/carga/` en integration-qa, e2e-qa y carga-qa |
| Salud de la conexión | `db/check_connection.py`: se conecta y verifica el esquema | Antes de system-check, deploy-qa y deploy-prod |

**Datos.** Las pruebas contra QA solo leen (y el login y la exportación, que no escriben datos de negocio). La
cuenta del pipeline (`QA_USUARIO`, rol empleado) se crea con `db/crear_usuario.py`. Producción solo recibe el smoke.

**Límites del plan gratuito.** Supabase pausa el proyecto tras días sin uso: el primer pedido tarda o falla hasta
que se reactiva (ver el plan de contingencia en [01-introduccion-calidad.md](01-introduccion-calidad.md)).

## Supabase (Storage)

**Contrato.** La API no sube archivos: devuelve la URL que guardaron los pipelines (`db._imagen_url()`). Si la
imagen quedó en el disco porque Storage no respondió, la API la sirve desde `heatmaps_pendientes/` o `evidencias/`,
y solo esas carpetas y solo imágenes (DEF-002, DEF-024).

**Cómo se prueba:** con dobles (URLs de Storage y rutas locales) en `test_heatmap.py` y `test_api_basica.py`; contra
el servicio real, cuando el E2E carga el dashboard en QA.

## Render

**Contrato.**

- **Despliegue:** el pipeline llama al Deploy Hook con el SHA exacto (`.github/scripts/deploy_render.sh`) y espera
  hasta 15 minutos a que el servicio corra ese commit.
- **Salud:** `GET /api/health` responde siempre 200 mientras el proceso esté vivo, con
  `{"status": "ok", "db": "ok" | "error", "commit": "<sha>", "env": "qa" | "production"}`. Render lo usa como
  `healthCheckPath`; el pipeline, para saber qué versión corre y si llega a la base.
- **Configuración por entorno:** `APP_ENV` (activa la cookie `Secure` y apaga el proxy de la cámara del local,
  DEF-023), `SECRET_KEY` (firma la cookie de sesión), `DATABASE_URL`.

**Cómo se prueba:**

| Qué | Prueba | Paso del pipeline |
|---|---|---|
| La imagen arranca y responde | Contenedor `optifull:ci` + `/api/health` + integración | system-check |
| QA corre el commit esperado | `test_health_corre_el_commit_esperado` (smoke, con `EXPECTED_COMMIT`) | integration-qa |
| La API exige sesión en la plataforma real | `test_la_api_exige_sesion` (smoke) | integration-qa y deploy-prod |
| El módulo aguanta la carga en la plataforma real | Locust: stress y sostenida | carga-qa |
| Producción corre el commit esperado | Smoke con `EXPECTED_COMMIT` | deploy-prod |

**Límites del plan gratuito.** 0,1 CPU y 512 MB: por eso gunicorn corre 1 worker con 4 hilos y por eso la conexión
por pedido saturaba el servicio (ver [pruebas-de-carga.md](pruebas-de-carga.md)). El servicio se duerme tras 15
minutos sin tráfico: las pruebas contra QA usan timeouts de 90 s.

## Resend

**Contrato.** `POST https://api.resend.com/emails` con la clave en la cabecera (`frontend/api/correo.py`). Si no hay
clave configurada no se envía nada y el pedido se guarda igual; si el envío falla, el pedido se guarda y la landing
responde 502.

**Cómo se prueba:** solo con dobles de prueba (`test_leads.py`: envío por Resend, por SMTP, sin configuración y con
falla). No hay prueba contra el servicio real: mandaría un email por cada ejecución. **Riesgo abierto:** si falla,
los pedidos quedan solo en el disco de Render, que se borra en cada deploy (riesgo R9).

## Secrets y variables

| Dónde | Nombre | Para qué |
|---|---|---|
| GitHub, environment `qa` | `DATABASE_URL`, `RENDER_DEPLOY_HOOK_URL`; variable `QA_URL` | Base de QA, deploy a QA |
| GitHub, environment `production` | `DATABASE_URL`, `RENDER_DEPLOY_HOOK_URL`; variable `PROD_URL` | Base de producción, deploy a producción (puede pedir aprobación manual) |
| GitHub, repositorio | `SONAR_TOKEN`, `QA_USUARIO`, `QA_CLAVE` | Análisis y quality gate; la cuenta con la que las pruebas inician sesión |
| Render, cada servicio | `APP_ENV`, `SECRET_KEY`, `DATABASE_URL`, `RESEND_API_KEY` | Configuración del servicio |

Ningún secret está en el repositorio ni se imprime en los logs del pipeline.

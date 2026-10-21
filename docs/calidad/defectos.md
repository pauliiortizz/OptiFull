# Registro de defectos

Todos los defectos encontrados desde que empezó el proceso de calidad (20/10/2026). Cada uno tiene un test de
regresión que falla sin el arreglo y pasa con él; el test lleva el número de defecto en su nombre o en un
comentario. El registro está cargado en Jira, en el proyecto **KAN** (DEF-001 = KAN-1 … DEF-022 = KAN-22:
[lista completa](https://optifull.atlassian.net/issues?jql=project%3DKAN%20ORDER%20BY%20key%20ASC)),
importado desde [`defectos-jira.csv`](defectos-jira.csv); la plantilla para cargar uno nuevo está en
[`plantillas.md`](plantillas.md).

**Severidad:** Crítica (expone datos o deja el sistema inutilizable), Alta (corta un flujo principal),
Media (un flujo funciona mal pero tiene alternativa), Baja (caso borde, mensaje o código de error incorrecto).

## Resumen

El TP de Calidad se enfoca en el **módulo de interfaz web** (`frontend/`, ver
[alcance-medicion.md](alcance-medicion.md)). Sus defectos son los de la primera tabla. Los de la segunda se
encontraron en los pipelines de video y de caja con el mismo proceso, y quedan registrados (también en Jira), pero
están fuera del alcance del TP.

### Módulo de interfaz web (alcance del TP)

| ID | Jira | Título | Severidad | Detectado por | Requisito | Commit rojo | Commit verde |
|---|---|---|---|---|---|---|---|
| DEF-001 | [KAN-1](https://optifull.atlassian.net/browse/KAN-1) | `fpdf2>=2.7` acepta versiones que rompen el PDF | Media | SonarCloud (análisis estático) | RF-13 | — | 7030358 |
| DEF-002 | [KAN-2](https://optifull.atlassian.net/browse/KAN-2) | `/api/heatmap/image` entrega cualquier archivo del proyecto (`.env`) | Crítica | Test unitario | RF-05, RF-06 | 22f4f21 | 4883562 |
| DEF-003 | [KAN-3](https://optifull.atlassian.net/browse/KAN-3) | `/heatmap/latest` y `/heatmap/camara` sin BD responden 500 en vez de 503 | Baja | Test unitario | RF-06 | 053ff7b | 053ff7b |
| DEF-004 | [KAN-4](https://optifull.atlassian.net/browse/KAN-4) | La API no exige iniciar sesión | Crítica | Revisión + test unitario | RF-14, RF-15 | 5bf2d25 | 5bf2d25 |
| DEF-005 | [KAN-5](https://optifull.atlassian.net/browse/KAN-5) | `Range: bytes=-N` en los videos da 500 | Baja | Test unitario | RF-15 | f91e6ac | f91e6ac |
| DEF-006 | [KAN-6](https://optifull.atlassian.net/browse/KAN-6) | Un `Range` más largo que el video anuncia bytes que no manda | Baja | Test unitario | RF-15 | f91e6ac | f91e6ac |
| DEF-007 | [KAN-7](https://optifull.atlassian.net/browse/KAN-7) | `?t=` / `?dur=` inválidos en los clips dan 500 en vez de 400 | Baja | Test unitario | RF-15 | f91e6ac | f91e6ac |
| DEF-008 | [KAN-8](https://optifull.atlassian.net/browse/KAN-8) | Con la base vacía, `/personas` y `/export/*` dan 500 | Baja | Test unitario | RF-13, RNF-04 | b690e97 | b690e97 |
| DEF-015 | [KAN-15](https://optifull.atlassian.net/browse/KAN-15) | Un error 500 de `/api/reportes/*` deja el Dashboard en blanco | Alta | Test del frontend | RF-14 | 7cad2e8 | 6b215ff |
| DEF-016 | [KAN-16](https://optifull.atlassian.net/browse/KAN-16) | Con `/api/stats` caído, la landing muestra el cuerpo del error como métricas | Baja | Test del frontend | RNF-04 | 34bb61b | 17d433a |
| DEF-017 | [KAN-17](https://optifull.atlassian.net/browse/KAN-17) | El formulario de la landing avisa "No se pudo enviar" sin haber enviado nada | Baja | Test del frontend | — (landing) | 34bb61b | 17d433a |
| DEF-018 | [KAN-18](https://optifull.atlassian.net/browse/KAN-18) | El menú lateral no se puede usar con el teclado | Media | Test del frontend | RF-14 | 7cad2e8 | 8a9a789 |
| DEF-020 | [KAN-20](https://optifull.atlassian.net/browse/KAN-20) | Sin Web Animations, el login y el formulario de la landing no se pueden enviar | Media | Tests del frontend (merge de `main`) | RF-14 | 671ef55 | 54a4e45 |
| DEF-021 | [KAN-21](https://optifull.atlassian.net/browse/KAN-21) | Sin visitantes, la conversión de compra muestra un 0 % inventado | Baja | Test del frontend (merge de `main`) | RNF-04 | 671ef55 | 54a4e45 |
| DEF-022 | [KAN-22](https://optifull.atlassian.net/browse/KAN-22) | Sin conexión, el formulario de la landing muestra "Failed to fetch" | Baja | Test del frontend (merge de `main`) | — (landing) | 671ef55 | 54a4e45 |
| DEF-023 | — | `/productos/camara` permite pedir URLs internas (SSRF: 127.0.0.1, metadatos de la nube) | Alta | SonarCloud (S5144) | RF-11 | dd6a07d | ffa1629 |
| DEF-024 | — | Los archivos del frontend dejan averiguar qué archivos hay en el servidor | Media | SonarCloud (S6549) | — (seguridad) | dd6a07d | ffa1629 |
| DEF-025 | — | `/productos/iniciar` lanza la caja con cualquier archivo o URL como fuente | Media | SonarCloud (S6350) | RF-11 | dd6a07d | ffa1629 |
| DEF-026 | — | El panel se puede incrustar en un sitio ajeno (clickjacking) | Baja | SonarCloud (S2819) | RF-14 | dd6a07d | ffa1629 |
| DEF-027 | — | `/api/video` deja leer carpetas vecinas con el mismo prefijo | Baja | Revisión de código | RF-15 | dd6a07d | ffa1629 |

Totales del módulo web: 2 críticos, 2 altos, 5 medios, 11 bajos (20). Todos corregidos.

DEF-020 a DEF-022 aparecieron al traer `main` a `Pau` (21/10/2026): el rediseño de la landing, el login y los
gráficos (08e12e6) los introdujo, y los tests que ya existían en `Pau` fallaron. El merge (39ea4e9) se
subió con los tests adaptados al diseño nuevo en rojo (671ef55) y los arreglos aparte (54a4e45). DEF-023 a
DEF-027 salieron de revisar las vulnerabilidades de SonarQube Cloud (ver la tabla al final).

### Otros módulos (fuera del alcance del TP)

| ID | Jira | Título | Severidad | Detectado por | Requisito | Commit rojo | Commit verde |
|---|---|---|---|---|---|---|---|
| DEF-009 | [KAN-9](https://optifull.atlassian.net/browse/KAN-9) | Comillas tipográficas dentro de un valor rompen el JSON del Re-ID | Media | Test unitario | RF-03 | 5aab42d | 5aab42d |
| DEF-010 | [KAN-10](https://optifull.atlassian.net/browse/KAN-10) | El schema no tiene `personas.zona_id`: en una base nueva falla `auditar_sesion()` | Alta | Test contra Postgres real | RF-12 | 7c0e13a | 7c0e13a |
| DEF-011 | [KAN-11](https://optifull.atlassian.net/browse/KAN-11) | `--webcam --screen` sin valor se acepta y gana la pantalla | Baja | Test E2E de `main.py` | RF-01 | d0308c8 | d0308c8 |
| DEF-012 | [KAN-12](https://optifull.atlassian.net/browse/KAN-12) | Las opciones de RTSP se aplican también a videos grabados (se pierde el primer frame) | Baja | Test E2E de `main.py` | RF-01 | d0308c8 | d0308c8 |
| DEF-013 | [KAN-13](https://optifull.atlassian.net/browse/KAN-13) | Una respuesta rara del LLM (confianza `null`, números como texto, JSON que no es objeto) corta la caja | Alta | Test unitario | RF-10, RF-11 | 0ca8501 | 4fc3052 |
| DEF-014 | [KAN-14](https://optifull.atlassian.net/browse/KAN-14) | Un producto con tamaño 0 en el catálogo produce una división por cero y corta la caja | Media | Test unitario | RF-11 | 0ca8501 | 4fc3052 |
| DEF-019 | [KAN-19](https://optifull.atlassian.net/browse/KAN-19) | La caja no arranca con el SDK de Anthropic 1.x (`import httpx`) | Alta | Pipeline (build-test en rojo) | RF-10 | a7bbe9f | 92585b1 |

Totales: 0 críticos, 3 altos, 2 medios, 2 bajos (7). Todos corregidos.

Cuando el commit rojo y el verde son el mismo, el test y el arreglo se subieron juntos; el test se verificó en
rojo localmente antes del arreglo. En el módulo web, los defectos con commits distintos se usaron para el
contraste rojo/verde en el pipeline: DEF-002 (el primero), DEF-020 a DEF-022 y DEF-023 a DEF-027.

## Detalle

### DEF-001 · `fpdf2>=2.7` acepta versiones que rompen el PDF
- **Pasos:** instalar las dependencias con `fpdf2==2.7.0` (lo permite `frontend/requirements.txt`) y exportar un reporte en PDF.
- **Esperado:** se genera el PDF.
- **Obtenido:** `pdf.table(padding=...)` falla: el parámetro `padding` recién existe desde fpdf2 2.7.6.
- **Arreglo:** `fpdf2>=2.7.6`. SonarCloud sigue marcando las dos líneas (su referencia de la librería es vieja); se marcaron como *falso positivo* con la justificación.
- **Regresión:** `test_reportes_formatos.py` genera los PDFs con tablas (`reportes_formatos.py`, que usa `padding`) con la versión que se instala en CI.

### DEF-002 · `/api/heatmap/image` entrega cualquier archivo del proyecto
- **Pasos:** `GET /api/heatmap/image/archivo_secreto_prueba.env` y `GET /api/heatmap/image/frontend/api/db.py`.
- **Esperado:** 404: el endpoint solo sirve imágenes de mapas de calor.
- **Obtenido:** 200 con el contenido del `.env` (en la PC del local: `DATABASE_URL` de Supabase, claves de los LLM) y con código fuente.
- **Regresión:** `test_heatmap.py::test_no_sirve_archivos_que_no_son_imagenes_de_heatmap`.

### DEF-003 · Heatmap sin base de datos responde 500
- **Pasos:** con la base caída, `GET /api/heatmap/latest` y `GET /api/heatmap/camara/1`.
- **Esperado:** 503 "sin conexión a la base de datos", como el resto de la API.
- **Obtenido:** 500 `'NoneType' object has no attribute 'cursor'`.
- **Regresión:** `test_heatmap.py::test_sin_base_de_datos_responde_503`.

### DEF-004 · La API no exige iniciar sesión
- **Pasos:** sin haber iniciado sesión, `GET /api/personas`, `/api/alertas`, `POST /api/productos/...`.
- **Esperado:** 401.
- **Obtenido:** 200 con datos; cualquiera con la URL podía leer personas y alertas o descontar stock.
- **Regresión:** `test_sesion.py` (32 tests) y el smoke `test_sistema.py::test_la_api_exige_sesion`, que corre en QA y en producción.

### DEF-005, DEF-006, DEF-007 · Videos y clips
- **Pasos:** `Range: bytes=-50` (DEF-005); un `Range` que pide más bytes que el archivo (DEF-006); `/api/sessions/1/clip?t=abc` (DEF-007).
- **Esperado:** los últimos 50 bytes; el rango recortado al último byte (o 416 si es imposible); 400.
- **Obtenido:** 500; la respuesta anuncia 999 bytes y manda 100 (algunos reproductores se cuelgan); 500.
- **Regresión:** 18 tests en `test_video.py`.

### DEF-008 · Base vacía en `/personas` y `/export/*`
- **Pasos:** con las tablas vacías, `GET /api/personas` y `GET /api/export/csv`.
- **Esperado:** 200 con lista vacía / un reporte sin filas.
- **Obtenido:** 500.
- **Regresión:** `test_api_basica.py::test_exportar_con_la_base_vacia_genera_el_reporte_sin_filas` y siguientes.

### DEF-009 · Comillas tipográficas en el JSON del Re-ID
- **Pasos:** el LLM responde un descriptor con un valor como `"remera “Nike”"`.
- **Esperado:** se interpreta el JSON.
- **Obtenido:** falla el parseo y la persona no se reidentifica.
- **Regresión:** `test_reid.py` (casos DEF-009).

### DEF-010 · Falta `personas.zona_id` en el schema
- **Pasos:** crear una base nueva con `db/schema.sql` y cerrar una sesión de video.
- **Esperado:** `auditar_sesion()` audita y fusiona las personas entre cámaras.
- **Obtenido:** falla entera (`column "zona_id" does not exist`).
- **Regresión:** `test/bd/test_persistencia_*.py`, que corren contra un Postgres creado con `schema.sql` en cada ejecución del pipeline.

### DEF-011 y DEF-012 · Opciones de `deteccion/main.py`
- **Pasos:** `python main.py --webcam --screen` (DEF-011); analizar un video grabado (DEF-012).
- **Esperado:** error por combinar dos modos; se analiza desde el primer frame.
- **Obtenido:** se usa la pantalla; las opciones de RTSP (`fflags;nobuffer`) se aplican al importar y se pierde el primer frame.
- **Regresión:** `test/bd/test_main_e2e.py`.

### DEF-013 y DEF-014 · La caja se corta con datos mal formados
- **Pasos:** el LLM devuelve `confianza: null`, `"tamano": "500ml"`, números como texto o un JSON que es una lista (DEF-013); el catálogo tiene un producto con `tamano_valor = 0` (DEF-014).
- **Esperado:** el dato ilegible cuenta como faltante y la caja sigue mirando la cámara.
- **Obtenido:** una excepción en `identificar()` corta el loop del orquestador ("Error inesperado").
- **Regresión:** `test_caja_matching.py` y `test_caja_vision.py` (tests `test_def013_*`, `test_def014_*`).

### DEF-015 · Dashboard en blanco ante un error de reportes
- **Pasos:** `/api/reportes/congestion-horaria` responde 500 y se abre el Dashboard.
- **Esperado:** el panel se muestra y ese gráfico queda "sin datos".
- **Obtenido:** pantalla en blanco: el cuerpo del error se tomaba como datos y no hay *error boundary*.
- **Regresión:** `App.test.jsx` › "un error 500 de congestion-horaria no deja el panel en blanco".

### DEF-016 y DEF-017 · Landing pública
- **Pasos:** `/api/stats` responde con error (DEF-016); en el formulario, enviar sin elegir el problema y después elegirlo (DEF-017).
- **Esperado:** "Las métricas todavía no están disponibles."; el aviso desaparece al elegir.
- **Obtenido:** cifras vacías con el badge de "Ya funcionando"; aparece "No se pudo enviar" sin haber enviado nada.
- **Regresión:** `LandingPage.test.jsx`.

### DEF-018 · Menú lateral sin teclado
- **Pasos:** en el panel, recorrer con Tab y activar una sección con Enter.
- **Esperado:** cada sección recibe el foco y se abre con Enter.
- **Obtenido:** los items eran `<a>` sin `href`: no reciben foco.
- **Regresión:** `Sidebar.test.jsx` (DEF-018).

### DEF-019 · La caja no arranca con el SDK de Anthropic 1.x
- **Pasos:** instalación nueva de `deteccion_productos` (`pip install -r requirements.txt`, que hoy instala `anthropic` 1.16) y `python main.py --source ...`.
- **Esperado:** arranca la caja.
- **Obtenido:** `ModuleNotFoundError: No module named 'httpx'`. Desde la 1.x el SDK usa `httpx2`, y aunque se instale `httpx` el SDK rechaza un `httpx.Limits`.
- **Cómo se detectó:** el job build-test del pipeline quedó en rojo desde 4fc3052 (en CI se instalan las dependencias de cero); en las PCs del equipo andaba porque tenían un SDK viejo. (Pipeline de caja: fuera del alcance del TP.)
- **Arreglo:** los límites de conexión se arman con la clase de `anthropic.DEFAULT_CONNECTION_LIMITS`, que es la del paquete que usa el SDK instalado.
- **Regresión:** `test_caja_vision.py::test_def019_*`.

### DEF-020 · Sin Web Animations no se puede ingresar
- **Pasos:** en un navegador sin `Element.animate` (o en jsdom), abrir el login y tocar "Ingresar", con o sin datos.
- **Esperado:** valida los campos e inicia sesión; el estirón del botón es decorativo.
- **Obtenido:** `TypeError: el.animate is not a function` dentro del submit: no se valida ni se envía nada. Lo mismo en el formulario de la landing.
- **Arreglo:** `estira()` (`efectos/seguir.js`) no hace nada si el elemento no tiene `animate`.
- **Regresión:** `seguir.test.js` › "DEF-020: sin Web Animations no hace nada y no tira error".

### DEF-021 · Conversión de compra en 0 % sin datos
- **Pasos:** `/api/reportes/conversion-compra` responde `pct_conversion: null` (un día con datos, sin visitantes) y se abre el Dashboard.
- **Esperado:** el anillo de conversión muestra "—" (RNF-04).
- **Obtenido:** "0%": el componente recibía `pct ?? 0`.
- **Regresión:** `ReportMetrics.test.jsx` › "conversión con un solo día usa singular".

### DEF-022 · "Failed to fetch" en la landing
- **Pasos:** sin conexión, completar el pedido de demo y enviarlo.
- **Esperado:** "No se pudo enviar. Probá de nuevo en un momento."
- **Obtenido:** "Failed to fetch": se mostraba el mensaje de cualquier error, también el del navegador.
- **Arreglo:** solo se muestra el mensaje cuando lo manda el servidor.
- **Regresión:** `LandingPage.test.jsx` › "sin conexión avisa que no se pudo enviar".

### DEF-023 · SSRF en el proxy de la cámara del celular
- **Pasos:** con sesión iniciada, `GET /api/productos/camara?url=http://169.254.169.254/latest/meta-data/` (o `http://127.0.0.1:8080/...`).
- **Esperado:** 400: solo cámaras de la red local del negocio.
- **Obtenido:** el servidor hace el pedido. `ipaddress.is_private` es True también para 127.0.0.1, 0.0.0.0 y 169.254.x, así que pasaban el control. En Render, además, la cámara del local nunca es alcanzable: el endpoint solo servía para eso.
- **Arreglo:** `seguridad.es_ip_de_red_local()` excluye loopback, link-local, 0.0.0.0, multicast y reservadas; en QA y producción el endpoint responde 404.
- **Regresión:** `test_seguridad.py::test_def023_*`.

### DEF-024 · Oráculo de archivos en el servidor
- **Pasos:** sin sesión, `GET /../api/paths.py` y `GET /../api/no_existe.py`.
- **Esperado:** la misma respuesta para las dos.
- **Obtenido:** 404 si el archivo existe fuera de `dist/` y 200 (la SPA) si no: desde internet se podía saber si hay un `.env`, qué módulos tiene la API, etc.
- **Arreglo:** `ruta_dentro()` (safe_join): una ruta que sale de `dist/` cae al fallback de la SPA.
- **Regresión:** `test_seguridad.py::test_def024_*`.

### DEF-025 · Fuente de la caja sin validar
- **Pasos:** con sesión (también de empleado), `POST /api/productos/iniciar` con `{"source": "../secreto.env"}`, `{"source": "http://8.8.8.8/x"}` o `{"roi": "a,b,c,d"}`.
- **Esperado:** 400.
- **Obtenido:** se lanza el proceso de la caja, que abre la fuente con OpenCV/ffmpeg (leen archivos del disco y piden URLs).
- **Arreglo:** solo cámaras de la red local (http, rtsp) o videos de `deteccion_productos/data/videos` y `videos/`; `roi` con formato `x1,y1,x2,y2`.
- **Regresión:** `test_seguridad.py::test_def025_*` (también los casos válidos que usa la caja web).

### DEF-026 · Clickjacking
- **Pasos:** un sitio ajeno muestra el panel en un `<iframe>` y le manda `postMessage({type: '__activate_edit_mode'})`.
- **Esperado:** el navegador no deja incrustar el panel.
- **Obtenido:** ninguna respuesta lo prohibía, y `TweaksPanel.jsx` aceptaba mensajes de cualquier origen.
- **Arreglo:** `X-Frame-Options: SAMEORIGIN`, `Content-Security-Policy: frame-ancestors 'self'` y `X-Content-Type-Options: nosniff` en todas las respuestas; `TweaksPanel` solo escucha mensajes en desarrollo.
- **Regresión:** `test_seguridad.py::test_def026_*` y `TweaksPanel.test.jsx` › "fuera de desarrollo no escucha mensajes".

### DEF-027 · Carpetas vecinas en `/api/video`
- **Pasos:** con sesión, `GET /api/video/../videos_privado/x.mp4` (existe una carpeta `videos_privado` al lado de `videos`).
- **Esperado:** 403.
- **Obtenido:** se sirve el archivo: el control era `startswith('.../videos')`, y `.../videos_privado/x.mp4` empieza igual.
- **Arreglo:** `safe_join`.
- **Regresión:** `test_seguridad.py::test_def027_*`.

## Revisión de vulnerabilidades de SonarQube Cloud (21/10/2026)

El quality gate frena bugs críticos, no vulnerabilidades: estas 10 estaban abiertas con el gate en OK. Se revisó
cada una contra el código y con una prueba; las reales se corrigieron (con su test en rojo primero) y las demás
se marcan en SonarQube Cloud con esta justificación.

| # | Regla | Severidad | Dónde | Veredicto |
|---|---|---|---|---|
| 1 | S5144 SSRF | Mayor | `productos.py` `camara()` | **Real → DEF-023** |
| 2 | S6549 Filesystem oracle | Mayor | `__init__.py` `static_files()` | **Real → DEF-024** (probado: 404 vs 200) |
| 3 | S6350 Command argument injection | Mayor | `productos.py` `iniciar()` | **Real → DEF-025**. No hay inyección de comandos (se pasa una lista, sin shell), pero la fuente y el roi no se validaban |
| 4 | S2819 postMessage sin origen (recibir) | Crítica | `TweaksPanel.jsx:121` | **Real → DEF-026** como clickjacking; el listener ahora es solo de desarrollo. SonarQube lo va a seguir marcando: *Safe*, porque en el build de producción no se registra y el servidor prohíbe incrustar el panel |
| 5 | S2819 postMessage sin origen (enviar) | Crítica | `TweaksPanel.jsx:122` | Igual que el 4: solo en desarrollo, y el mensaje (`__edit_mode_available`) no lleva datos |
| 6 | S6549 Filesystem oracle | Mayor | `alertas.py` `servir_evidencia()` | **Falso positivo**: responde 404 exista o no el archivo de afuera (probado). Igual se pasó a `ruta_dentro()` |
| 7 | S4502 CSRF desactivado | Crítica | `__init__.py` | **Falso positivo**: la cookie de sesión es `SameSite=Lax` (el navegador no la manda en un POST desde otro sitio), ningún `GET` modifica datos y la API recibe JSON, que desde otro origen exige un *preflight* CORS que el servidor no autoriza |
| 8 | S2245 Pseudoaleatorio | Mayor | `Sparkline.jsx` | **Falso positivo**: era el id de un degradado SVG. Se cambió por `useId()` |
| 9 | S2245 Pseudoaleatorio | Mayor | `Toast.jsx` | **Falso positivo**: era el id de un aviso en pantalla. Se cambió por un contador |
| 10 | S5332 http inseguro | Menor | `ProductosPage.jsx` | **Falso positivo**: es la URL de ejemplo de la cámara del celular en la red local; la app de la cámara (IP Camera Lite) solo ofrece http y el proxy no existe fuera del local (DEF-023) |


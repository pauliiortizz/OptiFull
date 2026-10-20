# Registro de defectos

Todos los defectos encontrados desde que empezó el proceso de calidad (20/10/2026). Cada uno tiene un test de
regresión que falla sin el arreglo y pasa con él; el test lleva el número de defecto en su nombre o en un
comentario. El mismo registro está en [`defectos-jira.csv`](defectos-jira.csv) para importarlo en Jira
(*Configuración del sistema → Importación externa → CSV*), y la plantilla para cargar uno nuevo está en
[`plantillas.md`](plantillas.md).

**Severidad:** Crítica (expone datos o deja el sistema inutilizable), Alta (corta un flujo principal),
Media (un flujo funciona mal pero tiene alternativa), Baja (caso borde, mensaje o código de error incorrecto).

## Resumen

| ID | Título | Severidad | Detectado por | Requisito | Commit rojo | Commit verde |
|---|---|---|---|---|---|---|
| DEF-001 | `fpdf2>=2.7` acepta versiones que rompen el PDF | Media | SonarCloud (análisis estático) | RF-13 | — | 7030358 |
| DEF-002 | `/api/heatmap/image` entrega cualquier archivo del proyecto (`.env`) | Crítica | Test unitario | RF-05, RF-06 | 22f4f21 | 4883562 |
| DEF-003 | `/heatmap/latest` y `/heatmap/camara` sin BD responden 500 en vez de 503 | Baja | Test unitario | RF-06 | 053ff7b | 053ff7b |
| DEF-004 | La API no exige iniciar sesión | Crítica | Revisión + test unitario | RF-14, RF-15 | 5bf2d25 | 5bf2d25 |
| DEF-005 | `Range: bytes=-N` en los videos da 500 | Baja | Test unitario | RF-15 | f91e6ac | f91e6ac |
| DEF-006 | Un `Range` más largo que el video anuncia bytes que no manda | Baja | Test unitario | RF-15 | f91e6ac | f91e6ac |
| DEF-007 | `?t=` / `?dur=` inválidos en los clips dan 500 en vez de 400 | Baja | Test unitario | RF-15 | f91e6ac | f91e6ac |
| DEF-008 | Con la base vacía, `/personas` y `/export/*` dan 500 | Baja | Test unitario | RF-13, RNF-04 | b690e97 | b690e97 |
| DEF-009 | Comillas tipográficas dentro de un valor rompen el JSON del Re-ID | Media | Test unitario | RF-03 | 5aab42d | 5aab42d |
| DEF-010 | El schema no tiene `personas.zona_id`: en una base nueva falla `auditar_sesion()` | Alta | Test contra Postgres real | RF-12 | 7c0e13a | 7c0e13a |
| DEF-011 | `--webcam --screen` sin valor se acepta y gana la pantalla | Baja | Test E2E de `main.py` | RF-01 | d0308c8 | d0308c8 |
| DEF-012 | Las opciones de RTSP se aplican también a videos grabados (se pierde el primer frame) | Baja | Test E2E de `main.py` | RF-01 | d0308c8 | d0308c8 |
| DEF-013 | Una respuesta rara del LLM (confianza `null`, números como texto, JSON que no es objeto) corta la caja | Alta | Test unitario | RF-10, RF-11 | 0ca8501 | 4fc3052 |
| DEF-014 | Un producto con tamaño 0 en el catálogo produce una división por cero y corta la caja | Media | Test unitario | RF-11 | 0ca8501 | 4fc3052 |
| DEF-015 | Un error 500 de `/api/reportes/*` deja el Dashboard en blanco | Alta | Test del frontend | RF-14 | 7cad2e8 | 6b215ff |
| DEF-016 | Con `/api/stats` caído, la landing muestra el cuerpo del error como métricas | Baja | Test del frontend | RNF-04 | 34bb61b | 17d433a |
| DEF-017 | El formulario de la landing avisa "No se pudo enviar" sin haber enviado nada | Baja | Test del frontend | — (landing) | 34bb61b | 17d433a |
| DEF-018 | El menú lateral no se puede usar con el teclado | Media | Test del frontend | RF-14 | 7cad2e8 | 8a9a789 |
| DEF-019 | La caja no arranca con el SDK de Anthropic 1.x (`import httpx`) | Alta | Pipeline (build-test en rojo) | RF-10 | a7bbe9f | 92585b1 |

Totales: 2 críticos, 5 altos, 4 medios, 8 bajos. Todos corregidos.

Cuando el commit rojo y el verde son el mismo, el test y el arreglo se subieron juntos; el test se verificó en
rojo localmente antes del arreglo. Los defectos con commits distintos se usaron para el contraste rojo/verde en el
pipeline: DEF-002 (el primero) y DEF-019 (detectado por el propio pipeline, ver más abajo).

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
- **Cómo se detectó:** el job build-test del pipeline quedó en rojo desde 4fc3052 (en CI se instalan las dependencias de cero); en las PCs del equipo andaba porque tenían un SDK viejo. Es la **ejecución fallida que detectó un problema real**.
- **Arreglo:** los límites de conexión se arman con la clase de `anthropic.DEFAULT_CONNECTION_LIMITS`, que es la del paquete que usa el SDK instalado.
- **Regresión:** `test_caja_vision.py::test_def019_*`.

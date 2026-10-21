# 5 · Pruebas dinámicas

Los casos se diseñan desde la especificación (caja negra) y se completan mirando el código (caja blanca, con la
cobertura de sentencia y de decisión). Cada caso se documenta con la plantilla IEEE 829 de
[plantillas.md](plantillas.md): entradas y precondiciones, resultado esperado, postcondiciones y dependencias, y el
test automatizado que lo ejecuta.

## Clases de equivalencia

### CP-VID-01 · Parámetros `t` y `dur` de `/api/sessions/<id>/clip` (RF-15)

| Campo | Contenido |
|---|---|
| Precondiciones | Sesión 1 con su video en disco; base de datos simulada |
| Clases válidas | CE1: `t` número ≥ 0 · CE2: `dur` número > 0 |
| Clases no válidas, formato correcto fuera de rango | CE3: `t` negativo (`t=-1`) · CE4: `dur` ≤ 0 (`dur=0`, `dur=-5`) |
| Clases no válidas, formato erróneo | CE5: texto (`t=abc`, `dur=diez`) · CE6: no finitos (`t=nan`, `dur=inf`) |
| Resultado esperado | CE1, CE2 → 200 con el clip · CE3 a CE6 → 400, **sin consultar la base de datos** |
| Postcondiciones | Ninguna (lectura) |
| Test | `test_video.py::test_clip_con_parametros_invalidos_responde_400` (un caso por clase no válida) |
| Defecto asociado | DEF-007: antes `t=abc` respondía 500 |

### CP-CAJ-01 · Fuente de video de `/api/productos/iniciar` (RF-11)

| Clase | Representante | Esperado |
|---|---|---|
| CE1 válida: video de `deteccion_productos/data/videos` | `data/videos/prueba.mp4` | 200, se lanza la caja |
| CE2 válida: video de `videos/` (lo que manda la caja web) | `../videos/caja.mp4` | 200 |
| CE3 válida: cámara de la red local por http | `http://admin:admin@192.168.0.10:8081/video` | 200 |
| CE4 válida: cámara IP de la red local por rtsp | `rtsp://10.0.0.7:554/stream` | 200 |
| CE5 no válida: archivo fuera de las carpetas permitidas | `../secreto.env`, `../videos/../secreto.env` | 400, no se lanza nada |
| CE6 no válida: video que no existe | `data/videos/no_existe.mp4` | 400 |
| CE7 no válida: URL de internet o del propio servidor | `http://8.8.8.8/stream`, `http://127.0.0.1:8080/...`, `rtsp://169.254.169.254/x` | 400 |
| CE8 no válida: otro esquema u opción de línea de comandos | `file:///etc/passwd`, `--help` | 400 |

Test: `test_seguridad.py::test_def025_*` (un parámetro por representante). Defecto asociado: DEF-025.

## Valores límite

Para cada límite se prueba el valor límite y su vecino del otro lado.

### CP-LOG-01 · Bloqueo del login por intentos fallidos

Regla: tras `LIMITE_FALLOS = 5` intentos fallidos seguidos de un mismo usuario, se bloquea durante
`BLOQUEO_SEG = 300` segundos (429), incluso con la clave correcta.

| Valor | Esperado | Test (`test_login.py`) |
|---|---|---|
| 4 fallos (límite − 1) y la clave correcta | 200: todavía puede entrar, y el contador vuelve a cero | `test_un_ingreso_correcto_reinicia_el_contador` |
| 5 fallos (el límite) y la clave correcta | 429 "Probá de nuevo en 5 minutos" | `test_se_bloquea_tras_los_intentos_fallidos_y_no_deja_pasar_ni_con_la_clave_correcta` |
| 301 s después del bloqueo (límite + 1) | 200 | `test_el_bloqueo_vence_con_el_tiempo` |
| Campos vacíos | No cuentan como intento fallido | `test_los_campos_vacios_no_cuentan_como_intento_fallido` |

**Límite sin probar:** exactamente 300 s después del bloqueo. La especificación no dice si el segundo 300 todavía
está bloqueado; queda como pregunta para el requisito (justo lo que advierte la teoría: los límites suelen estar
mal definidos).

### CP-VID-02 · Cabecera `Range` de un video de 1024 bytes (bytes 0 a 1023)

| Valor | Esperado | Test (`test_video.py`) |
|---|---|---|
| `bytes=1023-1023` (el último byte solo) | 206 con 1 byte | `test_video_parcial_con_range` |
| `bytes=1024-` (el primero fuera del archivo) | 416 | `test_range_imposible_de_satisfacer_responde_416` |
| `bytes=1000-5000` (el fin pasa del archivo) | 206, recortado a 1000-1023 (DEF-006) | `test_range_mas_largo_que_el_archivo_se_recorta` |
| `bytes=-0` (sufijo de cero bytes) | 416 | `test_range_imposible_de_satisfacer_responde_416` |
| `bytes=-5000` (sufijo más largo que el archivo) | 206 con el archivo entero | `test_range_mas_largo_que_el_archivo_se_recorta` |

### CP-VID-03 · Parámetros `t` y `dur` en sus límites

| Valor | Esperado |
|---|---|
| `t=-1` / `t=0` | 400 / válido |
| `dur=0` / `dur` positivo | 400 / válido |

## Tabla de decisión

**CP-PER-01 · Qué sección ve cada rol** (`frontend/src/components/permisos.js`). Condiciones: el rol de la sesión y
el tipo de sección pedida. Acción: mostrar la sección o redirigir a la sección inicial del rol.

| Regla | Rol | Sección pedida | Acción | Test (`permisos.test.js`) |
|---|---|---|---|---|
| 1 | Administrador | Cualquiera del panel | Mostrar | "el administrador ve todas las secciones" |
| 2 | Empleado | Operativa (Productos, Alertas) | Mostrar | "el empleado solo ve productos y alertas" |
| 3 | Empleado | De análisis o sistema (Dashboard, Reportes, Config) | Redirigir a Productos | "paginaPermitida redirige a la inicial…" |
| 4 | Desconocido, vacío o ausente | Cualquiera | No mostrar nada | "un rol desconocido, vacío o ausente no ve nada" |
| 5 | Cualquiera | Una que no existe | No mostrar | "una sección inexistente nunca está permitida" |

Las reglas 2 y 3 se verifican además de punta a punta: el E2E con la cuenta de empleado de QA comprueba que el menú
no muestre Dashboard, Reportes ni Config.

## Transición de estados

**CP-LAN-01 · Formulario de pedido de demo de la landing** (`LandingPage.jsx`, estado `envio`):

```
              elegir opción                      respuesta 201                 1,5 s (animación)
 ┌──────┐ ◄──────────────── ┌────────────────┐                ┌─────────┐ ─────────────────► ┌────┐
 │ idle │ ── enviar sin ──► │ falta_problema │    ┌─────────► │  listo  │                    │ ok │  (final)
 └──────┘    opción         └────────────────┘    │           └─────────┘                    └────┘
    │                                             │
    │ enviar con opción    ┌───────────┐ ─────────┘
    └────────────────────► │ enviando  │
                           └───────────┘ ─── 4xx/5xx o sin red ──► ┌───────┐ ── enviar ──► enviando
                                                                    │ error │
                                                                    └───────┘
```

| Camino | Transiciones | Test (`LandingPage.test.jsx`) |
|---|---|---|
| 1 | idle → enviando → listo → ok | "envía el pedido con los datos del formulario y los utm del link, y confirma" |
| 2 | idle → falta_problema | "sin elegir qué resolver pide elegirlo y no envía nada" |
| 3 | idle → falta_problema → idle (al elegir) | "al elegir la opción que faltaba no aparece un falso error de envío" (DEF-017) |
| 4 | idle → enviando → error → enviando → listo → ok | "si el servidor rechaza el pedido avisa y permite reintentar" |
| 5 | idle → enviando → error (sin red) | "sin conexión avisa que no se pudo enviar" (DEF-022) |
| Inválida | enviando → enviando (doble envío) | "mientras envía deshabilita el botón para no duplicar el pedido" |

**CP-LOG-02 · Bloqueo del login** (por usuario): `habilitado` → (fallo, n < 5) → `habilitado` con n fallos →
(5.º fallo) → `bloqueado` → (pasan 300 s) → `habilitado` con n = 0. Un ingreso correcto desde `habilitado` vuelve n
a 0. Los cuatro caminos son los casos de CP-LOG-01.

## Casos de uso

Los dos casos de uso principales del panel se prueban de punta a punta con el E2E contra QA
(`test/e2e/test_flujo_completo.py`):

| | CU-01 · El administrador consulta y exporta | CU-02 · El empleado atiende la caja |
|---|---|---|
| Actor | Dueño o gerente (rol administrador) | Empleado (rol usuario) |
| Precondiciones | Cuenta activa; QA desplegado con el commit a probar | Cuenta activa; QA desplegado |
| Flujo | Login → Dashboard con los datos de la base → Reportes: todas las métricas en CSV → descarga → Alertas → Cerrar sesión | Login → Productos con el stock de la base (sin Dashboard, Reportes ni Config en el menú) → Alertas → Cerrar sesión |
| Postcondiciones | La sesión deja de valer (`/api/personas` responde 401); ningún 5xx ni error de JavaScript durante el recorrido | Lo mismo |
| Hoy en QA | No se ejecuta: la cuenta del pipeline es de empleado (para cubrirlo hace falta una cuenta de administrador en `QA_USUARIO`) | ✅ Se ejecuta en cada deploy |

## Cobertura de sentencia y de decisión

Medidas por el pipeline (pytest-cov con `branch = true` y Vitest con V8) e importadas en SonarQube Cloud:

| | Sentencias (líneas) | Decisiones (ramas) | Combinada (SonarQube Cloud) |
|---|---|---|---|
| API (`frontend/api`) | 98,5 % | 96,0 % | 98,0 % |
| Panel (`frontend/src`) | 94,7 % | 87,9 % | 91,6 % |
| Módulo web (`frontend/`) | 96,8 % | 90,2 % | 94,5 % |

La cobertura de decisión es siempre más baja que la de sentencia: una línea con un `if` puede ejecutarse sin que se
recorran sus dos ramas. Las ramas sin cubrir más interesantes no son las que faltan probar, sino las que no se
pueden probar: la rama defensiva de `_stream_video()` (ver
[04-metricas-y-analisis-estatico.md](04-metricas-y-analisis-estatico.md#flujo-de-control)).

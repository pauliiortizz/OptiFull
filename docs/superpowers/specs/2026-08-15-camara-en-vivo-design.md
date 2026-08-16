# Cámara en vivo para el pipeline de detección de personas — Diseño

Fecha: 2026-08-15
Alcance: Fase 1 (webcam de PC). Fase 2 (iPhone) queda preparada en la
arquitectura pero no se implementa en esta iteración.

## Contexto

`deteccion/main.py` orquesta hoy YOLO+ByteTrack -> `PersonTracker`
(Re-ID local + nube) -> `HeatmapBuilder` -> `Persistencia` (Supabase),
leyendo siempre un archivo de video vía `cv2.VideoCapture(config.VIDEO_PATH)`
en un loop síncrono. La única visualización con boxes/tracking
IDs/heatmap/zonas es una ventana local de OpenCV (`cv2.imshow`,
activada por `config.SHOW_PREVIEW`) que se dibuja mientras corre el
análisis. El dashboard web (`frontend/`) solo reproduce el `.mp4` ya
guardado y grafica trayectorias post-análisis; no hay overlay de
detecciones en el navegador.

`deteccion_productos/` (pipeline de productos en caja, no tocado por
este trabajo) ya demuestra que `cv2.VideoCapture` funciona igual para
archivo, índice de webcam o URL de streaming — precedente reutilizado
para el diseño de abajo.

## Objetivo

Permitir correr el pipeline de `deteccion/` contra la webcam de la PC
en tiempo real, reutilizando toda la lógica de detección/tracking/
heatmap/zonas/overlay ya existente, sin duplicar código y sin romper
el modo archivo actual. El modo cámara **no persiste en la base de
datos** (Postgres/Supabase) — es una vista previa local para validar
que el pipeline funciona antes de decidir si algún día se persiste.

## Arquitectura

### `VideoSource` (nuevo módulo `deteccion/pipeline/video_source.py`)

```
VideoSource (ABC)
 ├── open() / read() -> (ok, frame) / release()
 ├── fps: float
 ├── frame_w, frame_h: int
 ├── total_frames: int | None   (None = fuente sin fin conocido)
 └── is_live: bool

FileVideoSource(path)
    Envuelve cv2.VideoCapture(path). Mismo comportamiento que hoy:
    lectura secuencial síncrona, total_frames conocido, is_live=False.

WebcamVideoSource(device, resolution=None, target_fps=None)
    Hilo de captura en background que sobreescribe SIEMPRE un único
    slot con el último frame leído (lock, sin cola). read() del
    consumidor devuelve lo más reciente disponible; si la inferencia
    es más lenta que la cámara, los frames viejos se descartan solos
    -- nunca se acumula backlog. total_frames=None, is_live=True.
    Maneja apertura fallida (cámara no encontrada / ocupada / sin
    permisos) con un RuntimeError de mensaje claro, y reintentos
    acotados si `read()` empieza a fallar (cámara desconectada en
    caliente) antes de levantar error.
```

`WebcamVideoSource` queda escrita para que una futura `IphoneVideoSource`
comparta la misma base de captura por hilo — la diferencia entre ambas
es solo qué se le pasa a `cv2.VideoCapture` (índice de dispositivo vs.
URL de red MJPEG/RTSP). Ninguna lógica de threading/backpressure se
duplicaría al agregarla.

### Refactor de `deteccion/main.py`

Se extrae del loop principal una función `_procesar_frame(...)` con
todo lo que hoy vive inline por iteración (YOLO `.track()`,
`tracker.procesar_frame`, acumulación de heatmap, cálculo de zona,
cercanía a caja, interacción con producto, muestreo de trayectoria,
overlay de preview). La usan **tanto el modo archivo como el modo
cámara** sin duplicar nada; `main()` deja de abrir `cv2.VideoCapture`
directo y en cambio recibe/crea un `VideoSource`.

Se agrega un CLI (`argparse`, mismo patrón que ya usa
`deteccion_productos/main.py`):

```
python deteccion/main.py                  # sin cambios: usa config.VIDEO_PATH
python deteccion/main.py --webcam         # cámara integrada (device 0)
python deteccion/main.py --webcam 1       # otro índice de cámara
```

### Modo cámara = sin persistencia

Se reutiliza el camino que YA existe para "sin conexión a BD" (el
mismo que corre hoy un video sin `camara_id` detectable, o con
`SOLO_LEER_ZONAS`): `Persistencia.*` ya es no-op sin conexión abierta,
así que no hace falta ningún `if` nuevo para esto. En modo `--webcam`:
- No se crea `camara_id` ni sesión en BD.
- Corren igual: tracking local (ByteTrack + Re-ID por apariencia),
  heatmap acumulado en memoria, overlay con boxes/IDs/heatmap.
- Re-ID en la nube (Gemini/Groq/Claude) queda deshabilitado por
  default en modo cámara (para no gastar cupo de API en pruebas
  locales) vía un override de `USAR_*_REID`, configurable.
- Al cortar (tecla `q` o Ctrl+C), se libera la cámara y el hilo de
  captura se detiene; no hay sesión que borrar en BD porque nunca se
  creó una.

### Rendimiento y controles

- Captura en hilo aparte, slot de 1 frame → nunca se acumula cola;
  se prioriza siempre el frame más reciente si el modelo es más
  lento que la cámara.
- FPS de procesamiento real (promedio móvil de los últimos ~30
  frames) dibujado en el overlay, mismo estilo visual que el texto
  "Frame N/M" que ya existe para archivo.
- Teclas en la ventana existente: `q` detiene y libera la cámara;
  `p` pausa/reanuda (nuevo, congela el frame mostrado sin cerrar la
  cámara).
- Mensajes `[INFO]`/`[ERROR]` claros para: cámara no encontrada,
  cámara en uso por otra aplicación, sin permisos, cámara que deja
  de responder.

### Config nueva (`deteccion/config.py`)

`WEBCAM_DEVICE_INDEX` (default 0), `WEBCAM_RESOLUTION` (opcional,
`None` = la que dé la cámara), `WEBCAM_TARGET_FPS` (opcional),
`WEBCAM_USAR_REID_NUBE` (default `False`). Reutiliza `CONF` existente
para el umbral de confianza de detección. `FRAME_SKIP` no aplica en
vivo: el descarte de frames atrasados ya lo hace el buffer de 1 slot
de `WebcamVideoSource`.

## Fuera de alcance (fase 1)

- Persistencia de sesiones de cámara en vivo en la BD.
- iPhone como fuente (`IphoneVideoSource`) — solo se deja la
  arquitectura lista; se implementa en una iteración separada.
- Cualquier UI web nueva — el modo cámara se maneja igual que el modo
  archivo hoy: por línea de comandos, con la ventana de OpenCV como
  visualización.

## Compatibilidad

El modo archivo (`python deteccion/main.py` sin flags) queda
byte-a-byte equivalente al comportamiento actual: mismo
`FileVideoSource` envolviendo el mismo `cv2.VideoCapture`, mismo
`FRAME_SKIP`, misma persistencia, mismo overlay. El refactor de
`_procesar_frame` no cambia ningún resultado, solo reubica código ya
existente para poder reutilizarlo desde el modo cámara.

## iPhone (fase 2 — solo diseño, no implementado ahora)

Alternativa recomendada: **stream MJPEG/RTSP servido por una app de
IP-camera en el iPhone**, consumido directo con
`cv2.VideoCapture(url)` (OpenCV ya trae el backend FFmpeg necesario
para HTTP/RTSP — sin dependencias nuevas). Se descarta WebRTC: agrega
señalización, servidores STUN/TURN y una librería nueva (`aiortc`)
por una reducción de latencia irrelevante para un caso de uso de
analítica de seguridad (no es video-llamada). Cuando se implemente,
`IphoneVideoSource(url)` hereda la misma base de captura por hilo que
`WebcamVideoSource`, sin duplicar lógica de threading/backpressure.

"""Orquestador del pipeline: YOLO+ByteTrack -> PersonTracker (Re-ID local +
Gemini) -> HeatmapBuilder -> Persistencia (Supabase) -> reporte de metricas."""
import argparse
import signal
import sys
import threading
import os
import time
# RTSP por TCP (UDP pierde paquetes y rompe el decodificado H264/H265) y con
# poco buffer para que el frame leido sea el mas reciente. Tiene que estar
# seteado ANTES de que cv2 abra la primera captura.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay")
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from datetime import datetime

import cv2
from ultralytics import YOLO

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from deteccion import config, utils
from deteccion.pipeline import metricas, eventos
from deteccion.reid.gemini_reid import GeminiReID
from deteccion.reid.groq_reid import GroqReID
from deteccion.reid.claude_reid import ClaudeReID
from deteccion.pipeline.tracking import PersonTracker
from deteccion.pipeline.video_source import FileVideoSource, WebcamVideoSource, ScreenVideoSource
from deteccion.pipeline.heatmap import (
    HeatmapBuilder, combinar_grids, calcular_stats_grid, codificar_combinado,
)
from deteccion.persistencia import Persistencia
from deteccion.pipeline.storage import SupabaseStorage
from deteccion.pipeline.evidencia import GrabadorEvidencia, publicar_evidencia
from deteccion.pipeline.fotos import CapturadorFotos


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline de deteccion: YOLO+ByteTrack -> PersonTracker -> Heatmap.",
    )
    parser.add_argument(
        "--webcam", nargs="?", const=None, default=False, metavar="DEVICE",
        help="Usa la camara en vivo de la PC en vez de config.VIDEO_PATH. Sin "
             "valor usa config.WEBCAM_DEVICE_INDEX; opcionalmente se puede "
             "pasar un indice de dispositivo, ej. --webcam 1. El modo camara "
             "NUNCA persiste en la base de datos ni en Supabase Storage.",
    )
    parser.add_argument(
        "--screen", nargs="?", const=None, default=False, metavar="MONITOR",
        help="Analiza la pantalla en vivo (ej. una videollamada de Google "
             "Meet abierta en el navegador) en vez de config.VIDEO_PATH. Dejar "
             "la ventana/pestana de Meet visible en el monitor elegido ANTES "
             "de correr esto. Sin valor usa config.SCREEN_MONITOR_INDEX; "
             "opcionalmente se puede pasar el indice de otro monitor, ej. "
             "--screen 2. Mismo modo que --webcam: NUNCA persiste en la base "
             "de datos ni en Supabase Storage. No se puede combinar con "
             "--webcam.",
    )
    parser.add_argument(
        "--rtsp", type=int, choices=sorted(config.CAMARA_NOMBRES), default=None, metavar="CAMARA_ID",
        help="Analiza en vivo la camara RTSP con ese id (1-4), tomando la URL de "
             "RTSP_URL_<id> en .env. A diferencia de --webcam/--screen, ESTE modo "
             "SI persiste en la BD (sesion, personas, trayectorias, eventos y "
             "heatmap), de forma incremental. Ctrl+C o 'q' cierra y guarda.",
    )
    args = parser.parse_args()
    if sum(x is not False and x is not None for x in (args.webcam, args.screen, args.rtsp)) > 1:
        parser.error("--webcam, --screen y --rtsp no se pueden usar juntos.")
    return args


def _fps_actual(muestras: deque) -> float:
    """FPS de procesamiento real (no el nominal de la camara), calculado
    sobre las marcas de tiempo de los ultimos frames PROCESADOS (ver
    fps_muestras en main()). Con menos de 2 muestras no hay intervalo que
    medir todavia."""
    if len(muestras) < 2:
        return 0.0
    return (len(muestras) - 1) / (muestras[-1] - muestras[0])


HEATMAPS_PENDIENTES_DIR = "heatmaps_pendientes"  # respaldo local (ignorado por git, ver .gitignore)


def _subir_o_guardar_local(storage: SupabaseStorage, path: str, contenido: bytes) -> str:
    """Sube 'contenido' a Supabase Storage bajo 'path' (con un reintento tras una
    pausa breve); si Storage no esta configurado o la subida falla las dos veces,
    lo guarda localmente en HEATMAPS_PENDIENTES_DIR (con el path aplanado a nombre
    de archivo) para no perder el analisis. Devuelve la URL o la ruta relativa local
    (el backend sirve esa ruta bajo /api/heatmap/image/)."""
    url = storage.subir_png(path, contenido)
    if not url and storage.enabled:
        time.sleep(2)
        url = storage.subir_png(path, contenido)
    if url:
        print(f"[Heatmap] Subido a Supabase Storage: {url}")
        return url
    os.makedirs(HEATMAPS_PENDIENTES_DIR, exist_ok=True)
    local_path = f"{HEATMAPS_PENDIENTES_DIR}/{path.replace('/', '_')}"
    with open(local_path, "wb") as f:
        f.write(contenido)
    print(f"[Heatmap] Storage no disponible, guardado local: {local_path}")
    return local_path


def main() -> None:
    args = _parse_args()
    modo_pantalla = args.screen is not False
    modo_rtsp = args.rtsp is not None
    # modo_camara = fuentes en vivo que NUNCA persisten (webcam/pantalla).
    # modo_vivo = cualquier fuente sin fin conocido (incluye RTSP, que si persiste).
    modo_camara = (args.webcam is not False) or modo_pantalla
    modo_vivo = modo_camara or modo_rtsp
    archivo_label = config.VIDEO_PATH
    webcam_device = config.WEBCAM_DEVICE_INDEX if args.webcam is None else int(args.webcam)
    screen_monitor = config.SCREEN_MONITOR_INDEX if args.screen is None else int(args.screen)
    # SHOW_PREVIEW puede estar en False en config.py (uso normal con video de
    # archivo, sin ventana) -- en modo camara la ventana esta prendida por
    # default: ver todo en vivo es el objetivo del modo. En modo pantalla es
    # al reves (config.SCREEN_MOSTRAR_PREVIEW=False por default): cv2.imshow
    # tambien consume CPU que compite con la videollamada que se esta
    # analizando, asi que ahi el preview es opt-in.
    if modo_pantalla:
        mostrar_preview = config.SCREEN_MOSTRAR_PREVIEW
    elif modo_rtsp:
        mostrar_preview = config.RTSP_MOSTRAR_PREVIEW
    elif modo_camara:
        mostrar_preview = True
    else:
        mostrar_preview = config.SHOW_PREVIEW

    # ── Determinar camara e inicio de grabacion ────────────────────────────────
    if modo_camara:
        camara_id = None
        inicio_dt = datetime.now()
        if modo_pantalla:
            print(f"[INFO] Modo pantalla en vivo (monitor={screen_monitor}) -- NO se "
                  f"va a persistir nada en la base de datos ni en Supabase Storage. "
                  f"Dejar la ventana/pestana a analizar (ej. Google Meet) visible en "
                  f"ese monitor.")
        else:
            print(f"[INFO] Modo camara en vivo (device={webcam_device}) -- NO se va "
                  f"a persistir nada en la base de datos ni en Supabase Storage. Es "
                  f"solo una vista previa local del pipeline.")
    elif modo_rtsp:
        camara_id = args.rtsp
        inicio_dt = datetime.now()
        rtsp_url = config.RTSP_URLS.get(camara_id)
        if not rtsp_url:
            print(f"[ERROR] Falta RTSP_URL_{camara_id} en .env.")
            return
        # Nunca se guarda la URL real en la BD (lleva usuario:clave).
        archivo_label = f"rtsp://camara_{camara_id}/{inicio_dt:%Y%m%d_%H%M%S}"
        print(f"[INFO] Modo RTSP en vivo -- camara {camara_id} "
              f"({config.CAMARA_NOMBRES[camara_id][0]}). SI se persiste en la BD.")
    else:
        try:
            camara_id = config.CAMARA_ID_OVERRIDE or utils.parse_camara_id(config.VIDEO_PATH)
            inicio_dt = utils.parse_inicio(config.VIDEO_PATH)
            print(f"Camara detectada : {camara_id}  (desde '{Path(config.VIDEO_PATH).name}')")
            print(f"Inicio grabacion : {inicio_dt}")
        except ValueError as e:
            print(f"[AVISO] {e}")
            camara_id = None
            inicio_dt = datetime.now()

    # ── Conexion a BD, zonas y sesion ───────────────────────────────────────────
    persistencia = Persistencia(
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS, config.CAMARA_NOMBRES,
        config.GRUPOS_CAMARA, config.REID_VENTANA_HORAS,
    )
    storage = SupabaseStorage(
        config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, config.SUPABASE_BUCKET, config.HAS_SUPABASE_STORAGE
    )
    conectado = persistencia.conectar() if camara_id else False

    # Frena ACA (antes de cargar el modelo y abrir el video) si un video con
    # este MISMO NOMBRE DE ARCHIVO ya fue analizado -- evita duplicar
    # personas/trayectorias/heatmaps. Compara solo el nombre, no la ruta
    # completa (la carpeta o la letra de unidad puede cambiar, ej. un mismo
    # pendrive montado como D: o como E: segun la PC).
    if conectado and not config.SOLO_LEER_ZONAS and not modo_rtsp:
        sesion_existente = persistencia.buscar_sesion_por_archivo(config.VIDEO_PATH)
        if sesion_existente:
            print(f"\n[AVISO] Ya existe un video analizado con el mismo nombre de archivo "
                  f"('{Path(config.VIDEO_PATH).name}') -- no se va a procesar de nuevo "
                  f"para no duplicar los datos.")
            print(f"        Sesion existente : id={sesion_existente['id']}, "
                  f"camara={sesion_existente['camara_id']}, inicio={sesion_existente['inicio']}")
            print(f"        Ruta ya analizada: '{sesion_existente['archivo_path']}'")
            print(f"        Ruta actual      : '{config.VIDEO_PATH}'")
            print(f"        Revisa la ruta del video en config.py (VIDEO_PATH) -- "
                  f"si en verdad es un video distinto, asegurate de que tenga un nombre de archivo diferente.")
            persistencia.cerrar()
            return

    if modo_camara and config.WEBCAM_CAMARA_ID_ZONAS is not None:
        # Carga de zonas en modo SOLO LECTURA para que el overlay las pueda
        # dibujar -- mismo patron que SOLO_LEER_ZONAS: conecta, lee, corta.
        # Nunca crea sesion ni escribe nada (coherente con modo_camara).
        zonas = persistencia.cargar_zonas(config.WEBCAM_CAMARA_ID_ZONAS) if persistencia.conectar() else []
        if persistencia.conn:
            persistencia.conn.close()
            persistencia.conn = None
    else:
        zonas = persistencia.cargar_zonas(camara_id) if conectado else []

    if zonas:
        zonas_de = config.WEBCAM_CAMARA_ID_ZONAS if modo_camara else camara_id
        print(f"[DB] {len(zonas)} zonas cargadas para camara {zonas_de}: {[z['nombre'] for z in zonas]}")
    else:
        print(f"[DB] Sin zonas definidas para esta corrida.")

    if conectado and config.SOLO_LEER_ZONAS:
        # Ya se leyeron las zonas -- se corta la conexion ACA, antes de crear
        # la sesion. Todo Persistencia.* de aca en mas es no-op sin conexion
        # (ver docstring del modulo), asi que el resto del analisis corre
        # entero sin escribir ninguna fila en la BD.
        print("[DB] SOLO_LEER_ZONAS activo -- se corta la conexion. El resto del "
              "analisis NO va a escribir nada en la BD.")
        persistencia.conn.close()
        persistencia.conn = None
        conectado = False

    sesion_id = persistencia.crear_sesion(camara_id, inicio_dt, archivo_label) if conectado else None
    # En vivo (RTSP) una caida de internet no puede dejar el analisis sin guardar: se reconecta sola.
    persistencia.reconectar_automaticamente = bool(modo_rtsp and conectado)

    # Mapas id->tipo/nombre para la clasificacion Escenario A/B/C (ver
    # pipeline/eventos.py) y para decidir en que zonas vale la pena correr la
    # deteccion de producto (solo tipo='gondola' -- Gondola/Heladera del
    # local, ver PRODUCTO_CLASES_COCO en config.py).
    zona_tipo_por_id   = {z["id"]: z["tipo"]   for z in zonas}
    zona_nombre_por_id = {z["id"]: z["nombre"] for z in zonas}

    # A partir de aca hay una sesion creada en la BD (si conectado): si el
    # analisis se interrumpe por lo que sea (Ctrl+C, cupo de API agotado,
    # excepcion no manejada, etc.) antes de llegar al final, se borra la
    # sesion completa (personas/trayectorias/visitas incluidas via CASCADE)
    # en vez de dejarla a medio procesar contaminando el Re-ID y los reportes.
    try:
        # ── Inicializacion modelo y video ───────────────────────────────────────────
        repo_root      = Path(__file__).resolve().parent.parent
        tracker_config = str(repo_root / "bytetrack_custom.yaml")

        model        = YOLO(config.RTSP_MODELO if modo_rtsp else "yolov8n.pt")
        # Modelo APARTE para detectar productos (clases COCO de config.PRODUCTO_CLASES_COCO)
        # -- nunca se llama con .track()/persist=True, asi que no pisa el estado de
        # tracking de 'model' (ver utils.detectar_productos). Se usa perezosamente, solo
        # cuando alguna persona esta parada en una zona tipo='gondola' este frame.
        model_productos = YOLO("yolov8n.pt")

        if modo_pantalla:
            source = ScreenVideoSource(
                monitor=screen_monitor,
                region=config.SCREEN_REGION,
                target_fps=config.SCREEN_TARGET_FPS,
                scale=config.SCREEN_SCALE,
            )
        elif modo_rtsp:
            source = WebcamVideoSource(
                device=rtsp_url,
                etiqueta=f"RTSP camara {camara_id}",
                timeout_primer_frame_seg=15.0,
                reconectar_hasta_seg=config.RTSP_RECONECTAR_HASTA_SEG,
                descartar_repetidos=True,
                timeout_lectura_ms=config.RTSP_TIMEOUT_LECTURA_MS,
            )
        elif modo_camara:
            source = WebcamVideoSource(
                device=webcam_device,
                resolution=config.WEBCAM_RESOLUTION,
                target_fps=config.WEBCAM_TARGET_FPS,
            )
        else:
            source = FileVideoSource(config.VIDEO_PATH)
        source.open()

        fps          = config.RTSP_TARGET_FPS if modo_rtsp else source.fps
        frame_w      = source.frame_w
        frame_h      = source.frame_h
        # Zonas dibujadas sobre 1920x1080: se llevan al tamano real del frame (RTSP = 640x360).
        zonas = utils.escalar_zonas(zonas, frame_w, frame_h, *config.ZONAS_REF_RESOLUCION)
        total_frames = source.total_frames  # None en modo camara
        # En modo camara no hay FRAME_SKIP: WebcamVideoSource ya descarta los
        # frames atrasados solo (siempre entrega el mas reciente), asi que no
        # hace falta el muestreo por FRAME_SKIP que si necesita un archivo (ahi
        # cada frame de un video ya grabado hay que decidir si se procesa).
        # frame_skip_efectivo=1 mantiene correctas las conversiones seg->frames
        # de mas abajo (caja_frames_minimos, tracker.frame_skip, etc.).
        frame_skip_efectivo = 1 if modo_vivo else config.FRAME_SKIP
        persistencia.actualizar_resolucion_sesion(sesion_id, frame_w, frame_h)

        max_dist            = frame_w * config.MAX_DIST_RATIO
        caja_distancia_px   = frame_w * config.CAJA_APROXIMACION_RATIO
        # Frames PROCESADOS (no crudos) por segundo real de video, para
        # convertir CAJA_PERMANENCIA_MINIMA_SEG a un contador de frames
        # consecutivos -- mismo criterio que INTERACCION_FRAMES_MINIMOS pero
        # partiendo de segundos en vez de un numero de frames fijo.
        caja_frames_minimos = max(1, round(config.CAJA_PERMANENCIA_MINIMA_SEG * fps / frame_skip_efectivo))
        quick_expiry_frames = int(config.QUICK_EXPIRY_SEC * fps)
        long_expiry_frames  = int(config.LONG_EXPIRY_SEC * fps)
        frames_a_procesar   = (total_frames // frame_skip_efectivo) if total_frames is not None else None

        if modo_pantalla:
            print(f"\nPantalla en vivo: monitor={screen_monitor}"
                  + (f", region={config.SCREEN_REGION}" if config.SCREEN_REGION else ""))
            print(f"Resolucion      : {frame_w}x{frame_h}  |  {fps:.0f}fps (nominal)")
        elif modo_rtsp:
            print(f"\nRTSP en vivo    : camara {camara_id}")
            print(f"Resolucion      : {frame_w}x{frame_h}  |  procesando a {fps:.1f}fps")
        elif modo_camara:
            print(f"\nCamara en vivo  : device={webcam_device}")
            print(f"Resolucion      : {frame_w}x{frame_h}  |  {fps:.0f}fps (nominal)")
        else:
            print(f"\nVideo           : {config.VIDEO_PATH}")
            print(f"Resolucion      : {frame_w}x{frame_h}  |  {fps:.0f}fps  |  {total_frames:,} frames")
            print(f"Frames a leer   : {frames_a_procesar:,}  (frame_skip={frame_skip_efectivo})")
        print()

        # ── Construccion de los componentes del pipeline ────────────────────────────
        heatmap = HeatmapBuilder(frame_w, frame_h, config.GAUSSIAN_RADIUS)

        # En modo camara, Re-ID en la nube esta apagado por default (config.
        # WEBCAM_USAR_REID_NUBE=False) para no gastar cupo de API en pruebas
        # locales -- el tracking local (ByteTrack + apariencia) sigue andando
        # igual. Se puede prender en config.py si se quiere probar tambien.
        permitir_reid_nube = (config.RTSP_USAR_REID_NUBE if modo_rtsp
                              else (not modo_camara) or config.WEBCAM_USAR_REID_NUBE)
        if not permitir_reid_nube:
            print("[ReID] Modo camara en vivo: Re-ID en la nube desactivado por "
                  "default (config.WEBCAM_USAR_REID_NUBE=False) -- tracking local "
                  "+ heatmap sin gastar cupo de API.")

        # Proveedor de Re-ID en la nube: Gemini o Groq (config.REID_PROVIDER), ambos
        # con la misma interfaz (.activo, .generar_descripcion(), .clasificar()) asi
        # que PersonTracker no necesita saber cual esta usando.
        if config.REID_PROVIDER == "groq":
            gemini = GroqReID(
                usar_groq_reid=config.USAR_GROQ_REID and permitir_reid_nube,
                has_groq=config.HAS_GROQ,
                api_keys=config.GROQ_API_KEYS,
                model=config.GROQ_MODEL,
                min_intervalo_seg=config.GROQ_MIN_INTERVALO_SEG,
                rafaga_umbral=config.GROQ_RAFAGA_UMBRAL,
                pausa_rafaga_seg=config.GROQ_PAUSA_RAFAGA_SEG,
                ventana_rafaga_seg=config.GROQ_VENTANA_RAFAGA_SEG,
                coincidencias_minimas=config.GROQ_COINCIDENCIAS_MINIMAS,
                umbral_mismo_momento_seg=config.UMBRAL_MISMO_MOMENTO_SEG,
            )
        elif config.REID_PROVIDER == "claude":
            gemini = ClaudeReID(
                usar_claude_reid=config.USAR_CLAUDE_REID and permitir_reid_nube,
                has_claude=config.HAS_CLAUDE,
                api_keys=config.CLAUDE_API_KEYS,
                model=config.CLAUDE_MODEL,
                min_intervalo_seg=config.CLAUDE_MIN_INTERVALO_SEG,
                rafaga_umbral=config.CLAUDE_RAFAGA_UMBRAL,
                pausa_rafaga_seg=config.CLAUDE_PAUSA_RAFAGA_SEG,
                ventana_rafaga_seg=config.CLAUDE_VENTANA_RAFAGA_SEG,
                coincidencias_minimas=config.CLAUDE_COINCIDENCIAS_MINIMAS,
                umbral_mismo_momento_seg=config.UMBRAL_MISMO_MOMENTO_SEG,
            )
        else:
            gemini = GeminiReID(
                usar_gemini_reid=config.USAR_GEMINI_REID and permitir_reid_nube,
                has_gemini=config.HAS_GEMINI,
                api_keys=config.GEMINI_API_KEYS,
                model=config.GEMINI_MODEL,
                min_intervalo_seg=config.GEMINI_MIN_INTERVALO_SEG,
                rafaga_umbral=config.GEMINI_RAFAGA_UMBRAL,
                pausa_rafaga_seg=config.GEMINI_PAUSA_RAFAGA_SEG,
                ventana_rafaga_seg=config.GEMINI_VENTANA_RAFAGA_SEG,
                coincidencias_minimas=config.GEMINI_COINCIDENCIAS_MINIMAS,
                umbral_mismo_momento_seg=config.UMBRAL_MISMO_MOMENTO_SEG,
            )
        print(f"[ReID] Proveedor configurado: {config.REID_PROVIDER}  (activo={gemini.activo})")

        def _on_descripcion(sid, frame_num, metodo, descripcion, cliente_id_hint):
            return persistencia.guardar_descripcion_persona(
                sesion_id, sid, frame_num, fps, inicio_dt, metodo, descripcion, cliente_id_hint,
            )

        def _obtener_candidatos_dia(excluir_ids, frame_num):
            momento = utils.frame_to_dt(frame_num, fps, inicio_dt)
            return persistencia.candidatos_reid_del_dia(momento, camara_id, excluir_ids), momento

        def _on_nueva_persona(sid, frame_num, metodo, cliente_id_hint):
            return persistencia.crear_persona(
                sesion_id, sid, frame_num, fps, inicio_dt, metodo, cliente_id_hint,
            )

        # Evidencia de los posibles hurtos (solo en vivo): ver pipeline/evidencia.py. Guarda en memoria los ultimos
        # segundos de imagenes; la subida de frames y clip se hace en un hilo aparte (no frena el analisis).
        grabador = None
        if modo_rtsp and config.EVIDENCIA_ACTIVA:
            grabador = GrabadorEvidencia(
                fps=fps, camara_id=camara_id, buffer_seg=config.EVIDENCIA_BUFFER_SEG,
                pre_seg=config.EVIDENCIA_PRE_SEG, post_seg=config.EVIDENCIA_POST_SEG,
                salida_seg=config.EVIDENCIA_SALIDA_SEG, frames_clave=config.EVIDENCIA_FRAMES_CLAVE,
            )
            persistencia.on_alerta_creada = lambda alerta_id, evidencia: threading.Thread(
                target=publicar_evidencia,
                args=(storage, config.DATABASE_URL, alerta_id, evidencia, config.EVIDENCIA_CLIP_FPS),
                daemon=True,
            ).start()

        # Foto de cada persona que lleva un rato en camara: sirve para que el usuario decida, desde la alerta
        # "Persona posiblemente empleada", si es empleado o no (ver pipeline/fotos.py).
        fotos = None
        if modo_rtsp and config.FOTOS_ACTIVAS and config.DATABASE_URL:
            fotos = CapturadorFotos(storage, config.DATABASE_URL, fps, config.FOTO_MIN_SEG)

        def _on_visita_cerrada(sid, frame_inicio, frame_fin, secuencia_zonas, tomo_producto, acerco_a_caja):
            persona_db_id = tracker.sid_to_persona_db_id.get(sid)
            visita_id = persistencia.guardar_visita(persona_db_id, frame_inicio, frame_fin, fps, inicio_dt)
            if not secuencia_zonas:
                if grabador:
                    grabador.liberar(sid)
                return  # sin zonas registradas en toda la visita, no hay nada que clasificar
            evento = eventos.clasificar_evento(secuencia_zonas, tomo_producto, acerco_a_caja, zona_nombre_por_id)
            # Se imprime SIEMPRE (haya BD conectada o no, ver SOLO_LEER_ZONAS) --
            # guardar_evento() es un no-op silencioso sin conexion, y sin este
            # print no habria forma de ver el resultado de la clasificacion.
            print(f"[Evento] Persona {sid}: {evento['accion_detectada']} -- {eventos.resumen_evento(evento)}")
            evidencia = None
            if grabador:
                # Posible hurto: se arma la evidencia (frames + clip); cualquier otra visita descarta lo reservado.
                if evento["es_sospechoso"]:
                    evidencia = grabador.construir(sid, frame_fin)
                else:
                    grabador.liberar(sid)
            persistencia.guardar_evento(persona_db_id, visita_id, evento, frame_fin, fps, inicio_dt, evidencia=evidencia)

        tracker = PersonTracker(
            frame_skip=frame_skip_efectivo,
            max_dist=max_dist,
            quick_expiry_frames=quick_expiry_frames,
            long_expiry_frames=long_expiry_frames,
            appearance_thresh=config.APPEARANCE_THRESH,
            max_app_samples=config.MAX_APP_SAMPLES,
            descripcion_streak_frames=config.DESCRIPCION_STREAK_FRAMES,
            min_frames_confirmacion=config.MIN_FRAMES_CONFIRMACION,
            gemini=gemini,
            on_descripcion=_on_descripcion,
            obtener_candidatos_dia=_obtener_candidatos_dia,
            on_nueva_persona=_on_nueva_persona,
            on_visita_cerrada=_on_visita_cerrada,
            interaccion_frames_minimos=config.INTERACCION_FRAMES_MINIMOS,
            caja_frames_minimos=caja_frames_minimos,
        )

        traj_buffer            = []
        ultimo_muestreo_traj    = {}   # sid -> frame_count del ultimo punto de trayectoria guardado
        muestreo_traj_frames    = max(1, int(fps * config.TRAYECTORIA_INTERVALO_SEG))
        last_frame      = None
        frame_count     = 0
        preview_counter = 0
        fps_muestras    = deque(maxlen=30)  # timestamps de los ultimos frames PROCESADOS (FPS en vivo)
        pausado         = False

        # Ctrl+C en RTSP no aborta: marca el corte para salir del loop y
        # pasar por el cierre normal (guardar personas/heatmap, cerrar sesion).
        detener = {"pedido": False}
        if modo_rtsp:
            signal.signal(signal.SIGINT, lambda *_: detener.update(pedido=True))
        intervalo_rtsp = 1.0 / config.RTSP_TARGET_FPS
        reloj_vivo     = [inicio_dt]  # indice 0 sin uso (frame_count arranca en 1)
        if modo_rtsp:
            utils.set_reloj_vivo(reloj_vivo)
        proximo_tick   = time.perf_counter()
        ultimo_flush   = ultimo_heatmap = ultimo_fusion = time.monotonic()

        def guardar_heatmaps(fin_dt, frames_procesados):
            """Heatmap de la sesion + combinado de la camara (upsert: se puede
            llamar varias veces durante una sesion en vivo sin duplicar)."""
            if heatmap.esta_vacio():
                print("[Heatmap] Acumulador vacio, no se guarda en BD.")
                return
            stats      = heatmap.calcular_stats(zonas, config.HEATMAP_UMBRAL, config.HEATMAP_GRID)
            ts_str     = inicio_dt.strftime("%Y%m%d_%H%M%S")
            puro_bytes = heatmap.codificar_puro(stats["hm_norm"])
            imagen_url = _subir_o_guardar_local(storage, f"camara_{camara_id}/{ts_str}.png", puro_bytes)

            persistencia.guardar_heatmap(
                camara_id, sesion_id, inicio_dt, fin_dt, stats,
                imagen_url, heatmap.total_detecciones, frames_procesados,
            )

            # Combinar con las sesiones previas de esta camara
            sesiones_previas = persistencia.obtener_matrices_camara(camara_id)
            if sesiones_previas:
                grid_size = sesiones_previas[0]["resolucion_x"] or config.HEATMAP_GRID
                combinado = combinar_grids(sesiones_previas, grid_size)
                stats_cam = calcular_stats_grid(combinado, zonas, config.HEATMAP_UMBRAL, frame_w, frame_h)
                cam_bytes = codificar_combinado(stats_cam["hm_norm"], frame_w, frame_h)
                cam_url   = _subir_o_guardar_local(storage, f"camara_{camara_id}/combinado.png", cam_bytes)
                persistencia.guardar_heatmap_camara(
                    camara_id, stats_cam, cam_url,
                    sum(s["total_detecciones"] for s in sesiones_previas),
                    sum(s["frames_procesados"] for s in sesiones_previas),
                    len(sesiones_previas),
                )

        pbar = tqdm(total=frames_a_procesar, unit="fr", desc="Analizando") if tqdm else None

        # ── Loop principal ──────────────────────────────────────────────────────────
        while True:
            if modo_rtsp:
                if detener["pedido"]:
                    print("\n[INFO] Corte pedido (Ctrl+C) -- cerrando y guardando...")
                    break
                restante = proximo_tick - time.perf_counter()
                if restante > 0:
                    time.sleep(restante)
                proximo_tick = max(proximo_tick, time.perf_counter()) + intervalo_rtsp

            if modo_vivo and pausado:
                # Pausa: no se lee ni procesa. La camara sigue viva en su hilo
                # de background (WebcamVideoSource sigue capturando), asi que
                # al reanudar se retoma con el frame mas reciente disponible,
                # no con uno atrasado. La ventana queda congelada en el ultimo
                # frame ya dibujado hasta que se reanuda.
                tecla = cv2.waitKey(50) & 0xFF
                if tecla == ord('q'):
                    break
                if tecla == ord('p'):
                    pausado = False
                    print("[INFO] Reanudado.")
                continue

            ret, frame = source.read()

            if modo_vivo:
                error = source.error()
                if error:
                    print(f"[ERROR] {error}")
                    break

            if not ret:
                break
            if modo_vivo and frame is None:
                continue   # sin frame nuevo (stream en pausa o reconectando): no se reprocesa el anterior

            frame_count += 1
            if modo_rtsp:
                reloj_vivo.append(datetime.now())  # reloj_vivo[n] = hora real del frame n
            if not modo_vivo and frame_count % frame_skip_efectivo != 0:
                continue

            last_frame = frame
            fps_muestras.append(time.perf_counter())

            if pbar is not None:
                pbar.update(1)
            elif not modo_vivo and frame_count % (frame_skip_efectivo * 500) == 0:
                pct = frame_count / total_frames * 100
                print(f"  {pct:.1f}%  [{utils.to_timestamp(frame_count, fps)}]", end="\r")

            results = model.track(
                frame,
                classes=[0],
                conf=config.RTSP_CONF if modo_rtsp else config.CONF,
                imgsz=config.RTSP_IMGSZ if modo_rtsp else 640,
                tracker=tracker_config,
                persist=True,
                verbose=False,
            )

            detecciones = tracker.procesar_frame(frame, frame_count, results)
            if grabador:
                grabador.registrar_frame(frame_count, utils.frame_to_dt(frame_count, fps, inicio_dt), frame, detecciones)

            # Cache de productos detectados en ESTE frame -- se calcula perezosamente
            # (solo si alguna persona esta parada en zona tipo='gondola') y una unica
            # vez por frame aunque haya varias personas en gondola/heladera a la vez.
            productos_frame = None

            for det in detecciones:
                heatmap.agregar_punto(det["cx"], det["cy"])
                sid = det["sid"]
                if fotos:
                    fotos.registrar(sid, frame_count, frame, det["box"])
                # Se calcula UNA vez por frame procesado (no solo en el muestreo
                # periodico de abajo) para que la secuencia de zonas de eventos.py
                # sea fiel al recorrido real -- ver PersonTracker.actualizar_zona.
                zona_id = utils.get_zona_id(det["cx"], det["cy"], zonas)
                tracker.actualizar_zona(sid, zona_id)

                # "Se acerco a pagar" = se quedo cerca de Zona Caja un tiempo
                # minimo (ver CAJA_PERMANENCIA_MINIMA_SEG/actualizar_acercamiento_caja),
                # no solo estar cerca en un instante -- eso descartaria a
                # alguien que solo camina de largo cerca del mostrador. Se
                # llama TODOS los frames (True o False) para que la racha se
                # corte si la persona se aleja antes de completar el minimo.
                cerca_de_caja = utils.cerca_de_zona_tipo(det["cx"], det["cy"], zonas, "caja", caja_distancia_px)
                tracker.actualizar_acercamiento_caja(sid, cerca_de_caja)

                # El chequeo de "hay un producto cerca" no puede depender SOLO
                # de zona_id=='gondola': en un kiosco/minimarket el cliente
                # muchas veces ni pisa la gondola -- el empleado le alcanza el
                # producto directo en el mostrador, y ese intercambio pasa
                # justo cerca de Zona Caja (cerca_de_caja, mismo chequeo de
                # arriba). Sin este OR, detectar_productos() nunca se llega a
                # invocar en ese caso -- no es que YOLO "no vea" el producto,
                # directamente nunca se le pide que mire.
                if zona_tipo_por_id.get(zona_id) == "gondola" or cerca_de_caja:
                    if productos_frame is None:
                        productos_frame = utils.detectar_productos(
                            model_productos, frame, config.PRODUCTO_CLASES_COCO, config.PRODUCTO_CONF,
                        )
                    hay_producto_cerca = utils.producto_cerca_de_persona(
                        det["box"], productos_frame, config.INTERACCION_MARGEN_PX,
                    )
                    tracker.actualizar_interaccion(sid, hay_producto_cerca)
                    if grabador and tracker.tomo_producto.get(sid) and not grabador.tiene_toma(sid):
                        grabador.marcar_toma(sid, frame_count)   # momento en que tomo el producto: se reserva su evidencia

                if persistencia.conn:
                    ultimo = ultimo_muestreo_traj.get(sid)
                    # Un punto de trayectoria por persona cada TRAYECTORIA_INTERVALO_SEG
                    # (antes: uno por frame procesado, ~5/seg -- eso era lo que
                    # inflaba la tabla). El primer punto de cada aparicion siempre
                    # se guarda (marca la posicion de entrada).
                    if ultimo is None or frame_count - ultimo >= muestreo_traj_frames:
                        ultimo_muestreo_traj[sid] = frame_count
                        traj_buffer.append({
                            "sid":     sid,
                            "frame":   frame_count,
                            "cx":      det["cx"],
                            "cy":      det["cy"],
                            "box":     det["box"],
                            "zona_id": zona_id,
                        })

            tracker.expirar_perdidos(frame_count)

            # Guardado incremental de trayectorias: cada N frames procesados se
            # vuelca a la BD lo acumulado hasta ahora, en vez de esperar a que
            # termine todo el video (si el analisis se corta, no se pierde el
            # recorrido ya hecho).
            if modo_rtsp:
                persistencia.asegurar_conexion()   # si se cayo la BD, reintenta (como maximo cada 20 s)
                toca_flush = time.monotonic() - ultimo_flush >= config.RTSP_FLUSH_CADA_SEG
            else:
                toca_flush = frame_count % (config.FRAME_SKIP * config.TRAYECTORIAS_FLUSH_CADA_N_FRAMES) == 0
            if persistencia.conn and toca_flush:
                if modo_rtsp:
                    ultimo_flush = time.monotonic()
                    # Personas (ultima_deteccion) + trayectorias pendientes; el
                    # buffer se vacia aca, el guardar_trayectorias_parcial de
                    # abajo ya no tiene nada que volcar.
                    persistencia.guardar_personas(
                        sesion_id, metricas.construir_rows(tracker.resumen_por_persona(), fps),
                        [], fps, inicio_dt, camara_id,
                    )
                    # El buffer solo se vacia si las trayectorias llegaron a la BD; si no (sin
                    # conexion), se conserva y se reintenta en el proximo ciclo.
                    if persistencia.guardar_trayectorias_parcial(traj_buffer, fps, inicio_dt, camara_id) >= 0:
                        traj_buffer.clear()
                    persistencia.actualizar_heartbeat(sesion_id)
                    if fotos:
                        fotos.publicar_pendientes(tracker.sid_to_persona_db_id, frame_count)
                    fps_real = _fps_actual(fps_muestras)
                    if fps_real < 0.7 * config.RTSP_TARGET_FPS:
                        print(f"[AVISO] La CPU procesa {fps_real:.1f}fps, muy por debajo del objetivo "
                              f"({config.RTSP_TARGET_FPS}fps) -- el analisis va con retraso respecto al "
                              f"vivo. Bajar config.RTSP_TARGET_FPS.")
                if traj_buffer:
                    persistencia.guardar_trayectorias_parcial(traj_buffer, fps, inicio_dt, camara_id)
                    traj_buffer.clear()

            if (modo_rtsp and persistencia.conn
                    and time.monotonic() - ultimo_heatmap >= config.RTSP_HEATMAP_CADA_SEG):
                ultimo_heatmap = time.monotonic()
                guardar_heatmaps(datetime.now(), frame_count)

            # Fusion en vivo de personas vistas por varias camaras del mismo grupo
            # (puede haber otras PCs analizando las demas camaras contra esta misma BD).
            if (modo_rtsp and persistencia.conn and config.RTSP_FUSION_CADA_SEG
                    and time.monotonic() - ultimo_fusion >= config.RTSP_FUSION_CADA_SEG):
                ultimo_fusion = time.monotonic()
                fusionadas = persistencia.fusionar_en_vivo(
                    datetime.now().date(), config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS,
                )
                if fusionadas:
                    print(f"[Fusion] {fusionadas} personas unificadas entre camaras del mismo grupo.")

            # Preview del heatmap en tiempo real
            if mostrar_preview:
                preview_counter += 1
                if preview_counter % config.PREVIEW_CADA_N == 0:
                    overlay = heatmap.render(frame, alpha_bg=0.5)
                    # Personas: box verde + sid, zona actual y tomo_producto (si ya se
                    # confirmo) -- para validar a ojo el Escenario A/B/C sin esperar a
                    # que termine el video y consultar la BD.
                    for det in detecciones:
                        x1, y1, x2, y2 = map(int, det["box"])
                        sid = det["sid"]
                        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        zona_nombre = zona_nombre_por_id.get(tracker.zona_actual.get(sid), "?")
                        etiqueta = f"#{sid} {zona_nombre}"
                        if tracker.tomo_producto.get(sid):
                            etiqueta += " | tomo_producto"
                        if tracker.acerco_a_caja.get(sid):
                            etiqueta += " | acerco_a_caja"
                        cv2.putText(overlay, etiqueta, (x1, max(0, y1 - 8)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    # Productos detectados este frame (amarillo) -- solo se calculo si
                    # alguien estaba en zona tipo='gondola' (ver bucle de arriba).
                    if productos_frame:
                        for box in productos_frame:
                            x1, y1, x2, y2 = map(int, box)
                            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 255), 2)
                    if modo_vivo:
                        cv2.putText(overlay, f"LIVE | Frame {frame_count} | FPS: {_fps_actual(fps_muestras):.1f}",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    else:
                        pct = frame_count / total_frames * 100 if total_frames else 0
                        cv2.putText(overlay, f"Frame {frame_count}/{total_frames} ({pct:.0f}%)",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                    cv2.imshow("OptiFull - Deteccion + Heatmap", utils.resize_for_display(overlay))
                    tecla = cv2.waitKey(1) & 0xFF
                    if tecla == ord('q'):
                        break
                    if modo_vivo and tecla == ord('p'):
                        pausado = True
                        print("[INFO] Pausado -- 'p' para reanudar, 'q' para detener.")

        if pbar is not None:
            pbar.close()
        if mostrar_preview:
            cv2.destroyAllWindows()
        source.release()

        # Cierra cualquier visita que haya quedado abierta (gente activa hasta el
        # ultimo frame, o perdida pero sin llegar a expirar) para que sume su
        # tiempo real de permanencia.
        if modo_rtsp:
            # Si internet se cayo justo antes del cierre, se reconecta ANTES de guardar lo ultimo
            # (visitas, eventos, personas, heatmap y fin de la sesion).
            persistencia.asegurar_conexion(forzar=True)
        tracker.cerrar_visitas_abiertas(frame_count)

        frames_procesados = frame_count // frame_skip_efectivo

        # ── Construir resultados de permanencia ──────────────────────────────────────
        rows = metricas.construir_rows(tracker.resumen_por_persona(), fps)

        if modo_camara:
            # Modo camara en vivo: NUNCA se persiste -- ni BD (Persistencia.*
            # ya es no-op sin conexion, pero eso no cubre Supabase Storage) ni
            # imagenes de heatmap. Se corta explicitamente ACA, antes de
            # cualquier llamada de guardado, en vez de confiar solo en que
            # sesion_id/camara_id sean None. Ver spec: "Modo camara = sin
            # persistencia".
            print("[INFO] Modo camara en vivo: no se persistio nada en la base "
                  "de datos ni en Supabase Storage (por diseno).")
        else:
            persistencia.guardar_personas(sesion_id, rows, traj_buffer, fps, inicio_dt, camara_id)

            # ── Auditoria post-analisis (ANTES de cerrar la sesion) ─────────────────
            # Red de seguridad para lo que el matching en vivo puede haber dejado
            # pasar: recalcula zona_id, saca de Zona Caja a quien no matchee a un
            # empleado ya conocido, y fusiona personas de camaras del mismo grupo
            # detectadas casi al mismo instante. Va DESPUES de guardar_personas
            # (necesita las trayectorias ya volcadas por completo) pero ANTES de
            # cerrar_sesion, tal como se pidio.
            persistencia.auditar_sesion(
                sesion_id, camara_id, config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS
            )

            # Decide empleado vs cliente por la MAYORIA de puntos de trayectoria
            # de cada persona de ESTA sesion (no por presencia puntual en Zona
            # Caja -- eso fusionaba clientes que solo pasaron a pagar) y borra
            # los puntos minoritarios que contradicen esa mayoria. Ver
            # Persistencia.reclasificar_por_mayoria_zona(). Acotado a 'sesion_id'
            # para no re-escanear toda la BD en cada video.
            persistencia.reclasificar_por_mayoria_zona(sesion_id=sesion_id)

            # Recien ACA se sabe quien es empleado en esta sesion -- durante el
            # analisis en vivo (_on_visita_cerrada) todavia no se sabia, asi que
            # los eventos/alertas de un sid que termino siendo empleado quedan
            # mal clasificados (un empleado no "compra" ni puede "robar"). Se
            # descartan antes de que lleguen al frontend.
            persistencia.limpiar_eventos_de_empleados(sesion_id=sesion_id)
            persistencia.sincronizar_es_empleado_trayectorias(sesion_id=sesion_id)

            # ── Cerrar sesion ──────────────────────────────────────────────────────
            fin_dt = datetime.now() if modo_rtsp else utils.frame_to_dt(total_frames, fps, inicio_dt)
            persistencia.cerrar_sesion(sesion_id, fin_dt)

            # Fusion retroactiva automatica de continuidad entre videos consecutivos
            # de esta camara (corte de archivo del DVR) + cross-camara del dia --
            # antes habia que correr deteccion/mantenimiento/fusionar_dia.py a mano
            # despues de cada corrida. Se corre para 'inicio_dt' (fecha del corte
            # con la sesion ANTERIOR de esta camara, el caso comun) y tambien para
            # 'fin_dt' si cae en otro dia calendario (sesion que cruza medianoche).
            if conectado:
                fechas_fusion = {inicio_dt.date(), fin_dt.date()}
                for fecha_fusion in fechas_fusion:
                    persistencia.fusionar_dia_hasta_converger(
                        fecha_fusion, config.CONTINUIDAD_VENTANA_SEG, config.CONTINUIDAD_ALTA_CONFIANZA_SEG,
                        config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS,
                    )

            # ── Guardar heatmap en BD (solo el "puro", sin overlay) ──────────────────
            guardar_heatmaps(fin_dt, frames_procesados)

        persistencia.cerrar()

        # ── Resumen ──────────────────────────────────────────────────────────────────
        metricas.imprimir_resumen(
            rows, camara_id, sesion_id, tracker.max_personas,
            tracker.conteo_metodo_reid, heatmap.total_detecciones, frames_procesados,
            len(traj_buffer),
        )
    except (KeyboardInterrupt, Exception):
        if modo_camara:
            # No hay sesion en BD (nunca se creo una) -- solo confirmar que se corto.
            print("\n[INFO] Camara en vivo detenida.")
        else:
            # Lo ya volcado a la BD se conserva (no se borra nada): solo se
            # marca el fin de la sesion.
            print("\n[AVISO] Analisis interrumpido por un error -- cerrando la sesion con lo ya guardado.")
            if conectado and sesion_id:
                persistencia.asegurar_conexion(forzar=True)
                persistencia.cerrar_sesion(sesion_id, datetime.now())
        persistencia.cerrar()
        raise


if __name__ == "__main__":
    main()

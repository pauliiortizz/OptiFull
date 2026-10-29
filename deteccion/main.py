"""Orquestador del pipeline: YOLO+ByteTrack -> PersonTracker (Re-ID local +
Gemini) -> HeatmapBuilder -> Persistencia (Supabase) -> reporte de metricas."""
import argparse
import signal
import sys
import threading
import os
import time
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


# RTSP por TCP (UDP pierde paquetes y rompe el decodificado H264/H265) y con poco buffer para que el frame
# leido sea el mas reciente. OpenCV lee esta variable al ABRIR cada captura, asi que se setea en main() solo en
# modo RTSP: aplicada a un video grabado, 'fflags;nobuffer' hacia perder su primer frame (DEF-012).
OPCIONES_FFMPEG_RTSP = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay"


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
    # --webcam/--screen sin valor quedan en None (pasadas, con el dispositivo por defecto) y en False si no
    # se pasaron; --rtsp queda en None si no se paso. Antes None contaba como "no pasada" y se aceptaba
    # '--webcam --screen' (DEF-011).
    pasadas = (args.webcam is not False) + (args.screen is not False) + (args.rtsp is not None)
    if pasadas > 1:
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


class Modo:
    """Que se analiza en esta corrida y como: archivo de video, camara RTSP en vivo (persiste), o webcam/pantalla
    (vista previa local, NUNCA persiste)."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.pantalla = args.screen is not False
        self.rtsp = args.rtsp is not None
        # camara = fuentes en vivo que NUNCA persisten (webcam/pantalla).
        # vivo = cualquier fuente sin fin conocido (incluye RTSP, que si persiste).
        self.camara = (args.webcam is not False) or self.pantalla
        self.vivo = self.camara or self.rtsp
        self.rtsp_id = args.rtsp
        self.archivo_label = config.VIDEO_PATH
        self.webcam_device = config.WEBCAM_DEVICE_INDEX if args.webcam is None else int(args.webcam)
        self.screen_monitor = config.SCREEN_MONITOR_INDEX if args.screen is None else int(args.screen)
        self.rtsp_url = None
        self.camara_id = None
        self.inicio_dt = None
        # SHOW_PREVIEW puede estar en False en config.py (uso normal con video de
        # archivo, sin ventana) -- en modo camara la ventana esta prendida por
        # default: ver todo en vivo es el objetivo del modo. En modo pantalla es
        # al reves (config.SCREEN_MOSTRAR_PREVIEW=False por default): cv2.imshow
        # tambien consume CPU que compite con la videollamada que se esta
        # analizando, asi que ahi el preview es opt-in.
        if self.pantalla:
            self.mostrar_preview = config.SCREEN_MOSTRAR_PREVIEW
        elif self.rtsp:
            self.mostrar_preview = config.RTSP_MOSTRAR_PREVIEW
        elif self.camara:
            self.mostrar_preview = True
        else:
            self.mostrar_preview = config.SHOW_PREVIEW

    def identificar(self) -> bool:
        """Determina camara_id, inicio_dt y archivo_label. False si la corrida no puede arrancar (RTSP sin URL)."""
        if self.camara:
            self.inicio_dt = datetime.now()
            if self.pantalla:
                print(f"[INFO] Modo pantalla en vivo (monitor={self.screen_monitor}) -- NO se "
                      f"va a persistir nada en la base de datos ni en Supabase Storage. "
                      f"Dejar la ventana/pestana a analizar (ej. Google Meet) visible en "
                      f"ese monitor.")
            else:
                print(f"[INFO] Modo camara en vivo (device={self.webcam_device}) -- NO se va "
                      f"a persistir nada en la base de datos ni en Supabase Storage. Es "
                      f"solo una vista previa local del pipeline.")
        elif self.rtsp:
            self.camara_id = self.rtsp_id
            self.inicio_dt = datetime.now()
            self.rtsp_url = config.RTSP_URLS.get(self.camara_id)
            if not self.rtsp_url:
                print(f"[ERROR] Falta RTSP_URL_{self.camara_id} en .env.")
                return False
            # Nunca se guarda la URL real en la BD (lleva usuario:clave).
            self.archivo_label = f"rtsp://camara_{self.camara_id}/{self.inicio_dt:%Y%m%d_%H%M%S}"
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", OPCIONES_FFMPEG_RTSP)
            print(f"[INFO] Modo RTSP en vivo -- camara {self.camara_id} "
                  f"({config.CAMARA_NOMBRES[self.camara_id][0]}). SI se persiste en la BD.")
        else:
            try:
                self.camara_id = config.CAMARA_ID_OVERRIDE or utils.parse_camara_id(config.VIDEO_PATH)
                self.inicio_dt = utils.parse_inicio(config.VIDEO_PATH)
                print(f"Camara detectada : {self.camara_id}  (desde '{Path(config.VIDEO_PATH).name}')")
                print(f"Inicio grabacion : {self.inicio_dt}")
            except ValueError as e:
                print(f"[AVISO] {e}")
                self.camara_id = None
                self.inicio_dt = datetime.now()
        return True


def _video_ya_analizado(persistencia: Persistencia) -> bool:
    """Frena ANTES de cargar el modelo y abrir el video si un video con este MISMO NOMBRE DE ARCHIVO ya fue
    analizado -- evita duplicar personas/trayectorias/heatmaps. Compara solo el nombre, no la ruta completa (la
    carpeta o la letra de unidad puede cambiar, ej. un mismo pendrive montado como D: o como E: segun la PC)."""
    sesion_existente = persistencia.buscar_sesion_por_archivo(config.VIDEO_PATH)
    if not sesion_existente:
        return False
    print(f"\n[AVISO] Ya existe un video analizado con el mismo nombre de archivo "
          f"('{Path(config.VIDEO_PATH).name}') -- no se va a procesar de nuevo "
          f"para no duplicar los datos.")
    print(f"        Sesion existente : id={sesion_existente['id']}, "
          f"camara={sesion_existente['camara_id']}, inicio={sesion_existente['inicio']}")
    print(f"        Ruta ya analizada: '{sesion_existente['archivo_path']}'")
    print(f"        Ruta actual      : '{config.VIDEO_PATH}'")
    print("        Revisa la ruta del video en config.py (VIDEO_PATH) -- "
          "si en verdad es un video distinto, asegurate de que tenga un nombre de archivo diferente.")
    return True


def _cargar_zonas(persistencia: Persistencia, modo: Modo, conectado: bool) -> list:
    if modo.camara and config.WEBCAM_CAMARA_ID_ZONAS is not None:
        # Carga de zonas en modo SOLO LECTURA para que el overlay las pueda
        # dibujar -- mismo patron que SOLO_LEER_ZONAS: conecta, lee, corta.
        # Nunca crea sesion ni escribe nada (coherente con modo camara).
        zonas = persistencia.cargar_zonas(config.WEBCAM_CAMARA_ID_ZONAS) if persistencia.conectar() else []
        if persistencia.conn:
            persistencia.conn.close()
            persistencia.conn = None
    else:
        zonas = persistencia.cargar_zonas(modo.camara_id) if conectado else []

    if zonas:
        zonas_de = config.WEBCAM_CAMARA_ID_ZONAS if modo.camara else modo.camara_id
        print(f"[DB] {len(zonas)} zonas cargadas para camara {zonas_de}: {[z['nombre'] for z in zonas]}")
    else:
        print("[DB] Sin zonas definidas para esta corrida.")
    return zonas


def _crear_reid(permitir_reid_nube: bool):
    """Proveedor de Re-ID en la nube segun config.REID_PROVIDER ('gemini', 'groq' o 'claude'). Todos tienen la
    misma interfaz (.activo, .generar_descripcion(), .clasificar()), asi que PersonTracker no necesita saber cual
    esta usando; la configuracion de cada uno sigue el mismo patron de nombres (GROQ_MODEL, CLAUDE_MODEL...)."""
    proveedores = {"groq": (GroqReID, "GROQ"), "claude": (ClaudeReID, "CLAUDE")}
    clase, p = proveedores.get(config.REID_PROVIDER, (GeminiReID, "GEMINI"))
    nombre = p.lower()
    return clase(**{
        f"usar_{nombre}_reid": getattr(config, f"USAR_{p}_REID") and permitir_reid_nube,
        f"has_{nombre}": getattr(config, f"HAS_{p}"),
        "api_keys": getattr(config, f"{p}_API_KEYS"),
        "model": getattr(config, f"{p}_MODEL"),
        "min_intervalo_seg": getattr(config, f"{p}_MIN_INTERVALO_SEG"),
        "rafaga_umbral": getattr(config, f"{p}_RAFAGA_UMBRAL"),
        "pausa_rafaga_seg": getattr(config, f"{p}_PAUSA_RAFAGA_SEG"),
        "ventana_rafaga_seg": getattr(config, f"{p}_VENTANA_RAFAGA_SEG"),
        "coincidencias_minimas": getattr(config, f"{p}_COINCIDENCIAS_MINIMAS"),
        "umbral_mismo_momento_seg": config.UMBRAL_MISMO_MOMENTO_SEG,
    })


def _abrir_fuente(modo: Modo):
    if modo.pantalla:
        source = ScreenVideoSource(
            monitor=modo.screen_monitor,
            region=config.SCREEN_REGION,
            target_fps=config.SCREEN_TARGET_FPS,
            scale=config.SCREEN_SCALE,
        )
    elif modo.rtsp:
        source = WebcamVideoSource(
            device=modo.rtsp_url,
            etiqueta=f"RTSP camara {modo.camara_id}",
            timeout_primer_frame_seg=15.0,
            reconectar_hasta_seg=config.RTSP_RECONECTAR_HASTA_SEG,
            descartar_repetidos=True,
            timeout_lectura_ms=config.RTSP_TIMEOUT_LECTURA_MS,
        )
    elif modo.camara:
        source = WebcamVideoSource(
            device=modo.webcam_device,
            resolution=config.WEBCAM_RESOLUTION,
            target_fps=config.WEBCAM_TARGET_FPS,
        )
    else:
        source = FileVideoSource(config.VIDEO_PATH)
    source.open()
    return source


_FIN = object()   # marca de _leer_frame(): la fuente termino o fallo


class Corrida:
    """Estado y pasos de UN analisis: preparar (modelo, fuente, tracker), procesar frame a frame, y al terminar
    guardar/auditar todo. main() solo decide el modo y orquesta estos pasos."""

    def __init__(self, modo: Modo, persistencia: Persistencia, storage: SupabaseStorage, zonas: list,
                 sesion_id, conectado: bool) -> None:
        self.modo = modo
        self.persistencia = persistencia
        self.storage = storage
        self.zonas = zonas
        self.sesion_id = sesion_id
        self.conectado = conectado
        self.camara_id = modo.camara_id
        self.inicio_dt = modo.inicio_dt
        # Mapas id->tipo/nombre para la clasificacion Escenario A/B/C (ver
        # pipeline/eventos.py) y para decidir en que zonas vale la pena correr la
        # deteccion de producto (solo tipo='gondola' -- Gondola/Heladera del
        # local, ver PRODUCTO_CLASES_COCO en config.py).
        self.zona_tipo_por_id   = {z["id"]: z["tipo"]   for z in zonas}
        self.zona_nombre_por_id = {z["id"]: z["nombre"] for z in zonas}

    # ── Preparacion ─────────────────────────────────────────────────────────────
    def preparar(self) -> None:
        modo = self.modo
        repo_root           = Path(__file__).resolve().parent.parent
        self.tracker_config = str(repo_root / "bytetrack_custom.yaml")

        self.model = YOLO(config.RTSP_MODELO if modo.rtsp else "yolov8n.pt")
        # Modelo APARTE para detectar productos (clases COCO de config.PRODUCTO_CLASES_COCO)
        # -- nunca se llama con .track()/persist=True, asi que no pisa el estado de
        # tracking de 'model' (ver utils.detectar_productos). Se usa perezosamente, solo
        # cuando alguna persona esta parada en una zona tipo='gondola' este frame.
        self.model_productos = YOLO("yolov8n.pt")

        self.source  = _abrir_fuente(modo)
        self.fps     = config.RTSP_TARGET_FPS if modo.rtsp else self.source.fps
        self.frame_w = self.source.frame_w
        self.frame_h = self.source.frame_h
        # Zonas dibujadas sobre 1920x1080: se llevan al tamano real del frame (RTSP = 640x360).
        self.zonas = utils.escalar_zonas(self.zonas, self.frame_w, self.frame_h, *config.ZONAS_REF_RESOLUCION)
        self.total_frames = self.source.total_frames  # None en modo camara
        # En vivo no hay FRAME_SKIP: WebcamVideoSource ya descarta los frames
        # atrasados solo (siempre entrega el mas reciente). frame_skip_efectivo=1
        # mantiene correctas las conversiones seg->frames de mas abajo.
        self.frame_skip = 1 if modo.vivo else config.FRAME_SKIP
        self.persistencia.actualizar_resolucion_sesion(self.sesion_id, self.frame_w, self.frame_h)

        self.caja_distancia_px = self.frame_w * config.CAJA_APROXIMACION_RATIO
        frames_a_procesar = (self.total_frames // self.frame_skip) if self.total_frames is not None else None
        self._imprimir_encabezado(frames_a_procesar)

        self.heatmap = HeatmapBuilder(self.frame_w, self.frame_h, config.GAUSSIAN_RADIUS)
        self._preparar_reid_y_tracker()
        self._preparar_evidencia_y_fotos()

        self.traj_buffer          = []
        self.ultimo_muestreo_traj = {}   # sid -> frame_count del ultimo punto de trayectoria guardado
        self.muestreo_traj_frames = max(1, int(self.fps * config.TRAYECTORIA_INTERVALO_SEG))
        self.frame_count          = 0
        self.preview_counter      = 0
        self.fps_muestras         = deque(maxlen=30)  # timestamps de los ultimos frames PROCESADOS (FPS en vivo)
        self.pausado              = False

        # Ctrl+C en RTSP no aborta: marca el corte para salir del loop y
        # pasar por el cierre normal (guardar personas/heatmap, cerrar sesion).
        self.detener = {"pedido": False}
        if modo.rtsp:
            signal.signal(signal.SIGINT, lambda *_: self.detener.update(pedido=True))
        self.intervalo_rtsp = 1.0 / config.RTSP_TARGET_FPS
        self.reloj_vivo     = [self.inicio_dt]  # indice 0 sin uso (frame_count arranca en 1)
        if modo.rtsp:
            utils.set_reloj_vivo(self.reloj_vivo)
        self.proximo_tick = time.perf_counter()
        self.ultimo_flush = self.ultimo_heatmap = self.ultimo_fusion = time.monotonic()
        self.pbar = tqdm(total=frames_a_procesar, unit="fr", desc="Analizando") if tqdm else None

    def _imprimir_encabezado(self, frames_a_procesar) -> None:
        modo = self.modo
        if modo.pantalla:
            print(f"\nPantalla en vivo: monitor={modo.screen_monitor}"
                  + (f", region={config.SCREEN_REGION}" if config.SCREEN_REGION else ""))
            print(f"Resolucion      : {self.frame_w}x{self.frame_h}  |  {self.fps:.0f}fps (nominal)")
        elif modo.rtsp:
            print(f"\nRTSP en vivo    : camara {self.camara_id}")
            print(f"Resolucion      : {self.frame_w}x{self.frame_h}  |  procesando a {self.fps:.1f}fps")
        elif modo.camara:
            print(f"\nCamara en vivo  : device={modo.webcam_device}")
            print(f"Resolucion      : {self.frame_w}x{self.frame_h}  |  {self.fps:.0f}fps (nominal)")
        else:
            print(f"\nVideo           : {config.VIDEO_PATH}")
            print(f"Resolucion      : {self.frame_w}x{self.frame_h}  |  {self.fps:.0f}fps  |  {self.total_frames:,} frames")
            print(f"Frames a leer   : {frames_a_procesar:,}  (frame_skip={self.frame_skip})")
        print()

    def _preparar_reid_y_tracker(self) -> None:
        modo, fps = self.modo, self.fps
        # En modo camara, Re-ID en la nube esta apagado por default (config.
        # WEBCAM_USAR_REID_NUBE=False) para no gastar cupo de API en pruebas
        # locales -- el tracking local (ByteTrack + apariencia) sigue andando igual.
        permitir_reid_nube = (config.RTSP_USAR_REID_NUBE if modo.rtsp
                              else (not modo.camara) or config.WEBCAM_USAR_REID_NUBE)
        if not permitir_reid_nube:
            print("[ReID] Modo camara en vivo: Re-ID en la nube desactivado por "
                  "default (config.WEBCAM_USAR_REID_NUBE=False) -- tracking local "
                  "+ heatmap sin gastar cupo de API.")
        reid = _crear_reid(permitir_reid_nube)
        print(f"[ReID] Proveedor configurado: {config.REID_PROVIDER}  (activo={reid.activo})")

        # Frames PROCESADOS (no crudos) por segundo real de video, para
        # convertir CAJA_PERMANENCIA_MINIMA_SEG a un contador de frames
        # consecutivos -- mismo criterio que INTERACCION_FRAMES_MINIMOS pero
        # partiendo de segundos en vez de un numero de frames fijo.
        caja_frames_minimos = max(1, round(config.CAJA_PERMANENCIA_MINIMA_SEG * fps / self.frame_skip))
        self.tracker = PersonTracker(
            frame_skip=self.frame_skip,
            max_dist=self.frame_w * config.MAX_DIST_RATIO,
            quick_expiry_frames=int(config.QUICK_EXPIRY_SEC * fps),
            long_expiry_frames=int(config.LONG_EXPIRY_SEC * fps),
            appearance_thresh=config.APPEARANCE_THRESH,
            max_app_samples=config.MAX_APP_SAMPLES,
            descripcion_streak_frames=config.DESCRIPCION_STREAK_FRAMES,
            min_frames_confirmacion=config.MIN_FRAMES_CONFIRMACION,
            gemini=reid,
            on_descripcion=self._on_descripcion,
            obtener_candidatos_dia=self._obtener_candidatos_dia,
            on_nueva_persona=self._on_nueva_persona,
            on_visita_cerrada=self._on_visita_cerrada,
            interaccion_frames_minimos=config.INTERACCION_FRAMES_MINIMOS,
            caja_frames_minimos=caja_frames_minimos,
        )

    def _preparar_evidencia_y_fotos(self) -> None:
        # Evidencia de los posibles hurtos (solo en vivo): ver pipeline/evidencia.py. Guarda en memoria los ultimos
        # segundos de imagenes; la subida de frames y clip se hace en un hilo aparte (no frena el analisis).
        self.grabador = None
        self.hilos_evidencia = []
        if self.modo.rtsp and config.EVIDENCIA_ACTIVA:
            self.grabador = GrabadorEvidencia(
                fps=self.fps, camara_id=self.camara_id, buffer_seg=config.EVIDENCIA_BUFFER_SEG,
                pre_seg=config.EVIDENCIA_PRE_SEG, post_seg=config.EVIDENCIA_POST_SEG,
                salida_seg=config.EVIDENCIA_SALIDA_SEG, frames_clave=config.EVIDENCIA_FRAMES_CLAVE,
            )
            self.persistencia.on_alerta_creada = self._publicar_evidencia_en_hilo

        # Foto de cada persona que lleva un rato en camara: sirve para que el usuario decida, desde la alerta
        # "Persona posiblemente empleada", si es empleado o no (ver pipeline/fotos.py).
        self.fotos = None
        if self.modo.rtsp and config.FOTOS_ACTIVAS and config.DATABASE_URL:
            self.fotos = CapturadorFotos(self.storage, config.DATABASE_URL, self.fps, config.FOTO_MIN_SEG)

    def _publicar_evidencia_en_hilo(self, alerta_id, evidencia) -> None:
        hilo = threading.Thread(
            target=publicar_evidencia,
            args=(self.storage, config.DATABASE_URL, alerta_id, evidencia, config.EVIDENCIA_CLIP_FPS),
            daemon=True,
        )
        hilo.start()
        self.hilos_evidencia = [h for h in self.hilos_evidencia if h.is_alive()] + [hilo]

    def _esperar_evidencia(self, timeout_seg: float = 120) -> None:
        """Antes de salir: espera las subidas de evidencia pendientes (son hilos daemon, al terminar el proceso
        se cortarian a la mitad y la alerta quedaria sin fotos ni clip)."""
        pendientes = [h for h in getattr(self, "hilos_evidencia", []) if h.is_alive()]
        if pendientes:
            print(f"[Evidencia] Esperando {len(pendientes)} subida(s) de evidencia pendiente(s)...")
        for h in pendientes:
            h.join(timeout_seg)

    # ── Callbacks de PersonTracker ──────────────────────────────────────────────
    def _on_descripcion(self, sid, frame_num, metodo, descripcion, cliente_id_hint):
        return self.persistencia.guardar_descripcion_persona(
            self.sesion_id, sid, frame_num, self.fps, self.inicio_dt, metodo, descripcion, cliente_id_hint,
        )

    def _obtener_candidatos_dia(self, excluir_ids, frame_num):
        momento = utils.frame_to_dt(frame_num, self.fps, self.inicio_dt)
        return self.persistencia.candidatos_reid_del_dia(momento, self.camara_id, excluir_ids), momento

    def _on_nueva_persona(self, sid, frame_num, metodo, cliente_id_hint):
        return self.persistencia.crear_persona(
            self.sesion_id, sid, frame_num, self.fps, self.inicio_dt, metodo, cliente_id_hint,
        )

    def _on_visita_cerrada(self, sid, frame_inicio, frame_fin, secuencia_zonas, tomo_producto, acerco_a_caja):
        persona_db_id = self.tracker.sid_to_persona_db_id.get(sid)
        visita_id = self.persistencia.guardar_visita(persona_db_id, frame_inicio, frame_fin, self.fps, self.inicio_dt)
        if not secuencia_zonas:
            if self.grabador:
                self.grabador.liberar(sid)
            return  # sin zonas registradas en toda la visita, no hay nada que clasificar
        evento = eventos.clasificar_evento(secuencia_zonas, tomo_producto, acerco_a_caja, self.zona_nombre_por_id)
        # Se imprime SIEMPRE (haya BD conectada o no, ver SOLO_LEER_ZONAS) --
        # guardar_evento() es un no-op silencioso sin conexion, y sin este
        # print no habria forma de ver el resultado de la clasificacion.
        print(f"[Evento] Persona {sid}: {evento['accion_detectada']} -- {eventos.resumen_evento(evento)}")
        evidencia = None
        if self.grabador:
            # Posible hurto: se arma la evidencia (frames + clip); cualquier otra visita descarta lo reservado.
            if evento["es_sospechoso"]:
                evidencia = self.grabador.construir(sid, frame_fin)
            else:
                self.grabador.liberar(sid)
        nota = "analisis cortado antes de confirmar la salida" if getattr(self, "cortado", False) else ""
        self.persistencia.guardar_evento(persona_db_id, visita_id, evento, frame_fin, self.fps, self.inicio_dt,
                                         evidencia=evidencia, nota=nota)

    # ── Heatmaps ────────────────────────────────────────────────────────────────
    def guardar_heatmaps(self, fin_dt, frames_procesados) -> None:
        """Heatmap de la sesion + combinado de la camara (upsert: se puede
        llamar varias veces durante una sesion en vivo sin duplicar)."""
        if self.heatmap.esta_vacio():
            print("[Heatmap] Acumulador vacio, no se guarda en BD.")
            return
        stats      = self.heatmap.calcular_stats(self.zonas, config.HEATMAP_UMBRAL, config.HEATMAP_GRID)
        ts_str     = self.inicio_dt.strftime("%Y%m%d_%H%M%S")
        puro_bytes = self.heatmap.codificar_puro(stats["hm_norm"])
        imagen_url = _subir_o_guardar_local(self.storage, f"camara_{self.camara_id}/{ts_str}.png", puro_bytes)

        self.persistencia.guardar_heatmap(
            self.camara_id, self.sesion_id, self.inicio_dt, fin_dt, stats,
            imagen_url, self.heatmap.total_detecciones, frames_procesados,
        )

        # Combinar con las sesiones previas de esta camara
        sesiones_previas = self.persistencia.obtener_matrices_camara(self.camara_id)
        if sesiones_previas:
            grid_size = sesiones_previas[0]["resolucion_x"] or config.HEATMAP_GRID
            combinado = combinar_grids(sesiones_previas, grid_size)
            stats_cam = calcular_stats_grid(combinado, self.zonas, config.HEATMAP_UMBRAL, self.frame_w, self.frame_h)
            cam_bytes = codificar_combinado(stats_cam["hm_norm"], self.frame_w, self.frame_h)
            cam_url   = _subir_o_guardar_local(self.storage, f"camara_{self.camara_id}/combinado.png", cam_bytes)
            self.persistencia.guardar_heatmap_camara(
                self.camara_id, stats_cam, cam_url,
                sum(s["total_detecciones"] for s in sesiones_previas),
                sum(s["frames_procesados"] for s in sesiones_previas),
                len(sesiones_previas),
            )

    # ── Loop principal ──────────────────────────────────────────────────────────
    def ejecutar(self) -> None:
        modo = self.modo
        while True:
            if modo.rtsp and not self._esperar_turno_rtsp():
                break
            if modo.vivo and self.pausado:
                if self._atender_pausa():
                    break
                continue

            frame = self._leer_frame()
            if frame is _FIN:
                break
            if frame is None:
                continue

            detecciones, productos_frame = self._procesar_frame(frame)
            self.tracker.expirar_perdidos(self.frame_count)
            self._volcar_a_la_bd()
            self._tareas_periodicas_rtsp()
            if modo.mostrar_preview and not self._mostrar_preview(frame, detecciones, productos_frame):
                break

    def _leer_frame(self):
        """El proximo frame a procesar; None si este se saltea (sin frame nuevo en vivo, o FRAME_SKIP en un
        video grabado) y _FIN si la fuente termino o fallo."""
        modo = self.modo
        ret, frame = self.source.read()
        if modo.vivo:
            error = self.source.error()
            if error:
                print(f"[ERROR] {error}")
                return _FIN
        if not ret:
            return _FIN
        if modo.vivo and frame is None:
            return None   # sin frame nuevo (stream en pausa o reconectando): no se reprocesa el anterior

        self.frame_count += 1
        if modo.rtsp:
            self.reloj_vivo.append(datetime.now())  # reloj_vivo[n] = hora real del frame n
        if not modo.vivo and self.frame_count % self.frame_skip != 0:
            return None
        return frame

    def _esperar_turno_rtsp(self) -> bool:
        """Mantiene el ritmo de RTSP_TARGET_FPS. False si se pidio cortar (Ctrl+C)."""
        if self.detener["pedido"]:
            print("\n[INFO] Corte pedido (Ctrl+C) -- cerrando y guardando...")
            return False
        restante = self.proximo_tick - time.perf_counter()
        if restante > 0:
            time.sleep(restante)
        self.proximo_tick = max(self.proximo_tick, time.perf_counter()) + self.intervalo_rtsp
        return True

    def _atender_pausa(self) -> bool:
        """Pausa: no se lee ni procesa. La camara sigue viva en su hilo de
        background (WebcamVideoSource sigue capturando), asi que al reanudar se
        retoma con el frame mas reciente disponible, no con uno atrasado. True
        si se pidio salir ('q')."""
        tecla = cv2.waitKey(50) & 0xFF
        if tecla == ord('q'):
            return True
        if tecla == ord('p'):
            self.pausado = False
            print("[INFO] Reanudado.")
        return False

    def _procesar_frame(self, frame):
        """YOLO+ByteTrack -> identidad estable -> zonas, caja, productos, heatmap y trayectorias de cada persona.
        Devuelve (detecciones, productos detectados en el frame o None si no hizo falta buscarlos)."""
        modo = self.modo
        self.fps_muestras.append(time.perf_counter())
        if self.pbar is not None:
            self.pbar.update(1)
        elif not modo.vivo and self.frame_count % (self.frame_skip * 500) == 0:
            pct = self.frame_count / self.total_frames * 100
            print(f"  {pct:.1f}%  [{utils.to_timestamp(self.frame_count, self.fps)}]", end="\r")

        results = self.model.track(
            frame,
            classes=[0],
            conf=config.RTSP_CONF if modo.rtsp else config.CONF,
            imgsz=config.RTSP_IMGSZ if modo.rtsp else 640,
            tracker=self.tracker_config,
            persist=True,
            verbose=False,
        )
        detecciones = self.tracker.procesar_frame(frame, self.frame_count, results)
        if self.grabador:
            self.grabador.registrar_frame(self.frame_count, utils.frame_to_dt(self.frame_count, self.fps, self.inicio_dt),
                                          frame, detecciones)

        # Cache de productos detectados en ESTE frame -- se calcula perezosamente
        # (solo si alguna persona esta parada en zona tipo='gondola' o cerca de la
        # caja) y una unica vez por frame aunque haya varias personas a la vez.
        productos = {"frame": None}
        for det in detecciones:
            self._procesar_persona(frame, det, productos)
        return detecciones, productos["frame"]

    def _procesar_persona(self, frame, det, productos) -> None:
        tracker = self.tracker
        self.heatmap.agregar_punto(det["cx"], det["cy"])
        sid = det["sid"]
        if self.fotos:
            self.fotos.registrar(sid, self.frame_count, frame, det["box"])
        # Se calcula UNA vez por frame procesado (no solo en el muestreo
        # periodico de abajo) para que la secuencia de zonas de eventos.py
        # sea fiel al recorrido real -- ver PersonTracker.actualizar_zona.
        zona_id = utils.get_zona_id(det["cx"], det["cy"], self.zonas)
        tracker.actualizar_zona(sid, zona_id)

        # "Se acerco a pagar" = se quedo cerca de Zona Caja un tiempo minimo
        # (ver CAJA_PERMANENCIA_MINIMA_SEG/actualizar_acercamiento_caja), no solo
        # estar cerca en un instante. Se llama TODOS los frames (True o False)
        # para que la racha se corte si la persona se aleja antes del minimo.
        cerca_de_caja = utils.cerca_de_zona_tipo(det["cx"], det["cy"], self.zonas, "caja", self.caja_distancia_px)
        tracker.actualizar_acercamiento_caja(sid, cerca_de_caja)

        # El chequeo de "hay un producto cerca" no puede depender SOLO de
        # zona_id=='gondola': en un kiosco/minimarket el cliente muchas veces ni
        # pisa la gondola -- el empleado le alcanza el producto directo en el
        # mostrador, y ese intercambio pasa justo cerca de Zona Caja. Sin este OR,
        # detectar_productos() nunca se llega a invocar en ese caso.
        if self.zona_tipo_por_id.get(zona_id) == "gondola" or cerca_de_caja:
            if productos["frame"] is None:
                productos["frame"] = utils.detectar_productos(
                    self.model_productos, frame, config.PRODUCTO_CLASES_COCO, config.PRODUCTO_CONF,
                )
            hay_producto_cerca = utils.producto_cerca_de_persona(
                det["box"], productos["frame"], config.INTERACCION_MARGEN_PX,
            )
            tracker.actualizar_interaccion(sid, hay_producto_cerca)
            if self.grabador and tracker.tomo_producto.get(sid) and not self.grabador.tiene_toma(sid):
                self.grabador.marcar_toma(sid, self.frame_count)   # momento en que tomo el producto: se reserva su evidencia

        if self.persistencia.conn:
            ultimo = self.ultimo_muestreo_traj.get(sid)
            # Un punto de trayectoria por persona cada TRAYECTORIA_INTERVALO_SEG (no
            # uno por frame procesado: eso inflaba la tabla). El primer punto de cada
            # aparicion siempre se guarda (marca la posicion de entrada).
            if ultimo is None or self.frame_count - ultimo >= self.muestreo_traj_frames:
                self.ultimo_muestreo_traj[sid] = self.frame_count
                self.traj_buffer.append({
                    "sid":     sid,
                    "frame":   self.frame_count,
                    "cx":      det["cx"],
                    "cy":      det["cy"],
                    "box":     det["box"],
                    "zona_id": zona_id,
                })

    def _volcar_a_la_bd(self) -> None:
        """Guardado incremental: cada N frames procesados (o cada RTSP_FLUSH_CADA_SEG en vivo) se vuelca a la BD lo
        acumulado, en vez de esperar al final (si el analisis se corta, no se pierde el recorrido ya hecho)."""
        p = self.persistencia
        if self.modo.rtsp:
            p.asegurar_conexion()   # si se cayo la BD, reintenta (como maximo cada 20 s)
            toca_flush = time.monotonic() - self.ultimo_flush >= config.RTSP_FLUSH_CADA_SEG
        else:
            toca_flush = self.frame_count % (config.FRAME_SKIP * config.TRAYECTORIAS_FLUSH_CADA_N_FRAMES) == 0
        if not (p.conn and toca_flush):
            return
        if self.modo.rtsp:
            self.ultimo_flush = time.monotonic()
            # Personas (ultima_deteccion) + trayectorias pendientes; el buffer se
            # vacia aca, el guardar_trayectorias_parcial de abajo ya no tiene nada.
            p.guardar_personas(
                self.sesion_id, metricas.construir_rows(self.tracker.resumen_por_persona(), self.fps),
                [], self.fps, self.inicio_dt, self.camara_id,
            )
            # El buffer solo se vacia si las trayectorias llegaron a la BD; si no (sin
            # conexion), se conserva y se reintenta en el proximo ciclo.
            if p.guardar_trayectorias_parcial(self.traj_buffer, self.fps, self.inicio_dt, self.camara_id) >= 0:
                self.traj_buffer.clear()
            p.actualizar_heartbeat(self.sesion_id)
            if self.fotos:
                self.fotos.publicar_pendientes(self.tracker.sid_to_persona_db_id, self.frame_count)
            fps_real = _fps_actual(self.fps_muestras)
            if fps_real < 0.7 * config.RTSP_TARGET_FPS:
                print(f"[AVISO] La CPU procesa {fps_real:.1f}fps, muy por debajo del objetivo "
                      f"({config.RTSP_TARGET_FPS}fps) -- el analisis va con retraso respecto al "
                      f"vivo. Bajar config.RTSP_TARGET_FPS.")
        if self.traj_buffer:
            p.guardar_trayectorias_parcial(self.traj_buffer, self.fps, self.inicio_dt, self.camara_id)
            self.traj_buffer.clear()

    def _tareas_periodicas_rtsp(self) -> None:
        """En vivo: heatmap cada RTSP_HEATMAP_CADA_SEG y fusion de personas vistas por varias camaras del mismo
        grupo cada RTSP_FUSION_CADA_SEG (puede haber otras PCs analizando las demas camaras contra la misma BD)."""
        p = self.persistencia
        if not (self.modo.rtsp and p.conn):
            return
        if time.monotonic() - self.ultimo_heatmap >= config.RTSP_HEATMAP_CADA_SEG:
            self.ultimo_heatmap = time.monotonic()
            self.guardar_heatmaps(datetime.now(), self.frame_count)
        if config.RTSP_FUSION_CADA_SEG and time.monotonic() - self.ultimo_fusion >= config.RTSP_FUSION_CADA_SEG:
            self.ultimo_fusion = time.monotonic()
            fusionadas = p.fusionar_en_vivo(
                datetime.now().date(), config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS,
            )
            if fusionadas:
                print(f"[Fusion] {fusionadas} personas unificadas entre camaras del mismo grupo.")

    def _mostrar_preview(self, frame, detecciones, productos_frame) -> bool:
        """Preview del heatmap en tiempo real, con cada persona (box, zona, tomo_producto/acerco_a_caja) para
        validar a ojo el Escenario A/B/C. False si se pidio salir ('q')."""
        self.preview_counter += 1
        if self.preview_counter % config.PREVIEW_CADA_N != 0:
            return True
        overlay = self.heatmap.render(frame, alpha_bg=0.5)
        for det in detecciones:
            x1, y1, x2, y2 = map(int, det["box"])
            sid = det["sid"]
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
            zona_nombre = self.zona_nombre_por_id.get(self.tracker.zona_actual.get(sid), "?")
            etiqueta = f"#{sid} {zona_nombre}"
            if self.tracker.tomo_producto.get(sid):
                etiqueta += " | tomo_producto"
            if self.tracker.acerco_a_caja.get(sid):
                etiqueta += " | acerco_a_caja"
            cv2.putText(overlay, etiqueta, (x1, max(0, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        # Productos detectados este frame (amarillo) -- solo se calculo si alguien estaba en gondola/caja.
        for box in productos_frame or []:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 255), 2)
        if self.modo.vivo:
            cv2.putText(overlay, f"LIVE | Frame {self.frame_count} | FPS: {_fps_actual(self.fps_muestras):.1f}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        else:
            pct = self.frame_count / self.total_frames * 100 if self.total_frames else 0
            cv2.putText(overlay, f"Frame {self.frame_count}/{self.total_frames} ({pct:.0f}%)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imshow("OptiFull - Deteccion + Heatmap", utils.resize_for_display(overlay))
        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord('q'):
            return False
        if self.modo.vivo and tecla == ord('p'):
            self.pausado = True
            print("[INFO] Pausado -- 'p' para reanudar, 'q' para detener.")
        return True

    # ── Cierre ──────────────────────────────────────────────────────────────────
    def finalizar(self) -> None:
        modo, p = self.modo, self.persistencia
        if self.pbar is not None:
            self.pbar.close()
        if modo.mostrar_preview:
            cv2.destroyAllWindows()
        self.source.release()

        # Cierra cualquier visita que haya quedado abierta (gente activa hasta el
        # ultimo frame, o perdida pero sin llegar a expirar) para que sume su
        # tiempo real de permanencia.
        if modo.rtsp:
            # Si internet se cayo justo antes del cierre, se reconecta ANTES de guardar lo ultimo
            # (visitas, eventos, personas, heatmap y fin de la sesion).
            p.asegurar_conexion(forzar=True)
            self.cortado = True   # las visitas que se cierran aca no llegaron a confirmar la salida
        self.tracker.cerrar_visitas_abiertas(self.frame_count)

        frames_procesados = self.frame_count // self.frame_skip
        rows = metricas.construir_rows(self.tracker.resumen_por_persona(), self.fps)

        if modo.camara:
            # Modo camara en vivo: NUNCA se persiste -- ni BD ni imagenes de heatmap
            # en Supabase Storage. Se corta explicitamente ACA, antes de cualquier
            # guardado, en vez de confiar solo en que sesion_id/camara_id sean None.
            print("[INFO] Modo camara en vivo: no se persistio nada en la base "
                  "de datos ni en Supabase Storage (por diseno).")
        else:
            self._guardar_y_auditar(rows, frames_procesados)

        self._esperar_evidencia()
        p.cerrar()
        metricas.imprimir_resumen(
            rows, self.camara_id, self.sesion_id, self.tracker.max_personas,
            self.tracker.conteo_metodo_reid, self.heatmap.total_detecciones, frames_procesados,
            len(self.traj_buffer),
        )

    def _guardar_y_auditar(self, rows, frames_procesados) -> None:
        p, sesion_id = self.persistencia, self.sesion_id
        p.guardar_personas(sesion_id, rows, self.traj_buffer, self.fps, self.inicio_dt, self.camara_id)

        # Auditoria post-analisis (ANTES de cerrar la sesion): red de seguridad para
        # lo que el matching en vivo puede haber dejado pasar -- recalcula zona_id y
        # fusiona personas de camaras del mismo grupo detectadas casi al mismo
        # instante. Va DESPUES de guardar_personas (necesita las trayectorias ya
        # volcadas por completo).
        p.auditar_sesion(sesion_id, self.camara_id, config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS)

        # Decide empleado vs cliente por la MAYORIA de puntos de trayectoria de
        # cada persona de ESTA sesion y borra los puntos minoritarios que
        # contradicen esa mayoria (ver Persistencia.reclasificar_por_mayoria_zona).
        p.reclasificar_por_mayoria_zona(sesion_id=sesion_id)

        # Recien ACA se sabe quien es empleado en esta sesion: los eventos/alertas
        # de un sid que termino siendo empleado se descartan (un empleado no
        # "compra" ni puede "robar") antes de que lleguen al frontend.
        p.limpiar_eventos_de_empleados(sesion_id=sesion_id)
        p.sincronizar_es_empleado_trayectorias(sesion_id=sesion_id)

        fin_dt = datetime.now() if self.modo.rtsp else utils.frame_to_dt(self.total_frames, self.fps, self.inicio_dt)
        p.cerrar_sesion(sesion_id, fin_dt)

        # Fusion retroactiva automatica de continuidad entre videos consecutivos de
        # esta camara (corte de archivo del DVR) + cross-camara del dia. Se corre para
        # 'inicio_dt' y tambien para 'fin_dt' si cae en otro dia (sesion que cruza medianoche).
        if self.conectado:
            for fecha_fusion in {self.inicio_dt.date(), fin_dt.date()}:
                p.fusionar_dia_hasta_converger(
                    fecha_fusion, config.CONTINUIDAD_VENTANA_SEG, config.CONTINUIDAD_ALTA_CONFIANZA_SEG,
                    config.UMBRAL_MISMO_MOMENTO_SEG, config.FUSION_COINCIDENCIAS_MINIMAS,
                )

        # Heatmap en BD (solo el "puro", sin overlay)
        self.guardar_heatmaps(fin_dt, frames_procesados)

    def abortar(self) -> None:
        """El analisis se interrumpio (Ctrl+C, error): lo ya volcado a la BD se conserva -- solo se marca el fin."""
        if self.modo.camara:
            # No hay sesion en BD (nunca se creo una) -- solo confirmar que se corto.
            print("\n[INFO] Camara en vivo detenida.")
        else:
            print("\n[AVISO] Analisis interrumpido por un error -- cerrando la sesion con lo ya guardado.")
            if self.conectado and self.sesion_id:
                self.persistencia.asegurar_conexion(forzar=True)
                self._cerrar_visitas_por_corte()
                self.persistencia.cerrar_sesion(self.sesion_id, datetime.now())
        self._esperar_evidencia()
        self.persistencia.cerrar()

    def _cerrar_visitas_por_corte(self) -> None:
        """En vivo, las visitas recien se cierran tras LONG_EXPIRY_SEC sin ver a la persona: si el analisis se
        corta antes, se cierran aca para no perder las de quien tomo un producto y no paso por caja -- se suben como
        alerta de posible hurto (con su evidencia) aunque todavia no estuviera confirmado que se fue."""
        tracker = getattr(self, "tracker", None)
        if not self.modo.rtsp or tracker is None:
            return
        self.cortado = True
        try:
            tracker.cerrar_visitas_abiertas(self.frame_count)
        except Exception as error:
            print(f"[AVISO] No se pudieron cerrar las visitas abiertas: {error}")


def main() -> None:
    modo = Modo(_parse_args())
    if not modo.identificar():
        return

    # ── Conexion a BD, zonas y sesion ───────────────────────────────────────────
    persistencia = Persistencia(
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS, config.CAMARA_NOMBRES,
        config.GRUPOS_CAMARA, config.REID_VENTANA_HORAS,
    )
    storage = SupabaseStorage(
        config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, config.SUPABASE_BUCKET, config.HAS_SUPABASE_STORAGE
    )
    conectado = persistencia.conectar() if modo.camara_id else False
    if conectado and not config.SOLO_LEER_ZONAS and not modo.rtsp and _video_ya_analizado(persistencia):
        persistencia.cerrar()
        return

    zonas = _cargar_zonas(persistencia, modo, conectado)
    if conectado and config.SOLO_LEER_ZONAS:
        # Ya se leyeron las zonas -- se corta la conexion ACA, antes de crear la
        # sesion. Todo Persistencia.* de aca en mas es no-op sin conexion, asi que
        # el resto del analisis corre entero sin escribir ninguna fila en la BD.
        print("[DB] SOLO_LEER_ZONAS activo -- se corta la conexion. El resto del "
              "analisis NO va a escribir nada en la BD.")
        persistencia.conn.close()
        persistencia.conn = None
        conectado = False

    sesion_id = persistencia.crear_sesion(modo.camara_id, modo.inicio_dt, modo.archivo_label) if conectado else None
    # En vivo (RTSP) una caida de internet no puede dejar el analisis sin guardar: se reconecta sola.
    persistencia.reconectar_automaticamente = bool(modo.rtsp and conectado)

    corrida = Corrida(modo, persistencia, storage, zonas, sesion_id, conectado)
    try:
        corrida.preparar()
        corrida.ejecutar()
        corrida.finalizar()
    except (KeyboardInterrupt, Exception):
        corrida.abortar()
        raise


if __name__ == "__main__":
    main()

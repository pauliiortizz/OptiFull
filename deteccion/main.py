"""Orquestador del pipeline: YOLO+ByteTrack -> PersonTracker (Re-ID local +
Gemini) -> HeatmapBuilder -> Persistencia (Supabase) -> reporte de metricas."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from datetime import datetime

import cv2
from ultralytics import YOLO

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from deteccion import config, utils, metricas
from deteccion.gemini_reid import GeminiReID
from deteccion.groq_reid import GroqReID
from deteccion.tracking import PersonTracker
from deteccion.heatmap import (
    HeatmapBuilder, combinar_grids, calcular_stats_grid, codificar_combinado,
)
from deteccion.persistencia import Persistencia
from deteccion.storage import SupabaseStorage


def _subir_o_guardar_local(storage: SupabaseStorage, path: str, contenido: bytes) -> str:
    """Sube 'contenido' a Supabase Storage bajo 'path'; si Storage no esta
    configurado o la subida falla, lo guarda localmente (con el path aplanado
    a nombre de archivo) para no perder el analisis."""
    url = storage.subir_png(path, contenido)
    if url:
        print(f"[Heatmap] Subido a Supabase Storage: {url}")
        return url
    local_path = path.replace("/", "_")
    with open(local_path, "wb") as f:
        f.write(contenido)
    print(f"[Heatmap] Storage no disponible, guardado local: {local_path}")
    return local_path


def main() -> None:
    # ── Determinar camara e inicio de grabacion ────────────────────────────────
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
        config.DATABASE_URL, config.HAS_DB, config.GUARDAR_TRAYECTORIAS, config.CAMARA_NOMBRES
    )
    storage = SupabaseStorage(
        config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, config.SUPABASE_BUCKET, config.HAS_SUPABASE_STORAGE
    )
    conectado = persistencia.conectar() if camara_id else False
    zonas     = persistencia.cargar_zonas(camara_id) if conectado else []
    sesion_id = persistencia.crear_sesion(camara_id, inicio_dt, config.VIDEO_PATH) if conectado else None

    if zonas:
        print(f"[DB] {len(zonas)} zonas cargadas para camara {camara_id}: {[z['nombre'] for z in zonas]}")
    else:
        print(f"[DB] Sin zonas definidas para camara {camara_id}.")

    # ── Inicializacion modelo y video ───────────────────────────────────────────
    repo_root      = Path(__file__).resolve().parent.parent
    tracker_config = str(repo_root / "bytetrack_custom.yaml")

    model        = YOLO("yolov8n.pt")
    cap          = cv2.VideoCapture(config.VIDEO_PATH)
    fps          = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_w      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h      = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    max_dist            = frame_w * config.MAX_DIST_RATIO
    quick_expiry_frames = int(config.QUICK_EXPIRY_SEC * fps)
    long_expiry_frames  = int(config.LONG_EXPIRY_SEC * fps)
    frames_a_procesar   = total_frames // config.FRAME_SKIP

    print(f"\nVideo           : {config.VIDEO_PATH}")
    print(f"Resolucion      : {frame_w}x{frame_h}  |  {fps:.0f}fps  |  {total_frames:,} frames")
    print(f"Frames a leer   : {frames_a_procesar:,}  (frame_skip={config.FRAME_SKIP})")
    print()

    # ── Construccion de los componentes del pipeline ────────────────────────────
    heatmap = HeatmapBuilder(frame_w, frame_h, config.GAUSSIAN_RADIUS)

    # Proveedor de Re-ID en la nube: Gemini o Groq (config.REID_PROVIDER), ambos
    # con la misma interfaz (.activo, .generar_descripcion(), .clasificar()) asi
    # que PersonTracker no necesita saber cual esta usando.
    if config.REID_PROVIDER == "groq":
        gemini = GroqReID(
            usar_groq_reid=config.USAR_GROQ_REID,
            has_groq=config.HAS_GROQ,
            api_keys=config.GROQ_API_KEYS,
            model=config.GROQ_MODEL,
            min_intervalo_seg=config.GROQ_MIN_INTERVALO_SEG,
            rafaga_umbral=config.GROQ_RAFAGA_UMBRAL,
            pausa_rafaga_seg=config.GROQ_PAUSA_RAFAGA_SEG,
            ventana_rafaga_seg=config.GROQ_VENTANA_RAFAGA_SEG,
            coincidencias_minimas=config.GROQ_COINCIDENCIAS_MINIMAS,
        )
    else:
        gemini = GeminiReID(
            usar_gemini_reid=config.USAR_GEMINI_REID,
            has_gemini=config.HAS_GEMINI,
            api_keys=config.GEMINI_API_KEYS,
            model=config.GEMINI_MODEL,
            min_intervalo_seg=config.GEMINI_MIN_INTERVALO_SEG,
            rafaga_umbral=config.GEMINI_RAFAGA_UMBRAL,
            pausa_rafaga_seg=config.GEMINI_PAUSA_RAFAGA_SEG,
            ventana_rafaga_seg=config.GEMINI_VENTANA_RAFAGA_SEG,
            coincidencias_minimas=config.GEMINI_COINCIDENCIAS_MINIMAS,
        )
    print(f"[ReID] Proveedor configurado: {config.REID_PROVIDER}  (activo={gemini.activo})")

    def _on_descripcion(sid, frame_num, metodo, descripcion, cliente_id_hint):
        return persistencia.guardar_descripcion_persona(
            sesion_id, sid, frame_num, fps, inicio_dt, metodo, descripcion, cliente_id_hint,
        )

    def _obtener_candidatos_dia(excluir_ids):
        return persistencia.candidatos_reid_del_dia(inicio_dt.date(), excluir_ids)

    def _on_nueva_persona(sid, frame_num, metodo, cliente_id_hint):
        return persistencia.crear_persona(
            sesion_id, sid, frame_num, fps, inicio_dt, metodo, cliente_id_hint,
        )

    tracker = PersonTracker(
        frame_skip=config.FRAME_SKIP,
        max_dist=max_dist,
        quick_expiry_frames=quick_expiry_frames,
        long_expiry_frames=long_expiry_frames,
        appearance_thresh=config.APPEARANCE_THRESH,
        max_app_samples=config.MAX_APP_SAMPLES,
        descripcion_streak_frames=config.DESCRIPCION_STREAK_FRAMES,
        gemini=gemini,
        on_descripcion=_on_descripcion,
        obtener_candidatos_dia=_obtener_candidatos_dia,
        on_nueva_persona=_on_nueva_persona,
    )

    traj_buffer     = []
    last_frame      = None
    frame_count     = 0
    preview_counter = 0

    pbar = tqdm(total=frames_a_procesar, unit="fr", desc="Analizando") if tqdm else None

    # ── Loop principal ──────────────────────────────────────────────────────────
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        if frame_count % config.FRAME_SKIP != 0:
            continue

        last_frame = frame

        if pbar:
            pbar.update(1)
        elif frame_count % (config.FRAME_SKIP * 500) == 0:
            pct = frame_count / total_frames * 100
            print(f"  {pct:.1f}%  [{utils.to_timestamp(frame_count, fps)}]", end="\r")

        results = model.track(
            frame,
            classes=[0],
            conf=config.CONF,
            tracker=tracker_config,
            persist=True,
            verbose=False,
        )

        detecciones = tracker.procesar_frame(frame, frame_count, results)

        for det in detecciones:
            heatmap.agregar_punto(det["cx"], det["cy"])
            if persistencia.conn:
                traj_buffer.append({
                    "sid":     det["sid"],
                    "frame":   frame_count,
                    "cx":      det["cx"],
                    "cy":      det["cy"],
                    "box":     det["box"],
                    "zona_id": utils.get_zona_id(det["cx"], det["cy"], zonas),
                })

        tracker.expirar_perdidos(frame_count)

        # Guardado incremental de trayectorias: cada N frames procesados se
        # vuelca a la BD lo acumulado hasta ahora, en vez de esperar a que
        # termine todo el video (si el analisis se corta, no se pierde el
        # recorrido ya hecho).
        if (persistencia.conn and traj_buffer
                and frame_count % (config.FRAME_SKIP * config.TRAYECTORIAS_FLUSH_CADA_N_FRAMES) == 0):
            persistencia.guardar_trayectorias_parcial(traj_buffer, fps, inicio_dt)
            traj_buffer.clear()

        # Preview del heatmap en tiempo real
        if config.SHOW_PREVIEW:
            preview_counter += 1
            if preview_counter % config.PREVIEW_CADA_N == 0:
                overlay = heatmap.render(frame, alpha_bg=0.5)
                r = results[0]
                if r.boxes is not None:
                    for box in r.boxes.xyxy.tolist():
                        x1, y1, x2, y2 = map(int, box)
                        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
                pct = frame_count / total_frames * 100 if total_frames else 0
                cv2.putText(overlay, f"Frame {frame_count}/{total_frames} ({pct:.0f}%)",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
                cv2.imshow("OptiFull - Deteccion + Heatmap", utils.resize_for_display(overlay))
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    if pbar:
        pbar.close()
    if config.SHOW_PREVIEW:
        cv2.destroyAllWindows()
    cap.release()

    frames_procesados = frame_count // config.FRAME_SKIP

    # ── Cerrar sesion ────────────────────────────────────────────────────────────
    fin_dt = utils.frame_to_dt(total_frames, fps, inicio_dt)
    persistencia.cerrar_sesion(sesion_id, fin_dt)

    # ── Construir resultados de permanencia y guardar en BD ─────────────────────
    rows = metricas.construir_rows(tracker.resumen_por_persona(), fps)
    persistencia.guardar_personas(sesion_id, rows, traj_buffer, fps, inicio_dt)

    # ── Guardar heatmap en BD (solo el "puro", sin overlay) ─────────────────────
    if not heatmap.esta_vacio():
        stats      = heatmap.calcular_stats(zonas, config.HEATMAP_UMBRAL, config.HEATMAP_GRID)
        ts_str     = inicio_dt.strftime("%Y%m%d_%H%M%S")
        puro_bytes = heatmap.codificar_puro(stats["hm_norm"])
        imagen_url = _subir_o_guardar_local(storage, f"camara_{camara_id}/{ts_str}.png", puro_bytes)

        persistencia.guardar_heatmap(
            camara_id, sesion_id, inicio_dt, fin_dt, stats,
            imagen_url, heatmap.total_detecciones, frames_procesados,
        )

        # ── Combinar con las sesiones previas de esta camara ────────────────────
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
    else:
        print("[Heatmap] Acumulador vacio, no se guarda en BD.")

    persistencia.cerrar()

    # ── Resumen ──────────────────────────────────────────────────────────────────
    metricas.imprimir_resumen(
        rows, camara_id, sesion_id, tracker.max_personas,
        tracker.conteo_metodo_reid, heatmap.total_detecciones, frames_procesados,
        len(traj_buffer),
    )


if __name__ == "__main__":
    main()

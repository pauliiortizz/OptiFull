"""Deteccion de personas: resuelve identidad estable por frame combinando
tracking local de ByteTrack con Re-ID local (posicion/apariencia) y, si esos
fallan, Re-ID en la nube via Gemini."""
import json
from typing import Optional

import cv2
import numpy as np

from deteccion.utils import safe_crop
from deteccion.gemini_reid import GeminiReID


def _compute_appearance(frame, box):
    crop = safe_crop(frame, box)
    if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 10:
        return None
    torso = crop[: crop.shape[0] // 2, :]
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0], None, [18], [0, 180]).flatten()
    s = cv2.calcHist([hsv], [1], None, [8],  [0, 256]).flatten()
    hist = np.concatenate([h, s]).astype(np.float32)
    hist /= hist.sum() + 1e-6
    return hist


def _appearance_sim(h1, h2):
    dist = cv2.compareHist(h1.reshape(-1, 1), h2.reshape(-1, 1), cv2.HISTCMP_BHATTACHARYYA)
    return 1.0 - dist


def _centroid_dist(box1, box2):
    cx1, cy1 = (box1[0] + box1[2]) / 2, (box1[1] + box1[3]) / 2
    cx2, cy2 = (box2[0] + box2[2]) / 2, (box2[1] + box2[3]) / 2
    return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5


class PersonTracker:
    """Mantiene todo el estado de tracking de una camara: mapeo bytetrack->id
    estable, tracks perdidos, historial de apariencia, y el registro de
    clientes activos del dia (con su descripcion visual y metodo de Re-ID)."""

    def __init__(
        self,
        frame_skip: int,
        max_dist: float,
        quick_expiry_frames: int,
        long_expiry_frames: int,
        appearance_thresh: float,
        max_app_samples: int,
        descripcion_streak_frames: int,
        gemini: GeminiReID,
        on_descripcion: Optional[callable] = None,
        obtener_candidatos_dia: Optional[callable] = None,
        on_nueva_persona: Optional[callable] = None,
    ) -> None:
        self.frame_skip                = frame_skip
        self.max_dist                  = max_dist
        self.quick_expiry_frames       = quick_expiry_frames
        self.long_expiry_frames        = long_expiry_frames
        self.appearance_thresh         = appearance_thresh
        self.max_app_samples           = max_app_samples
        self.descripcion_streak_frames = descripcion_streak_frames
        self.gemini                    = gemini
        # on_descripcion(sid, frame_count, metodo, descripcion, cliente_id_hint)
        # -> persona_db_id: persiste la descripcion en la BD apenas se genera
        # (no al final del video). obtener_candidatos_dia(excluir_ids) -> list:
        # consulta la BD (nunca memoria) por descripciones del mismo dia
        # calendario, para que Gemini/Groq pueda reidentificar tanto dentro de
        # este video como entre videos distintos analizados el mismo dia.
        # on_nueva_persona(sid, frame_count, metodo, cliente_id_hint) ->
        # persona_db_id: crea la fila de 'personas' apenas se resuelve un sid
        # nuevo (sin esperar la descripcion), para que las trayectorias de esa
        # persona ya tengan un persona_id valido desde el primer frame.
        self.on_descripcion         = on_descripcion
        self.obtener_candidatos_dia = obtener_candidatos_dia
        self.on_nueva_persona       = on_nueva_persona

        self.next_stable_id     = 1
        self.max_personas        = 0
        self.bytetrack_to_stable = {}
        self.lost_tracks         = {}
        self.active_boxes        = {}
        self.app_samples         = {}
        self.first_seen          = {}
        self.last_seen           = {}
        self.streak_frames       = {}
        self.registro_clientes   = {}
        self.metodo_reid         = {}
        # Metodos "locales" fijos; la clave del proveedor de nube (gemini/groq)
        # se agrega sola la primera vez que se usa (ver procesar_frame).
        self.conteo_metodo_reid  = {"nuevo": 0, "posicion": 0, "apariencia": 0}
        self.sid_to_persona_db_id = {}   # sid local (esta corrida) -> id en 'personas'
        self.sid_cliente_id_hint  = {}   # sid local nuevo -> cliente_id de otra sesion (mismo dia)

    # ── Registro de Clientes Activos del Dia ───────────────────────────────────
    def _registrar_o_actualizar_cliente(
        self, sid: int, frame_num: int, estado: str, descripcion: Optional[str] = None
    ) -> None:
        entrada = self.registro_clientes.setdefault(sid, {
            "primera_deteccion_frame": frame_num,
            "descripcion": None,
        })
        entrada["ultima_deteccion_frame"] = frame_num
        entrada["estado"] = estado
        if descripcion is not None:
            entrada["descripcion"] = descripcion

    # ── Resolucion de identidad ─────────────────────────────────────────────────
    def _resolver_identidad(self, frame, frame_count: int, bt_id, box, new_app):
        best_sid       = None
        best_metodo     = None
        best_pos_score = -1
        best_app_score = -1

        for sid, info in self.lost_tracks.items():
            frames_perdido = frame_count - info["last_frame"]
            if frames_perdido > self.long_expiry_frames:
                continue
            if frames_perdido <= self.quick_expiry_frames:
                d = _centroid_dist(box, info["last_box"])
                if d < self.max_dist:
                    score = 1.0 - (d / self.max_dist)
                    if score > best_pos_score:
                        best_pos_score = score
                        best_sid = sid
                        best_metodo = "posicion"
            elif new_app is not None and info.get("mean_app") is not None:
                sim = _appearance_sim(new_app, info["mean_app"])
                if sim >= self.appearance_thresh and sim > best_app_score:
                    best_app_score = sim
                    best_sid = sid
                    best_metodo = "apariencia"

        if best_sid is not None:
            del self.lost_tracks[best_sid]
            return best_sid, best_metodo

        # Disparador: el matching local (posicion/apariencia) fallo. Antes de
        # darlo por un cliente nuevo, se consulta a la BD (nunca la memoria de
        # esta corrida) por descripciones del mismo dia calendario -- incluye
        # tanto clientes "perdidos" de ESTE MISMO video (ya guardados ahi
        # apenas se describieron) como de otras sesiones ya cerradas.
        sid_gemini  = None
        cliente_hit = None
        if self.gemini.activo and self.obtener_candidatos_dia:
            excluir_ids = {
                self.sid_to_persona_db_id[s]
                for s in self.active_boxes
                if s in self.sid_to_persona_db_id
            }
            candidatos_bd = self.obtener_candidatos_dia(excluir_ids)
            if candidatos_bd:
                crop_nuevo = safe_crop(frame, box)
                if crop_nuevo.size > 0:
                    candidatos_gemini = [
                        {"sid": c["persona_id"], "descripcion": c["descripcion"]} for c in candidatos_bd
                    ]
                    resultado = self.gemini.clasificar(crop_nuevo, candidatos_gemini)
                    match = next((c for c in candidatos_bd if c["persona_id"] == resultado), None) \
                        if resultado is not None else None
                    if match is not None:
                        # ¿El candidato es un id perdido de ESTE MISMO video? -> reusar su sid local.
                        sid_local_previo = next(
                            (s for s, db_id in self.sid_to_persona_db_id.items()
                             if db_id == match["persona_id"] and s in self.lost_tracks),
                            None
                        )
                        if sid_local_previo is not None:
                            sid_gemini = sid_local_previo
                        else:
                            cliente_hit = match["cliente_id"]

        proveedor = type(self.gemini).__name__.replace("ReID", "").lower() or "gemini"

        if sid_gemini is not None:
            print(f"[{proveedor.capitalize()}] bytetrack {bt_id} reidentificado como cliente {sid_gemini} (mismo video)")
            del self.lost_tracks[sid_gemini]
            return sid_gemini, proveedor

        nuevo_sid = self.next_stable_id
        self.next_stable_id += 1
        metodo_final = proveedor if cliente_hit is not None else "nuevo"
        if cliente_hit is not None:
            self.sid_cliente_id_hint[nuevo_sid] = cliente_hit
            print(f"[{proveedor.capitalize()}] bytetrack {bt_id} -> nuevo id local {nuevo_sid}, "
                  f"mismo cliente que persona_id={cliente_hit} (otro video, mismo dia)")

        if self.on_nueva_persona:
            db_id = self.on_nueva_persona(nuevo_sid, frame_count, metodo_final, cliente_hit)
            if db_id is not None:
                self.sid_to_persona_db_id[nuevo_sid] = db_id

        return nuevo_sid, metodo_final

    # ── Procesamiento por frame ─────────────────────────────────────────────────
    def procesar_frame(self, frame, frame_count: int, results) -> list:
        """Resuelve la identidad de cada deteccion de este frame y actualiza
        todo el estado interno. Devuelve una lista de detecciones resueltas:
        [{"sid", "box", "cx", "cy"}, ...] (sin zona ni persistencia -- eso lo
        maneja el orquestador)."""
        detecciones = []
        current_stable_ids = set()

        r = results[0]
        if r.boxes is not None and r.boxes.id is not None:
            ids   = r.boxes.id.int().tolist()
            boxes = r.boxes.xyxy.tolist()

            if len(ids) > self.max_personas:
                self.max_personas = len(ids)

            for bt_id, box in zip(ids, boxes):
                app = _compute_appearance(frame, box)

                if bt_id not in self.bytetrack_to_stable:
                    sid_resuelto, metodo = self._resolver_identidad(frame, frame_count, bt_id, box, app)
                    self.bytetrack_to_stable[bt_id] = sid_resuelto
                    self.metodo_reid[sid_resuelto] = metodo
                    self.conteo_metodo_reid[metodo] = self.conteo_metodo_reid.get(metodo, 0) + 1

                sid = self.bytetrack_to_stable[bt_id]
                current_stable_ids.add(sid)
                self.active_boxes[sid] = box

                if sid not in self.first_seen:
                    self.first_seen[sid] = frame_count
                if self.last_seen.get(sid) == frame_count - self.frame_skip:
                    self.streak_frames[sid] = self.streak_frames.get(sid, 0) + 1
                else:
                    self.streak_frames[sid] = 1
                self.last_seen[sid] = frame_count

                # Generacion UNICA de la descripcion visual: recien cuando el
                # ID lleva suficientes frames consecutivos confirmados (buen
                # recorte, sin oclusiones raras) y todavia no tiene descripcion.
                descripcion_nueva = None
                if (self.gemini.activo
                        and self.streak_frames[sid] == self.descripcion_streak_frames
                        and not self.registro_clientes.get(sid, {}).get("descripcion")):
                    crop_confirmado = safe_crop(frame, box)
                    if crop_confirmado.size > 0:
                        descripcion_nueva = self.gemini.generar_descripcion(crop_confirmado)
                        if descripcion_nueva:
                            proveedor = type(self.gemini).__name__.replace("ReID", "").lower() or "gemini"
                            print(f"[{proveedor.capitalize()}] Cliente {sid} descrito: "
                                  f"{json.dumps(descripcion_nueva, ensure_ascii=False)}")
                            if self.on_descripcion:
                                db_id = self.on_descripcion(
                                    sid, frame_count, self.metodo_reid.get(sid, "nuevo"),
                                    descripcion_nueva, self.sid_cliente_id_hint.get(sid),
                                )
                                if db_id is not None:
                                    self.sid_to_persona_db_id[sid] = db_id
                self._registrar_o_actualizar_cliente(sid, frame_count, estado="activo", descripcion=descripcion_nueva)

                if app is not None:
                    samples = self.app_samples.setdefault(sid, [])
                    if len(samples) < self.max_app_samples:
                        samples.append(app)
                    else:
                        samples[frame_count % self.max_app_samples] = app

                cx = (box[0] + box[2]) / 2
                cy = (box[1] + box[3]) / 2
                detecciones.append({"sid": sid, "box": box, "cx": cx, "cy": cy})

        # Degradar a lost_tracks los sid que estaban activos y no aparecieron
        # en este frame. Corre SIEMPRE, incluso si este frame no tuvo ninguna
        # deteccion (r.boxes is None) -- si no, la gente que sale de cuadro
        # nunca se marcaria como perdida.
        for sid in list(self.active_boxes.keys()):
            if sid not in current_stable_ids:
                samples  = self.app_samples.get(sid, [])
                mean_app = np.mean(samples, axis=0).astype(np.float32) if samples else None
                self.lost_tracks[sid] = {
                    "last_box":   self.active_boxes[sid],
                    "last_frame": frame_count,
                    "mean_app":   mean_app,
                }
                del self.active_boxes[sid]
                self._registrar_o_actualizar_cliente(sid, frame_count, estado="perdido")

        return detecciones

    def expirar_perdidos(self, frame_count: int) -> None:
        """Purga definitivamente los tracks perdidos hace mas de long_expiry_frames."""
        expirados = [s for s, i in self.lost_tracks.items()
                     if frame_count - i["last_frame"] > self.long_expiry_frames]
        for sid in expirados:
            del self.lost_tracks[sid]

    def resumen_por_persona(self) -> list:
        """Devuelve los datos crudos por persona (orden ascendente de sid)
        para que metricas.py arme el reporte final."""
        return [
            {
                "sid":              sid,
                "first_frame":      self.first_seen[sid],
                "last_frame":       self.last_seen[sid],
                "metodo_reid":      self.metodo_reid.get(sid, "nuevo"),
                "descripcion":      self.registro_clientes.get(sid, {}).get("descripcion"),
                "cliente_id_hint":  self.sid_cliente_id_hint.get(sid),
            }
            for sid in sorted(self.first_seen.keys())
        ]

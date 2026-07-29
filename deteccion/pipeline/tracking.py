"""Deteccion de personas: resuelve identidad estable por frame combinando
tracking local de ByteTrack con Re-ID local (posicion/apariencia) y, si esos
fallan, Re-ID en la nube via Gemini."""
import json
from typing import Optional

import cv2
import numpy as np

from deteccion.utils import safe_crop
from deteccion.reid.gemini_reid import GeminiReID


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
        min_frames_confirmacion: int,
        gemini: GeminiReID,
        on_descripcion: Optional[callable] = None,
        obtener_candidatos_dia: Optional[callable] = None,
        on_nueva_persona: Optional[callable] = None,
        on_visita_cerrada: Optional[callable] = None,
        interaccion_frames_minimos: int = 3,
        caja_frames_minimos: int = 1,
    ) -> None:
        self.frame_skip                = frame_skip
        self.max_dist                  = max_dist
        self.quick_expiry_frames       = quick_expiry_frames
        self.long_expiry_frames        = long_expiry_frames
        self.appearance_thresh         = appearance_thresh
        self.max_app_samples           = max_app_samples
        self.descripcion_streak_frames = descripcion_streak_frames
        self.interaccion_frames_minimos = interaccion_frames_minimos
        self.caja_frames_minimos       = caja_frames_minimos
        # Piso de frames CONSECUTIVOS que un id debe sobrevivir antes de crear
        # su fila en 'personas' -- sin esto, un falso positivo de un solo
        # frame (reflejo, siluetas superpuestas, glitch de ByteTrack) queda
        # persistido como "cliente nuevo" igual que alguien que estuvo 20
        # minutos en el local. Ver auditoria del 2026-05-20: camara 3 tenia
        # ~4x mas detecciones de <2s (un solo punto de trayectoria) que
        # camara 4 mirando el mismo lugar, y eso explicaba buena parte de la
        # diferencia de conteo entre las dos.
        self.min_frames_confirmacion   = min_frames_confirmacion
        self.confirmados               = set()  # sids que ya pasaron el piso y tienen fila en 'personas'
        self.gemini                    = gemini
        # on_descripcion(sid, frame_count, metodo, descripcion, cliente_id_hint)
        # -> persona_db_id: persiste la descripcion en la BD apenas se genera
        # (no al final del video). obtener_candidatos_dia(excluir_ids,
        # frame_count) -> (list, momento): consulta la BD (nunca memoria) por
        # descripciones de camaras del mismo grupo fisico y dentro de una
        # ventana horaria cercana al frame actual, para que Gemini/Groq pueda
        # reidentificar tanto dentro de este video como entre videos
        # distintos (misma camara u otra del mismo grupo) cerca en el tiempo;
        # 'momento' (datetime del frame actual) se pasa a gemini.clasificar()
        # para el bonus de "mismo instante en otra camara" (ver GeminiReID).
        # on_nueva_persona(sid, frame_count, metodo, cliente_id_hint) ->
        # persona_db_id: crea la fila de 'personas' apenas se resuelve un sid
        # nuevo (sin esperar la descripcion), para que las trayectorias de esa
        # persona ya tengan un persona_id valido desde el primer frame.
        self.on_descripcion         = on_descripcion
        self.obtener_candidatos_dia = obtener_candidatos_dia
        self.on_nueva_persona       = on_nueva_persona
        # on_visita_cerrada(sid, frame_inicio, frame_fin, secuencia_zonas,
        # tomo_producto, acerco_a_caja): se llama cada vez que se cierra un
        # segmento de presencia continua ("visita") -- solo ante huecos
        # LARGOS (reconexion por apariencia o Groq/Gemini/Claude), nunca ante
        # huecos cortos por oclusion (reconexion por posicion). Sirve para
        # sumar tiempo real de permanencia sin contar los huecos, y ahora
        # tambien para clasificar el Escenario A/B/C de ESA visita (ver
        # pipeline/eventos.py) -- los 3 ultimos parametros vienen de
        # _cerrar_segmento(), que resetea el estado para la proxima visita.
        self.on_visita_cerrada      = on_visita_cerrada

        self.next_stable_id     = 1
        self.max_personas        = 0
        self.bytetrack_to_stable = {}
        self.lost_tracks         = {}
        self.active_boxes        = {}
        self.app_samples         = {}
        self.first_seen          = {}
        self.last_seen           = {}
        self.streak_frames       = {}
        self.segment_start       = {}   # sid -> frame_count de inicio de la visita ABIERTA actual
        self.registro_clientes   = {}
        self.metodo_reid         = {}
        # Metodos "locales" fijos; la clave del proveedor de nube (gemini/groq)
        # se agrega sola la primera vez que se usa (ver procesar_frame).
        self.conteo_metodo_reid  = {"nuevo": 0, "posicion": 0, "apariencia": 0}
        self.sid_to_persona_db_id = {}   # sid local (esta corrida) -> id en 'personas'
        self.sid_cliente_id_hint  = {}   # sid local nuevo -> cliente_id de otra sesion (mismo dia)

        # ── Estado por VISITA (segmento) para la clasificacion Escenario A/B/C ──
        # Se resetea en _cerrar_segmento() cada vez que arranca un segmento
        # nuevo para un sid (tanto en su primera aparicion como al reconectar
        # tras un hueco largo) -- ver pipeline/eventos.py.
        self.zona_actual         = {}   # sid -> ultimo zona_id registrado (para deduplicar)
        self.secuencia_zonas     = {}   # sid -> [zona_id, ...] en orden, sin repetidos consecutivos
        self.tomo_producto       = {}   # sid -> bool, confirmado (sticky) para la visita actual
        self.frames_interaccion  = {}   # sid -> contador de frames consecutivos con producto cerca
        self.acerco_a_caja       = {}   # sid -> bool, sticky para la visita actual (ver actualizar_acercamiento_caja)
        self.frames_cerca_caja   = {}   # sid -> contador de frames consecutivos cerca de Zona Caja

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

    # ── Secuencia de zonas + interaccion con producto (Escenario A/B/C) ─────────
    def actualizar_zona(self, sid: int, zona_id) -> None:
        """Registra un cambio de zona para la visita ABIERTA de este sid.
        'zona_id' None (fuera de cobertura de todos los poligonos) no aporta
        informacion de secuencia y se ignora. Se llama UNA vez por frame
        procesado y por persona (no solo en el muestreo periodico de
        trayectorias) para que la secuencia de zonas de eventos.py sea fiel
        al recorrido real, no una version diezmada de el."""
        if zona_id is None:
            return
        if self.zona_actual.get(sid) != zona_id:
            self.zona_actual[sid] = zona_id
            self.secuencia_zonas.setdefault(sid, []).append(zona_id)

    def actualizar_interaccion(self, sid: int, hay_producto_cerca: bool) -> None:
        """Acumula frames consecutivos con un producto 'cerca' (ver
        utils.producto_cerca_de_persona) y confirma tomar_producto=True al
        llegar a interaccion_frames_minimos. Una vez confirmado para la
        visita actual, no se vuelve a evaluar (sticky): la persona puede
        guardar el producto en el bolsillo/bolsa y dejar de 'tocarlo' sin que
        eso signifique que lo devolvio a la gondola."""
        if self.tomo_producto.get(sid):
            return
        if hay_producto_cerca:
            contador = self.frames_interaccion.get(sid, 0) + 1
            self.frames_interaccion[sid] = contador
            if contador >= self.interaccion_frames_minimos:
                self.tomo_producto[sid] = True
                print(f"[Interaccion] Persona {sid}: tomar_producto=True "
                      f"({contador} frames consecutivos con producto cerca)")
        else:
            self.frames_interaccion[sid] = 0

    def actualizar_acercamiento_caja(self, sid: int, cerca_de_caja: bool) -> None:
        """Acumula frames PROCESADOS consecutivos con la persona cerca de
        Zona Caja (ver utils.cerca_de_zona_tipo) y confirma paso_por_caja=True
        al llegar a caja_frames_minimos (ver config.CAJA_PERMANENCIA_MINIMA_SEG).
        Se probo antes exigir que hubiera OTRA persona (posible empleado)
        presente al mismo tiempo, pero en un local con empleados fijos en Zona
        Caja esa condicion se cumple casi siempre -- no discriminaba "vino a
        pagar" de "paso caminando cerca del mostrador". La PERMANENCIA si lo
        hace: alguien de paso no se queda parado ahi varios segundos seguidos.

        En pipeline/eventos.py, paso_por_caja es la condicion DOMINANTE para
        COMPRA_NORMAL: no importa si tambien hubo tomar_producto (agarrar
        algo de gondola/heladera) o no -- cubre tanto la compra en gondola
        como la compra directa en el mostrador o un pedido preparado en
        cocina, casos donde nunca hay un producto que YOLO pueda detectar.

        Sticky una vez confirmado (no se re-evalua), mismo criterio que
        actualizar_interaccion: la persona puede alejarse del mostrador
        despues de pagar sin que eso signifique que no pago."""
        if self.acerco_a_caja.get(sid):
            return
        if cerca_de_caja:
            contador = self.frames_cerca_caja.get(sid, 0) + 1
            self.frames_cerca_caja[sid] = contador
            if contador >= self.caja_frames_minimos:
                self.acerco_a_caja[sid] = True
                print(f"[Caja] Persona {sid}: paso_por_caja=True "
                      f"({contador} frames consecutivos cerca del mostrador)")
        else:
            self.frames_cerca_caja[sid] = 0

    def _cerrar_segmento(self, sid: int, frame_inicio: int, frame_fin: int) -> None:
        """Punto UNICO de cierre de visita: junta la secuencia de zonas, el
        tomar_producto y el acercamiento a caja acumulados durante el
        segmento que se esta cerrando, se los pasa a on_visita_cerrada (que
        arma y persiste el evento Escenario A/B/C via pipeline/eventos.py), y
        resetea el estado por sid para que la PROXIMA visita (si el sid se
        reconecta mas adelante) arranque de cero -- sin esto, un cliente que
        vuelve horas despues por Re-ID de nube heredaria la secuencia/
        tomar_producto/acerco_a_caja de una visita anterior ya reportada."""
        if self.on_visita_cerrada:
            secuencia = list(self.secuencia_zonas.get(sid, []))
            self.on_visita_cerrada(
                sid, frame_inicio, frame_fin, secuencia,
                self.tomo_producto.get(sid, False), self.acerco_a_caja.get(sid, False),
            )
        self.zona_actual.pop(sid, None)
        self.secuencia_zonas.pop(sid, None)
        self.tomo_producto.pop(sid, None)
        self.frames_interaccion.pop(sid, None)
        self.acerco_a_caja.pop(sid, None)
        self.frames_cerca_caja.pop(sid, None)

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
            if best_metodo == "apariencia":
                # Hueco LARGO (reconexion por apariencia, no por posicion): la
                # visita anterior se cierra en el ultimo frame donde se la vio,
                # y arranca una nueva ahora -- aunque el sid/persona_id sigan
                # siendo los mismos, el tiempo perdido en el medio no cuenta
                # como permanencia.
                if best_sid in self.segment_start:
                    self._cerrar_segmento(
                        best_sid, self.segment_start[best_sid], self.lost_tracks[best_sid]["last_frame"]
                    )
                self.segment_start[best_sid] = frame_count
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
            candidatos_bd, momento = self.obtener_candidatos_dia(excluir_ids, frame_count)
            if candidatos_bd:
                crop_nuevo = safe_crop(frame, box)
                if crop_nuevo.size > 0:
                    candidatos_gemini = [
                        {"sid": c["persona_id"], "descripcion": c["descripcion"],
                         "primera_deteccion": c["primera_deteccion"]}
                        for c in candidatos_bd
                    ]
                    resultado = self.gemini.clasificar(crop_nuevo, candidatos_gemini, momento=momento)
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
            # Reconexion via nube = hueco largo por definicion (el matching
            # local ya fallo antes de llegar aca): cierra la visita anterior
            # y arranca una nueva, mismo criterio que el caso "apariencia".
            if sid_gemini in self.segment_start:
                self._cerrar_segmento(
                    sid_gemini, self.segment_start[sid_gemini], self.lost_tracks[sid_gemini]["last_frame"]
                )
            self.segment_start[sid_gemini] = frame_count
            del self.lost_tracks[sid_gemini]
            return sid_gemini, proveedor

        nuevo_sid = self.next_stable_id
        self.next_stable_id += 1
        self.segment_start[nuevo_sid] = frame_count
        metodo_final = proveedor if cliente_hit is not None else "nuevo"
        if cliente_hit is not None:
            self.sid_cliente_id_hint[nuevo_sid] = cliente_hit
            print(f"[{proveedor.capitalize()}] bytetrack {bt_id} -> nuevo id local {nuevo_sid}, "
                  f"mismo cliente que persona_id={cliente_hit} (otro video, mismo dia)")

        # OJO: aca NO se crea la fila en 'personas' todavia -- se crea recien
        # en procesar_frame() cuando el sid confirme min_frames_confirmacion
        # frames consecutivos (ver comentario en __init__). Minting inmediato
        # persistia hasta el ultimo falso positivo de un solo frame.
        return nuevo_sid, metodo_final

    # ── Procesamiento por frame ─────────────────────────────────────────────────
    def procesar_frame(self, frame, frame_count: int, results) -> list:
        """Resuelve la identidad de cada deteccion de este frame y actualiza
        todo el estado interno. Devuelve una lista de detecciones resueltas:
        [{"sid", "box", "cx", "cy"}, ...] (sin zona ni persistencia -- eso lo
        maneja el orquestador). "cx"/"cy" son la posicion en el PISO (centro
        horizontal, base vertical del box) -- ver comentario mas abajo."""
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

                # Confirmacion tardia: recien aca (streak consecutivo, no un
                # solo frame suelto) se crea la fila de 'personas' -- ver
                # min_frames_confirmacion en __init__.
                if (sid not in self.confirmados
                        and self.streak_frames[sid] >= self.min_frames_confirmacion):
                    self.confirmados.add(sid)
                    if self.on_nueva_persona:
                        db_id = self.on_nueva_persona(
                            sid, self.first_seen[sid], self.metodo_reid.get(sid, "nuevo"),
                            self.sid_cliente_id_hint.get(sid),
                        )
                        if db_id is not None:
                            self.sid_to_persona_db_id[sid] = db_id

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

                # 'cy' es la BASE del box (altura de los pies), no el centro
                # vertical -- esta posicion es la que despues usan el heatmap
                # y get_zona_id() (via main.py) para decidir en que zona cae
                # la persona. El centro geometrico del box (cabeza a pies)
                # queda a la altura del pecho/cintura, y desde una camara
                # elevada mirando en angulo hacia abajo, ese punto se proyecta
                # en la imagen mas arriba y mas "atras" (hacia el fondo) que
                # los pies reales -- suficiente para que alguien parado del
                # lado del cliente, pegado al mostrador, caiga adentro del
                # poligono de Zona Caja (que representa el piso) aunque sus
                # pies esten del otro lado. La base del box es la mejor
                # aproximacion en 2D de donde esta parada la persona.
                # OJO: esto NO afecta _centroid_dist() -- esa funcion recibe
                # el box crudo y calcula su propio centro para reconectar
                # tracks entre frames, que es un uso distinto (continuidad
                # de movimiento, no posicion real en el piso).
                cx = (box[0] + box[2]) / 2
                cy = box[3]
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
            if sid in self.segment_start:
                self._cerrar_segmento(sid, self.segment_start[sid], self.lost_tracks[sid]["last_frame"])
                del self.segment_start[sid]
            del self.lost_tracks[sid]

    def cerrar_visitas_abiertas(self, frame_final: int) -> None:
        """Al terminar el video, cierra cualquier visita que haya quedado
        abierta -- gente todavia activa en el ultimo frame, o perdida pero
        sin llegar a expirar -- para que su tiempo cuente como permanencia.
        Sin esto, la ultima visita de cada persona nunca llegaria a la BD."""
        for sid, inicio in list(self.segment_start.items()):
            salida = self.last_seen.get(sid, frame_final)
            self._cerrar_segmento(sid, inicio, salida)
        self.segment_start.clear()

    def resumen_por_persona(self) -> list:
        """Devuelve los datos crudos por persona (orden ascendente de sid)
        para que metricas.py arme el reporte final. Solo incluye sids
        CONFIRMADOS (ver min_frames_confirmacion) -- un id que nunca junto
        suficientes frames consecutivos fue ruido de deteccion, no una
        persona real, y no debe contarse ni persistirse."""
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
            if sid in self.confirmados
        ]

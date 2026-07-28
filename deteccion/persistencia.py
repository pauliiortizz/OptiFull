"""Capa de persistencia contra Supabase (Postgres). Todos los metodos son
no-op si no hay conexion (BD deshabilitada o inalcanzable) -- el pipeline
sigue funcionando solo con el reporte por consola."""
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

from deteccion.utils import frame_to_dt, get_zona_id
from deteccion.reid.gemini_reid import _comparar_descriptores, _obligatorios_coinciden


def _decidir_continuidad_temporal(desc_previa: dict, desc_nueva: dict, delta_seg: float,
                                   umbral_seg: float, umbral_alta_confianza_seg: float) -> dict:
    """Decide si dos personas separadas por el CORTE entre dos videos
    consecutivos de la MISMA camara son la misma, combinando ventana de
    tiempo + coincidencia visual (ver fusionar_continuidad_sesiones):
    - 'delta_seg' > 'umbral_seg' (la persona no fue vista ni cerca del corte
      de ningun lado) -> NO MATCH, sin mirar descripcion.
    - Color de ropa obligatorio (superior/inferior) NO coincide, donde
      visible en ambos lados -> NO MATCH ("discrepancia visual clara"),
      sin importar cuan chico sea el hueco.
    - Sin NINGUN campo visible en comun entre las dos descripciones -> NO
      MATCH: no hay evidencia visual real para confirmar, aunque el hueco
      de tiempo sea minimo.
    - Si pasa los tres filtros: MATCH, con confianza 'Alta' si el hueco es
      <= 'umbral_alta_confianza_seg' (practicamente el mismo instante --
      solo pudo pasar por el corte del archivo) o 'Media' si cae dentro de
      la ventana mas amplia mostrando igual coincidencia visual.
    Devuelve {'es_coincidencia', 'confianza', 'justificacion'} -- 'confianza'
    y 'justificacion' son para logging/auditoria, no afectan la decision de
    fusionar en si (esa es 'es_coincidencia')."""
    if delta_seg > umbral_seg:
        return {
            "es_coincidencia": False, "confianza": None,
            "justificacion": f"Hueco de {delta_seg:.1f}s supera la ventana de continuidad "
                              f"({umbral_seg:.0f}s) -> distinta persona.",
        }
    if not _obligatorios_coinciden(desc_previa, desc_nueva):
        return {
            "es_coincidencia": False, "confianza": None,
            "justificacion": f"Color de ropa obligatorio no coincide (hueco {delta_seg:.1f}s) "
                              f"-> distinta persona.",
        }
    coincidencias, comparables = _comparar_descriptores(desc_previa, desc_nueva)
    if comparables == 0:
        return {
            "es_coincidencia": False, "confianza": None,
            "justificacion": f"Sin ningun campo visible en comun para comparar (hueco "
                              f"{delta_seg:.1f}s) -> se descarta por falta de evidencia.",
        }
    confianza = "Alta" if delta_seg <= umbral_alta_confianza_seg else "Media"
    return {
        "es_coincidencia": True, "confianza": confianza,
        "justificacion": f"Hueco de {delta_seg:.1f}s en el corte de archivo + {coincidencias}/"
                          f"{comparables} caracteristicas visuales coincidentes -> misma persona.",
    }


class Persistencia:
    def __init__(self, database_url: Optional[str], has_db: bool, guardar_trayectorias: bool,
                 camara_nombres: dict, grupos_camara: Optional[dict] = None,
                 reid_ventana_horas: float = 1.0) -> None:
        self.database_url         = database_url
        self.has_db                = has_db
        self.guardar_trayectorias = guardar_trayectorias
        self.camara_nombres        = camara_nombres
        # camara_id -> lista de camara_id del mismo espacio fisico (incluida
        # ella misma); una camara no presente en el dict se busca solo a si
        # misma. Ver GRUPOS_CAMARA en config.py.
        self.grupos_camara         = grupos_camara or {}
        self.reid_ventana_horas    = reid_ventana_horas
        self.conn = None
        # sid (local, de esta corrida) -> id de 'personas' en la BD. Se llena
        # apenas Gemini genera una descripcion (guardar_descripcion_persona),
        # asi el analisis no pierde nada si se corta antes de terminar el video.
        self.persona_db_ids: dict = {}

    def conectar(self) -> bool:
        if not self.has_db or not self.database_url:
            return False
        try:
            self.conn = psycopg2.connect(self.database_url)
            print("[DB] Conexion exitosa.")
            return True
        except Exception as e:
            print(f"[DB] No se pudo conectar: {e}")
            self.conn = None
            return False

    def _con_reconexion(self, fn, default=None):
        """Ejecuta fn() (que arranca revisando 'self.conn'); si la conexion se
        cayo a mitad de un analisis (corte de red, timeout del pooler, etc.)
        psycopg2 tira una excepcion y el resto del video se perderia entero --
        aca se intenta reconectar UNA vez y reintentar antes de resignarse a
        devolver 'default' (mismo criterio de no-op que cuando nunca hubo
        conexion, para no cortar el analisis por un hipo transitorio)."""
        try:
            return fn()
        except (psycopg2.Error, psycopg2.InterfaceError) as e:
            print(f"[DB] Conexion perdida ({e}); intentando reconectar...")
            try:
                if self.conn:
                    self.conn.close()
            except Exception:
                pass
            self.conn = None
            if self.conectar():
                try:
                    return fn()
                except (psycopg2.Error, psycopg2.InterfaceError) as e2:
                    print(f"[DB] Fallo de nuevo tras reconectar, se omite: {e2}")
            else:
                print("[DB] No se pudo reconectar, se omite esta operacion.")
            return default

    def cargar_zonas(self, camara_id: int) -> list:
        def _run():
            if not self.conn:
                return []
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, nombre, tipo, poligono FROM zonas WHERE camara_id = %s",
                (camara_id,)
            )
            zonas = []
            for row in cur.fetchall():
                zonas.append({"id": row["id"], "nombre": row["nombre"], "tipo": row["tipo"], "poligono": row["poligono"]})
            cur.close()
            return zonas
        return self._con_reconexion(_run, default=[])

    def _asegurar_camara(self, camara_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM camaras WHERE id = %s", (camara_id,))
        if cur.fetchone() is None:
            nombre, ubicacion = self.camara_nombres.get(camara_id, (f"Camara {camara_id:02d}", "Sin ubicacion"))
            cur.execute(
                "INSERT INTO camaras (id, nombre, ubicacion, rtsp_url) VALUES (%s, %s, %s, %s)",
                (camara_id, nombre, ubicacion, f"rtsp://192.168.1.{9 + camara_id}:554/stream1")
            )
            self.conn.commit()
            print(f"[DB] Camara {camara_id} creada: '{nombre}'")
        cur.close()

    def buscar_sesion_por_archivo(self, archivo_path: str) -> Optional[dict]:
        """Busca si un video con el MISMO NOMBRE DE ARCHIVO ya fue analizado
        -- para frenar ANTES de re-procesarlo y duplicar personas/
        trayectorias/heatmaps si alguien pasa por error la ruta de un video
        viejo. Compara solo el nombre de archivo (ej. 'D04_20260520214426.mp4'),
        nunca la ruta completa: la carpeta o la letra de unidad puede cambiar
        (ej. el mismo pendrive montado como D: una vez y como E: otra) sin que
        eso signifique que es un video distinto."""
        def _run():
            if not self.conn:
                return None
            nombre_archivo = Path(archivo_path).name
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT id, camara_id, inicio, archivo_path FROM sesiones_video ORDER BY id")
            for row in cur.fetchall():
                if row["archivo_path"] and Path(row["archivo_path"]).name == nombre_archivo:
                    cur.close()
                    return dict(row)
            cur.close()
            return None
        return self._con_reconexion(_run, default=None)

    def crear_sesion(self, camara_id: int, inicio: datetime, archivo_path: str) -> Optional[int]:
        def _run():
            if not self.conn:
                return None
            self._asegurar_camara(camara_id)
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO sesiones_video (camara_id, inicio, archivo_path) VALUES (%s, %s, %s) RETURNING id",
                (camara_id, inicio, str(Path(archivo_path).resolve()))
            )
            sesion_id = cur.fetchone()[0]
            self.conn.commit()
            cur.close()
            print(f"[DB] Sesion creada -> id={sesion_id}, camara_id={camara_id}, inicio={inicio}")
            return sesion_id
        return self._con_reconexion(_run, default=None)

    def actualizar_resolucion_sesion(self, sesion_id, frame_w: int, frame_h: int) -> None:
        """Guarda la resolucion REAL del video (frame_w/frame_h) apenas se
        abre con cv2 -- las coordenadas de 'trayectorias' (centroide_x/y) se
        guardan en ese mismo espacio de pixeles, y sin esto no hay forma de
        saber a que resolucion corresponden para poder alinearlas contra la
        foto fija del local en el frontend (que puede tener otra resolucion
        distinta a la del video)."""
        def _run():
            if not self.conn or not sesion_id:
                return
            cur = self.conn.cursor()
            cur.execute(
                "UPDATE sesiones_video SET frame_w = %s, frame_h = %s WHERE id = %s",
                (frame_w, frame_h, sesion_id)
            )
            self.conn.commit()
            cur.close()
        self._con_reconexion(_run, default=None)

    def actualizar_heartbeat(self, sesion_id) -> None:
        """Marca que esta sesion sigue viva -- se llama periodicamente durante
        el analisis (ver main.py, mismo cadencia que el flush de trayectorias).
        limpiar_sesiones_incompletas() usa esto para no confundir una sesion
        que otra maquina/proceso todavia esta procesando en paralelo con una
        que quedo abandonada de verdad (ver comentario en esa funcion)."""
        def _run():
            if not self.conn or not sesion_id:
                return
            cur = self.conn.cursor()
            cur.execute("UPDATE sesiones_video SET heartbeat = NOW() WHERE id = %s", (sesion_id,))
            self.conn.commit()
            cur.close()
        self._con_reconexion(_run, default=None)

    def cerrar_sesion(self, sesion_id, fin: datetime) -> None:
        def _run():
            if not self.conn or not sesion_id:
                return
            cur = self.conn.cursor()
            cur.execute("UPDATE sesiones_video SET fin = %s WHERE id = %s", (fin, sesion_id))
            self.conn.commit()
            cur.close()
            print(f"[DB] Sesion cerrada -> fin={fin}")
        self._con_reconexion(_run, default=None)

    def borrar_sesion(self, sesion_id: Optional[int]) -> None:
        """Borra una sesion de video y TODO lo que dependa de ella (personas,
        trayectorias, visitas -- via ON DELETE CASCADE en el schema) y
        cualquier heatmap que la referencie. Se usa para limpiar sesiones que
        quedaron a MEDIO analizar (Ctrl+C, corte de cupo de API, crash,
        cierre de la PC, etc.) -- nunca hay que dejar en la BD personas o
        trayectorias de un video que no termino de procesarse, porque
        contaminan tanto los reportes como el Re-ID entre camaras."""
        if not sesion_id:
            return

        def _run():
            if not self.conn:
                return
            cur = self.conn.cursor()
            # Por si la interrupcion dejo una transaccion a medias (ej. un
            # execute() cortado por Ctrl+C), se limpia antes de borrar --
            # si no, el DELETE podria fallar o quedar bloqueado.
            self.conn.rollback()
            cur.execute("DELETE FROM mapas_calor WHERE sesion_id = %s", (sesion_id,))
            cur.execute("DELETE FROM sesiones_video WHERE id = %s", (sesion_id,))
            borrada = cur.rowcount > 0
            self.conn.commit()
            cur.close()
            if borrada:
                print(f"[DB] Sesion incompleta id={sesion_id} borrada "
                      f"(junto con sus personas/trayectorias/visitas).")
        self._con_reconexion(_run, default=None)

    def limpiar_sesiones_incompletas(self, excluir_id: Optional[int] = None,
                                      inactividad_min: float = 20.0) -> int:
        """Busca sesiones de video sin 'fin' -- quedaron a medio analizar en
        una corrida anterior que se corto antes de llegar a cerrar_sesion()
        (crash, Ctrl+C, cupo de API agotado, corte de luz, etc.) -- y las
        borra junto con todos sus datos dependientes. Se llama al arrancar
        CADA analisis nuevo, asi las sesiones fantasma de una corrida
        interrumpida nunca llegan a contaminar el Re-ID entre camaras ni los
        reportes. 'excluir_id', si viene, es la sesion recien creada en ESTA
        corrida (nunca hay que borrarla a si misma).

        OJO: 'fin IS NULL' NO alcanza para decidir "abandonada" -- puede haber
        OTRA maquina/proceso analizando otra camara en paralelo contra la
        MISMA base (Supabase compartida), y esa sesion tambien tiene 'fin IS
        NULL' mientras esta en curso (ver incidente real: la sesion en curso
        de una compu se borro porque la otra arranco un analisis nuevo al
        mismo tiempo y la vio como "incompleta"). Por eso ademas se exige que
        'heartbeat' (que el proceso dueno actualiza periodicamente, ver
        actualizar_heartbeat) este mas viejo que 'inactividad_min' minutos --
        recien ahi se puede asumir que nadie la sigue actualizando de verdad."""
        def _run():
            if not self.conn:
                return 0
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, camara_id, inicio, archivo_path FROM sesiones_video "
                "WHERE fin IS NULL AND heartbeat < NOW() - %s::interval",
                (f"{inactividad_min} minutes",)
            )
            pendientes = [r for r in cur.fetchall() if r["id"] != excluir_id]
            cur.close()
            for s in pendientes:
                print(f"[DB] Sesion incompleta detectada -> id={s['id']}, camara={s['camara_id']}, "
                      f"inicio={s['inicio']}, archivo='{s['archivo_path']}' -- borrando...")
                self.borrar_sesion(s["id"])
            return len(pendientes)
        return self._con_reconexion(_run, default=0)

    def crear_persona(self, sesion_id, sid: int, frame_num: int, fps: float,
                       inicio: datetime, metodo_reid: str,
                       cliente_id_hint: Optional[int] = None) -> Optional[int]:
        """Crea la fila de 'personas' apenas se resuelve un sid nuevo -- sin
        esperar a que Gemini/Groq genere su descripcion. Asi cada trayectoria
        ya tiene un persona_id valido desde el primer frame, y se puede ir
        guardando en bloques periodicos en vez de todo junto al final del
        video (que se perdia entero si el analisis se cortaba antes)."""
        if sid in self.persona_db_ids:
            return self.persona_db_ids[sid]

        def _run():
            if not self.conn or not sesion_id:
                return None
            ts = frame_to_dt(frame_num, fps, inicio)
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO personas "
                "(sesion_id, primera_deteccion, ultima_deteccion, metodo_reid) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (sesion_id, ts, ts, metodo_reid)
            )
            db_id = cur.fetchone()[0]
            self.persona_db_ids[sid] = db_id
            cliente_id = cliente_id_hint if cliente_id_hint is not None else db_id
            cur.execute("UPDATE personas SET cliente_id = %s WHERE id = %s", (cliente_id, db_id))
            self.conn.commit()
            cur.close()
            extra = f" (mismo cliente que persona_id={cliente_id_hint})" if cliente_id_hint else ""
            print(f"[DB] Persona nueva registrada -> persona_id={db_id} (metodo={metodo_reid}){extra}")
            return db_id
        return self._con_reconexion(_run, default=None)

    def guardar_trayectorias_parcial(self, traj_chunk: list, fps: float, inicio: datetime,
                                      camara_id: Optional[int] = None) -> int:
        """Inserta en bloque los puntos de trayectoria acumulados hasta ahora
        -- se llama periodicamente durante el analisis (no solo al final), asi
        un corte a mitad de video no hace perder todo el recorrido. Usa
        self.persona_db_ids para resolver sid -> persona_id; los puntos de un
        sid que todavia no tiene persona_id (rarisimo -- solo si la BD estaba
        caida justo cuando se creo ese sid) se descartan en silencio, igual
        que ya pasaba antes en el guardado final."""
        if not traj_chunk:
            return 0

        def _run():
            if not self.conn:
                return 0
            cur = self.conn.cursor()
            persona_ids = {
                self.persona_db_ids[t["sid"]] for t in traj_chunk if t["sid"] in self.persona_db_ids
            }
            empleado_por_persona = {}
            if persona_ids:
                # Resuelve es_empleado via CUALQUIER fila de la cadena de
                # cliente_id, no solo la raiz -- mismo criterio EXISTS que
                # limpiar_trayectorias_fuera_de_zona (ver comentario ahi).
                cur.execute(
                    "SELECT p.id, EXISTS ("
                    "  SELECT 1 FROM personas p2 "
                    "  WHERE p2.cliente_id = COALESCE(p.cliente_id, p.id) AND p2.es_empleado"
                    ") FROM personas p WHERE p.id = ANY(%s)",
                    (list(persona_ids),)
                )
                empleado_por_persona = dict(cur.fetchall())
            batch = []
            for t in traj_chunk:
                persona_db_id = self.persona_db_ids.get(t["sid"])
                if persona_db_id is None:
                    continue
                ts = frame_to_dt(t["frame"], fps, inicio)
                batch.append((
                    persona_db_id, t["zona_id"], camara_id,
                    empleado_por_persona.get(persona_db_id, False), ts,
                    round(t["cx"], 2), round(t["cy"], 2),
                    round(t["box"][0], 2), round(t["box"][1], 2),
                    round(t["box"][2], 2), round(t["box"][3], 2),
                ))
            if not batch:
                cur.close()
                return 0
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO trayectorias "
                "(persona_id, zona_id, camara_id, es_empleado, timestamp, centroide_x, centroide_y, "
                " bbox_x1, bbox_y1, bbox_x2, bbox_y2) "
                "VALUES %s",
                batch,
            )
            self.conn.commit()
            cur.close()
            print(f"[DB] {len(batch)} trayectorias guardadas (parcial, durante el analisis).")
            return len(batch)
        return self._con_reconexion(_run, default=0)

    def guardar_visita(self, persona_db_id: Optional[int], frame_inicio: int, frame_fin: int,
                        fps: float, inicio: datetime) -> None:
        """Inserta un segmento de presencia continua ("visita") ya cerrado --
        ver PersonTracker.on_visita_cerrada. persona_db_id puede ser None si
        el sid nunca llego a tener fila en 'personas' (BD caida al crearlo);
        en ese caso se descarta en silencio, mismo criterio que trayectorias."""
        if persona_db_id is None:
            return

        def _run():
            if not self.conn:
                return
            entrada = frame_to_dt(frame_inicio, fps, inicio)
            salida  = frame_to_dt(frame_fin, fps, inicio)
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO visitas (persona_id, entrada, salida) VALUES (%s, %s, %s)",
                (persona_db_id, entrada, salida)
            )
            self.conn.commit()
            cur.close()
        self._con_reconexion(_run, default=None)

    def limpiar_trayectorias_fuera_de_zona(self) -> int:
        """Borra puntos de 'trayectorias' que violan la regla de negocio:
        Zona Caja es exclusiva de empleados (maximo 3 en todo el local, ver
        auditar_sesion()), Zona Gondolas/Salon son exclusivas de clientes --
        un empleado ahi, o un cliente en Zona Caja, es un punto mal
        clasificado. El estado de empleado se resuelve por CLIENTE_ID
        agrupado (EXISTS contra cualquier fila de esa cadena con
        es_empleado=true), no por la fila puntual de 'personas' -- las
        fusiones retroactivas (fusionar_cross_camara_dia/
        fusionar_continuidad_sesiones) solo reapuntan cliente_id, no
        propagan es_empleado a todas las filas del grupo, asi que confiar
        solo en la fila puntual dejaria pasar casos ya fusionados con un
        empleado conocido. No toca 'personas.zona_id' (la zona dominante ya
        calculada por auditar_sesion) ni borra personas, solo los puntos de
        trayectoria puntuales que quedan mal ubicados. Devuelve cuantos
        puntos se borraron."""
        if not self.conn:
            return 0

        def _run():
            cur = self.conn.cursor()
            cur.execute("""
                DELETE FROM trayectorias t
                USING personas p, zonas z
                WHERE t.persona_id = p.id AND t.zona_id = z.id
                AND (
                    (z.tipo = 'caja' AND NOT EXISTS (
                        SELECT 1 FROM personas p2
                        WHERE p2.cliente_id = COALESCE(p.cliente_id, p.id) AND p2.es_empleado
                    ))
                    OR
                    (z.tipo IN ('gondola', 'otro') AND EXISTS (
                        SELECT 1 FROM personas p2
                        WHERE p2.cliente_id = COALESCE(p.cliente_id, p.id) AND p2.es_empleado
                    ))
                )
            """)
            borrados = cur.rowcount
            self.conn.commit()
            cur.close()
            print(f"[DB] Limpieza de trayectorias fuera de zona: {borrados} puntos borrados.")
            return borrados
        return self._con_reconexion(_run, default=0)

    def completar_camara_id_trayectorias(self) -> int:
        """Rellena 'trayectorias.camara_id' (columna agregada para no tener
        que pasar por 'personas' -> 'sesiones_video' en cada consulta que
        filtra por camara) para las filas que ya existian antes de agregarla
        o que por algun motivo quedaron en NULL. Lo resuelve via
        persona_id -> sesiones_video.camara_id, que es la fuente de verdad.
        Devuelve cuantas filas se actualizaron."""
        if not self.conn:
            return 0

        def _run():
            cur = self.conn.cursor()
            cur.execute("""
                UPDATE trayectorias AS t SET camara_id = sv.camara_id
                FROM personas p
                JOIN sesiones_video sv ON sv.id = p.sesion_id
                WHERE t.persona_id = p.id
                AND (t.camara_id IS NULL OR t.camara_id != sv.camara_id)
            """)
            actualizados = cur.rowcount
            self.conn.commit()
            cur.close()
            print(f"[DB] camara_id completado en trayectorias: {actualizados} filas actualizadas.")
            return actualizados
        return self._con_reconexion(_run, default=0)

    def sincronizar_es_empleado_trayectorias(self, cliente_id: Optional[int] = None,
                                              sesion_id: Optional[int] = None) -> int:
        """Sincroniza 'trayectorias.es_empleado' (copia desnormalizada) con el
        estado actual de 'personas'. Una cadena de cliente_id es empleado si
        CUALQUIER fila de la cadena tiene es_empleado=true -- NO solo la raiz
        (id = cliente_id): guardar_descripcion_persona() y
        reclasificar_por_mayoria_zona() pueden marcar ese flag directamente en
        una fila hija al fusionarla contra un empleado ya conocido, sin tocar
        la raiz. Mismo criterio EXISTS que ya usa
        limpiar_trayectorias_fuera_de_zona -- hay que mantener los dos
        alineados. Sin 'cliente_id' ni 'sesion_id', recorre TODA la tabla
        (backfill inicial o resync general); con 'cliente_id', se limita a
        esa cadena puntual (uso tipico: justo despues de POST
        /personas/<id>/empleado); con 'sesion_id', a las personas de esa
        sesion (uso en vivo, justo despues de reclasificar_por_mayoria_zona
        en main.py -- evita recorrer TODA la BD en cada video analizado). Los
        dos filtros son excluyentes entre si; si se pasan ambos, gana
        'cliente_id'. Devuelve cuantas filas se actualizaron."""
        if not self.conn:
            return 0

        def _run():
            cur = self.conn.cursor()
            if cliente_id is not None:
                filtro, params = "WHERE COALESCE(p.cliente_id, p.id) = %s", (cliente_id,)
            elif sesion_id is not None:
                filtro, params = "WHERE p.sesion_id = %s", (sesion_id,)
            else:
                filtro, params = "", ()
            cur.execute(f"""
                UPDATE trayectorias AS t SET es_empleado = sub.empleado
                FROM (
                    SELECT p.id AS persona_id, EXISTS (
                        SELECT 1 FROM personas p2
                        WHERE p2.cliente_id = COALESCE(p.cliente_id, p.id) AND p2.es_empleado
                    ) AS empleado
                    FROM personas p
                    {filtro}
                ) AS sub
                WHERE t.persona_id = sub.persona_id AND t.es_empleado != sub.empleado
            """, params)
            actualizados = cur.rowcount
            self.conn.commit()
            cur.close()
            print(f"[DB] es_empleado sincronizado en trayectorias: {actualizados} filas actualizadas.")
            return actualizados
        return self._con_reconexion(_run, default=0)

    def poblar_empleados_desde_personas(self, nombres: dict) -> dict:
        """Siembra 'empleados'/'empleados_descripciones' a partir de las
        apariciones YA confirmadas a mano en 'personas' (es_empleado = true),
        agrupadas por cadena de cliente_id -- una fila por CADENA distinta
        (cada una es, en teoria, un empleado real) con todas sus descripciones
        DISTINTAS como variantes de referencia (la misma cadena puede tener
        docenas de apariciones casi identicas; solo importan las variantes
        unicas). 'nombres' mapea cliente_id (raiz de la cadena) -> nombre a
        usarle en 'empleados'; una raiz sin entrada en 'nombres' se nombra
        'Empleado <cliente_id>'. Solo-siembra: si 'empleados' YA tiene filas,
        no hace nada (evita duplicar si se corre dos veces) y devuelve
        {'ya_poblado': True}. Devuelve {'empleados': N, 'descripciones': M}."""
        if not self.conn:
            return {}

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT count(*) AS n FROM empleados")
            if cur.fetchone()["n"] > 0:
                cur.close()
                print("[DB] 'empleados' ya tiene filas -- no se vuelve a poblar (evita duplicar).")
                return {"ya_poblado": True}

            cur.execute(
                "SELECT DISTINCT COALESCE(cliente_id, id) AS raiz FROM personas "
                "WHERE es_empleado = true ORDER BY raiz"
            )
            raices = [r["raiz"] for r in cur.fetchall()]

            total_desc = 0
            for raiz in raices:
                nombre = nombres.get(raiz, f"Empleado {raiz}")
                cur.execute(
                    "INSERT INTO empleados (nombre) VALUES (%s) RETURNING id", (nombre,)
                )
                empleado_id = cur.fetchone()["id"]

                cur.execute(
                    "SELECT DISTINCT descripcion_visual FROM personas "
                    "WHERE COALESCE(cliente_id, id) = %s AND es_empleado = true "
                    "AND descripcion_visual IS NOT NULL",
                    (raiz,)
                )
                variantes = [json.loads(r["descripcion_visual"]) for r in cur.fetchall()]
                for desc in variantes:
                    cur.execute(
                        "INSERT INTO empleados_descripciones (empleado_id, descripcion) VALUES (%s, %s)",
                        (empleado_id, json.dumps(desc, ensure_ascii=False))
                    )
                total_desc += len(variantes)
                print(f"[DB] Empleado '{nombre}' (id={empleado_id}, ex-cliente_id={raiz}): "
                      f"{len(variantes)} variantes de descripcion cargadas.")

            self.conn.commit()
            cur.close()
            return {"empleados": len(raices), "descripciones": total_desc}
        return self._con_reconexion(_run, default={})

    def marcar_empleados_en_zona_caja(self, zona_ids: list) -> dict:
        """Correccion retroactiva ACOTADA a zonas puntuales (a diferencia de
        auditar_sesion(), que solo mira la zona DOMINANTE de la sesion
        completa): para toda 'persona' con al menos un punto de trayectoria
        en alguna de 'zona_ids' y es_empleado = false, intenta matchear su
        descripcion_visual contra los empleados conocidos -- misma fuente
        combinada que auditar_sesion() paso 2 (apariciones ya confirmadas en
        'personas' + variantes de empleados_descripciones) y mismo criterio
        de match (_obligatorios_coinciden). Si matchea contra una cadena real
        ya conocida, se fusiona (cliente_id); si matchea solo contra la tabla
        de referencia, se marca sola (es_empleado=true, empleado_id) sin
        fusionar. NO toca a quienes no matchean (a diferencia de
        auditar_sesion(), que les saca la zona -- ver llamador para esa
        limpieza aparte si hace falta). NO actualiza 'trayectorias.es_empleado'
        -- correr sincronizar_es_empleado_trayectorias() despues. Devuelve
        {'evaluados', 'marcados', 'sin_descripcion'}."""
        if not self.conn:
            return {}

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT DISTINCT p.id, p.cliente_id, p.descripcion_visual "
                "FROM trayectorias t JOIN personas p ON p.id = t.persona_id "
                "WHERE t.zona_id = ANY(%s) AND t.es_empleado = false",
                (zona_ids,)
            )
            sospechosos = cur.fetchall()
            if not sospechosos:
                cur.close()
                return {"evaluados": 0, "marcados": 0, "sin_descripcion": 0}

            cur.execute(
                "SELECT DISTINCT ON (cliente_id) cliente_id, descripcion_visual, empleado_id "
                "FROM personas WHERE es_empleado = true AND descripcion_visual IS NOT NULL "
                "ORDER BY cliente_id, empleado_id NULLS LAST"
            )
            empleados_conocidos = [
                {"cliente_id": r["cliente_id"], "empleado_id": r["empleado_id"],
                 "descripcion": json.loads(r["descripcion_visual"])}
                for r in cur.fetchall()
            ]
            cur.execute(
                "SELECT ed.empleado_id, ed.descripcion "
                "FROM empleados_descripciones ed JOIN empleados e ON e.id = ed.empleado_id "
                "WHERE e.activo = true"
            )
            empleados_conocidos += [
                {"cliente_id": None, "empleado_id": r["empleado_id"], "descripcion": r["descripcion"]}
                for r in cur.fetchall()
            ]

            marcados, sin_descripcion = 0, 0
            for s in sospechosos:
                if not s["descripcion_visual"]:
                    sin_descripcion += 1
                    continue
                desc = json.loads(s["descripcion_visual"])
                match = next(
                    (c for c in empleados_conocidos if _obligatorios_coinciden(desc, c["descripcion"], estricto=True)),
                    None
                )
                if match is None:
                    continue
                if match["cliente_id"] is not None:
                    cur.execute(
                        "UPDATE personas SET cliente_id = %s, es_empleado = true, "
                        "empleado_id = COALESCE(%s, empleado_id) WHERE id = %s",
                        (match["cliente_id"], match["empleado_id"], s["id"])
                    )
                else:
                    cur.execute(
                        "UPDATE personas SET es_empleado = true, empleado_id = %s WHERE id = %s",
                        (match["empleado_id"], s["id"])
                    )
                marcados += 1

            self.conn.commit()
            cur.close()
            print(f"[DB] Zonas {zona_ids}: {marcados}/{len(sospechosos)} marcadas como empleado "
                  f"({sin_descripcion} sin descripcion_visual, no evaluables).")
            return {"evaluados": len(sospechosos), "marcados": marcados, "sin_descripcion": sin_descripcion}
        return self._con_reconexion(_run, default={})

    def consolidar_cadenas_empleados(self, raiz_por_empleado: dict) -> dict:
        """Solo puede haber tantos EMPLEADOS REALES como filas en 'empleados'
        (hoy 3) -- una aparicion marcada es_empleado=true que matcheo solo
        contra la tabla de referencia (ver marcar_empleados_en_zona_caja)
        queda, sin este paso, como la raiz de su PROPIA cadena en vez de
        fusionarse con el empleado real al que corresponde; eso infla el
        numero de "empleados" distintos muy por encima de los que existen en
        la realidad. 'raiz_por_empleado' mapea empleado_id -> persona_id
        CANONICO de esa cadena (ej. {1: 81, 2: 109, 3: 114}). Dos pasadas:
        1) toda fila con empleado_id ya asignado se reapunta (cliente_id) a
        la raiz canonica de ESE empleado, sin importar donde apuntaba antes;
        2) toda fila es_empleado=true SIN empleado_id pero cuya cadena YA es
        una de las raices canonicas (fusionada por el otro camino de match,
        contra una aparicion real) se le completa el empleado_id, para que
        quede identificada igual. Devuelve {'reapuntadas', 'empleado_id_completado'}."""
        if not self.conn:
            return {}

        def _run():
            cur = self.conn.cursor()
            reapuntadas = 0
            for empleado_id, raiz in raiz_por_empleado.items():
                cur.execute(
                    "UPDATE personas SET cliente_id = %s "
                    "WHERE es_empleado = true AND empleado_id = %s AND COALESCE(cliente_id, id) != %s",
                    (raiz, empleado_id, raiz)
                )
                reapuntadas += cur.rowcount

            completadas = 0
            for empleado_id, raiz in raiz_por_empleado.items():
                cur.execute(
                    "UPDATE personas SET empleado_id = %s "
                    "WHERE es_empleado = true AND empleado_id IS NULL AND COALESCE(cliente_id, id) = %s",
                    (empleado_id, raiz)
                )
                completadas += cur.rowcount

            self.conn.commit()
            cur.close()
            print(f"[DB] Consolidacion de cadenas de empleados: {reapuntadas} reapuntadas a su raiz "
                  f"canonica, {completadas} con empleado_id completado.")
            return {"reapuntadas": reapuntadas, "empleado_id_completado": completadas}
        return self._con_reconexion(_run, default={})

    def forzar_empleado_zona_caja(self, zona_ids: Optional[list] = None, sesion_id: Optional[int] = None) -> dict:
        """Regla de negocio MAS FUERTE que marcar_empleados_en_zona_caja():
        Zona Caja es fisicamente espacio EXCLUSIVO de empleados (detras del
        mostrador) -- quien sea que tenga un punto de trayectoria ahi es
        empleado SI O SI, sin condicionarlo a que su descripcion matchee
        contra algo ya conocido (a diferencia de auditar_sesion()/
        marcar_empleados_en_zona_caja(), que si no matchea le sacan la zona
        en vez de marcarlo). La cadena canonica de cada empleado_id se deriva
        de 'personas' (la raiz mas antigua ya tagueada con ese empleado_id),
        no de una lista hardcodeada -- asi que TODA aparicion termina
        fusionada (cliente_id) a la cadena real de alguno de los empleados
        conocidos:
        1) si su descripcion matchea (_obligatorios_coinciden) contra un
           empleado ya conocido (apariciones confirmadas + variantes de
           empleados_descripciones), se fusiona con ESE.
        2) si no matchea pero tiene descripcion, se atribuye al empleado con
           mas campos coincidentes (_comparar_descriptores, el mejor puntaje
           entre las cadenas conocidas) -- interpretacion: es el MISMO
           empleado descrito distinto por luz/angulo, no una persona nueva --
           y esa descripcion se guarda como variante NUEVA en
           empleados_descripciones para que la proxima vez matchee directo.
        3) si no tiene descripcion_visual (no se puede comparar nada), se le
           atribuye al empleado de id mas bajo (no hay forma de elegir mejor).
        Si un empleado_id todavia no tiene ninguna cadena real conocida (caso
        raro: recien sembrada la tabla de referencia, nunca se aplico esto
        antes), la primera aparicion que le toque queda como raiz de su
        propia cadena -- las siguientes ya se fusionan contra ella.
        'zona_ids', si no viene, se resuelve solo a todas las zonas con
        tipo='caja' (la regla es sobre el TIPO de zona, no sobre ids
        particulares -- asi sigue funcionando aunque se editen/agreguen
        zonas despues). 'sesion_id', si viene, acota el trabajo a esa sesion
        (uso en vivo, justo despues de auditar_sesion en main.py); sin el,
        corre sobre TODA la BD (uso de correccion retroactiva). Devuelve
        {'fusionadas_por_match', 'fusionadas_por_similitud', 'sin_descripcion',
        'total'}."""
        if not self.conn:
            return {}

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            zids = zona_ids
            if zids is None:
                cur.execute("SELECT id FROM zonas WHERE tipo = 'caja'")
                zids = [r["id"] for r in cur.fetchall()]
                if not zids:
                    cur.close()
                    return {"fusionadas_por_match": 0, "fusionadas_por_similitud": 0,
                            "sin_descripcion": 0, "total": 0}

            cur.execute(
                "SELECT empleado_id, MIN(COALESCE(cliente_id, id)) AS raiz "
                "FROM personas WHERE empleado_id IS NOT NULL GROUP BY empleado_id"
            )
            raiz_por_empleado = {r["empleado_id"]: r["raiz"] for r in cur.fetchall()}

            filtro_sesion = "AND p.sesion_id = %s" if sesion_id is not None else ""
            params = (zids, sesion_id) if sesion_id is not None else (zids,)
            cur.execute(
                "SELECT DISTINCT p.id, p.descripcion_visual "
                "FROM trayectorias t JOIN personas p ON p.id = t.persona_id "
                f"WHERE t.zona_id = ANY(%s) {filtro_sesion} "
                "AND NOT (p.es_empleado AND p.empleado_id IS NOT NULL "
                "AND p.cliente_id = ANY(%s))",
                params + (list(raiz_por_empleado.values()) or [-1],)
            )
            pendientes = cur.fetchall()
            if not pendientes:
                cur.close()
                return {"fusionadas_por_match": 0, "fusionadas_por_similitud": 0,
                        "sin_descripcion": 0, "total": 0}

            cur.execute(
                "SELECT DISTINCT ON (cliente_id) cliente_id, descripcion_visual, empleado_id "
                "FROM personas WHERE es_empleado = true AND descripcion_visual IS NOT NULL "
                "ORDER BY cliente_id, empleado_id NULLS LAST"
            )
            conocidos = [
                {"empleado_id": r["empleado_id"], "descripcion": json.loads(r["descripcion_visual"])}
                for r in cur.fetchall() if r["empleado_id"] is not None
            ]
            cur.execute(
                "SELECT ed.empleado_id, ed.descripcion "
                "FROM empleados_descripciones ed JOIN empleados e ON e.id = ed.empleado_id "
                "WHERE e.activo = true"
            )
            variantes_por_empleado = defaultdict(list)
            for r in cur.fetchall():
                variantes_por_empleado[r["empleado_id"]].append(r["descripcion"])
            for c in conocidos:
                variantes_por_empleado[c["empleado_id"]].append(c["descripcion"])

            ids_conocidos = set(raiz_por_empleado) | set(variantes_por_empleado)
            if not ids_conocidos:
                cur.close()
                print("[DB] forzar_empleado_zona_caja: no hay ningun 'empleado' definido todavia -- se omite.")
                return {"fusionadas_por_match": 0, "fusionadas_por_similitud": 0,
                        "sin_descripcion": 0, "total": 0}
            empleado_default = min(ids_conocidos)
            por_match = por_similitud = sin_desc = 0

            for s in pendientes:
                desc = json.loads(s["descripcion_visual"]) if s["descripcion_visual"] else None

                if desc is None:
                    empleado_id = empleado_default
                    sin_desc += 1
                else:
                    match = next(
                        (c["empleado_id"] for c in conocidos
                         if _obligatorios_coinciden(desc, c["descripcion"], estricto=True)),
                        None
                    )
                    if match is not None:
                        empleado_id = match
                        por_match += 1
                    else:
                        mejor_empleado, mejor_score = None, -1
                        for eid, variantes in variantes_por_empleado.items():
                            for variante in variantes:
                                coincidencias, comparables = _comparar_descriptores(desc, variante)
                                if comparables > 0 and coincidencias > mejor_score:
                                    mejor_score, mejor_empleado = coincidencias, eid
                        empleado_id = mejor_empleado if mejor_empleado is not None else empleado_default
                        cur.execute(
                            "INSERT INTO empleados_descripciones (empleado_id, descripcion) VALUES (%s, %s)",
                            (empleado_id, json.dumps(desc, ensure_ascii=False))
                        )
                        variantes_por_empleado[empleado_id].append(desc)
                        por_similitud += 1

                # Si el empleado matcheado todavia no tiene una cadena real
                # conocida (recien sembrada la tabla de referencia), esta
                # aparicion queda como raiz de su propia cadena -- la
                # siguiente que matchee el mismo empleado_id ya se fusiona
                # contra ella (raiz_por_empleado se recalcula en cada corrida).
                raiz = raiz_por_empleado.get(empleado_id, s["id"])
                cur.execute(
                    "UPDATE personas SET es_empleado = true, empleado_id = %s, cliente_id = %s WHERE id = %s",
                    (empleado_id, raiz, s["id"])
                )

            self.conn.commit()
            cur.close()
            resumen = {"fusionadas_por_match": por_match, "fusionadas_por_similitud": por_similitud,
                       "sin_descripcion": sin_desc, "total": len(pendientes)}
            print(f"[DB] Zona Caja forzada a empleado en {zids}: {resumen}")
            return resumen
        return self._con_reconexion(_run, default={})

    def reclasificar_por_mayoria_zona(self, sesion_id: Optional[int] = None) -> dict:
        """Sucesor de forzar_empleado_zona_caja(): esa regla marcaba empleado
        a CUALQUIERA con un solo punto en Zona Caja, lo que terminaba
        fusionando clientes reales que solo pasaron a pagar (mayoria de su
        trayectoria en Salon/Gondola, con 1-2 puntos sueltos en Caja) --
        contaminando las cadenas de empleado. Esta version decide por la
        MAYORIA de puntos de cada 'persona' (no por presencia puntual) y
        ademas BORRA los puntos minoritarios que contradicen esa mayoria (en
        vez de solo re-etiquetar):
        - mayoria de puntos en zona tipo='caja' -> es EMPLEADO (se fusiona
          con el conocido mas parecido, misma logica de match/similitud que
          forzar_empleado_zona_caja) y se borran sus puntos que NO son de
          tipo 'caja' (ruido: cruzo el salon de paso, quedo mal clasificado).
        - mayoria de puntos en zona tipo IN ('gondola','otro') -> es CLIENTE
          (si estaba marcado empleado por error, se revierte: es_empleado,
          empleado_id y cliente_id vuelven a su estado propio) y se borran
          sus puntos que SI son de tipo 'caja' (paso a pagar, no lo convierte
          en empleado).
        Empate exacto (misma cantidad de puntos en cada lado) se resuelve
        como CLIENTE -- hace falta evidencia clara para afirmar que alguien
        es empleado, no al reves. Los puntos con zona_id NULL no cuentan para
        la mayoria ni se tocan (no hay evidencia que contradigan).
        'sesion_id', si viene, acota el trabajo a esa sesion (uso en vivo,
        reemplaza a forzar_empleado_zona_caja en main.py); sin el, corre
        sobre TODA la BD. Devuelve {'a_empleado', 'a_cliente', 'puntos_borrados'}
        ('a_empleado'/'a_cliente' cuentan CUALQUIER persona de cada mayoria,
        haya cambiado de estado o ya estuviera bien)."""
        if not self.conn:
            return {}

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            filtro_sesion = "AND p.sesion_id = %s" if sesion_id is not None else ""
            params = (sesion_id,) if sesion_id is not None else ()
            cur.execute(
                "SELECT p.id AS persona_id, p.es_empleado, p.descripcion_visual, "
                "  count(*) FILTER (WHERE z.tipo = 'caja') AS n_caja, "
                "  count(*) FILTER (WHERE z.tipo IN ('gondola','otro')) AS n_no_caja "
                "FROM personas p "
                "JOIN trayectorias t ON t.persona_id = p.id "
                "LEFT JOIN zonas z ON z.id = t.zona_id "
                f"WHERE true {filtro_sesion} "
                "GROUP BY p.id "
                "HAVING count(*) FILTER (WHERE z.tipo = 'caja') > 0 "
                "    OR count(*) FILTER (WHERE z.tipo IN ('gondola','otro')) > 0",
                params
            )
            candidatos = cur.fetchall()
            if not candidatos:
                cur.close()
                return {"a_empleado": 0, "a_cliente": 0, "puntos_borrados": 0}

            cur.execute(
                "SELECT empleado_id, MIN(COALESCE(cliente_id, id)) AS raiz "
                "FROM personas WHERE empleado_id IS NOT NULL GROUP BY empleado_id"
            )
            raiz_por_empleado = {r["empleado_id"]: r["raiz"] for r in cur.fetchall()}

            cur.execute(
                "SELECT DISTINCT ON (cliente_id) cliente_id, descripcion_visual, empleado_id "
                "FROM personas WHERE es_empleado = true AND descripcion_visual IS NOT NULL "
                "ORDER BY cliente_id, empleado_id NULLS LAST"
            )
            conocidos = [
                {"empleado_id": r["empleado_id"], "descripcion": json.loads(r["descripcion_visual"])}
                for r in cur.fetchall() if r["empleado_id"] is not None
            ]
            cur.execute(
                "SELECT ed.empleado_id, ed.descripcion "
                "FROM empleados_descripciones ed JOIN empleados e ON e.id = ed.empleado_id "
                "WHERE e.activo = true"
            )
            variantes_por_empleado = defaultdict(list)
            for r in cur.fetchall():
                variantes_por_empleado[r["empleado_id"]].append(r["descripcion"])
            for c in conocidos:
                variantes_por_empleado[c["empleado_id"]].append(c["descripcion"])

            ids_conocidos = set(raiz_por_empleado) | set(variantes_por_empleado)
            empleado_default = min(ids_conocidos) if ids_conocidos else None

            a_empleado = a_cliente = puntos_borrados = 0
            for c in candidatos:
                mayoria_caja = c["n_caja"] > c["n_no_caja"]  # empate -> False (cliente)

                if mayoria_caja:
                    if empleado_default is None:
                        continue  # no hay ningun 'empleado' definido todavia
                    desc = json.loads(c["descripcion_visual"]) if c["descripcion_visual"] else None
                    empleado_id = None
                    if desc is not None:
                        empleado_id = next(
                            (k["empleado_id"] for k in conocidos
                             if _obligatorios_coinciden(desc, k["descripcion"], estricto=True)),
                            None
                        )
                        if empleado_id is None:
                            mejor_empleado, mejor_score = None, -1
                            for eid, variantes in variantes_por_empleado.items():
                                for variante in variantes:
                                    coincidencias, comparables = _comparar_descriptores(desc, variante)
                                    if comparables > 0 and coincidencias > mejor_score:
                                        mejor_score, mejor_empleado = coincidencias, eid
                            empleado_id = mejor_empleado
                    if empleado_id is None:
                        empleado_id = empleado_default
                    raiz = raiz_por_empleado.get(empleado_id, c["persona_id"])
                    cur.execute(
                        "UPDATE personas SET es_empleado = true, empleado_id = %s, cliente_id = %s WHERE id = %s",
                        (empleado_id, raiz, c["persona_id"])
                    )
                    cur.execute(
                        "DELETE FROM trayectorias t USING zonas z "
                        "WHERE t.zona_id = z.id AND t.persona_id = %s AND z.tipo != 'caja'",
                        (c["persona_id"],)
                    )
                    puntos_borrados += cur.rowcount
                    a_empleado += 1
                else:
                    if c["es_empleado"]:
                        cur.execute(
                            "UPDATE personas SET es_empleado = false, empleado_id = NULL, cliente_id = %s "
                            "WHERE id = %s",
                            (c["persona_id"], c["persona_id"])
                        )
                    cur.execute(
                        "DELETE FROM trayectorias t USING zonas z "
                        "WHERE t.zona_id = z.id AND t.persona_id = %s AND z.tipo = 'caja'",
                        (c["persona_id"],)
                    )
                    puntos_borrados += cur.rowcount
                    a_cliente += 1

            self.conn.commit()
            cur.close()
            resumen = {"a_empleado": a_empleado, "a_cliente": a_cliente, "puntos_borrados": puntos_borrados}
            print(f"[DB] Reclasificacion por mayoria de zona: {resumen}")
            return resumen
        return self._con_reconexion(_run, default={})

    def recalcular_zonas_por_pie(self) -> dict:
        """Recalcula 'trayectorias.centroide_x/y' y 'zona_id' de TODA la BD
        usando la BASE del bounding box guardado (bbox_x1, bbox_x2, bbox_y2)
        en vez del centro geometrico -- ver el comentario en
        PersonTracker.procesar_frame() (tracking.py) sobre por que el centro
        del box (altura del pecho) no representa bien la posicion real en el
        piso desde una camara elevada en angulo, y puede hacer que alguien
        parado del lado del cliente caiga (en la imagen) adentro del
        poligono de Zona Caja. Corrige datos ya guardados con ese sesgo
        (videos analizados antes de este fix); los nuevos ya se guardan bien
        desde el pipeline. Agrupa por camara para usar el set de zonas
        correcto de cada una. Devuelve {camara_id: filas_actualizadas}."""
        if not self.conn:
            return {}

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT DISTINCT camara_id FROM sesiones_video ORDER BY camara_id")
            camaras = [r["camara_id"] for r in cur.fetchall()]
            resumen = {}
            for camara_id in camaras:
                cur.execute(
                    "SELECT id, poligono FROM zonas WHERE camara_id = %s",
                    (camara_id,)
                )
                zonas = [{"id": r["id"], "poligono": r["poligono"]} for r in cur.fetchall()]

                cur.execute(
                    "SELECT t.id, t.bbox_x1, t.bbox_x2, t.bbox_y2 "
                    "FROM trayectorias t "
                    "JOIN personas p ON p.id = t.persona_id "
                    "JOIN sesiones_video sv ON sv.id = p.sesion_id "
                    "WHERE sv.camara_id = %s AND t.bbox_x1 IS NOT NULL AND t.bbox_y2 IS NOT NULL",
                    (camara_id,)
                )
                filas = cur.fetchall()
                cambios = [
                    (f["id"], round((f["bbox_x1"] + f["bbox_x2"]) / 2, 2), round(f["bbox_y2"], 2),
                     get_zona_id((f["bbox_x1"] + f["bbox_x2"]) / 2, f["bbox_y2"], zonas))
                    for f in filas
                ]
                if cambios:
                    # Casts explicitos: Postgres a veces infiere el tipo de
                    # la columna 'zona' de VALUES como text (ej. si en ese
                    # batch particular hay muchos NULL), y despues rechaza
                    # asignarla a la columna INT real -- sin el cast, esto
                    # fallaba de forma intermitente segun que filas cayeran
                    # en cada batch.
                    psycopg2.extras.execute_values(
                        cur,
                        "UPDATE trayectorias AS t SET "
                        "centroide_x = v.cx::float, centroide_y = v.cy::float, zona_id = v.zona::int "
                        "FROM (VALUES %s) AS v(id, cx, cy, zona) "
                        "WHERE t.id = v.id::bigint",
                        cambios, template="(%s, %s, %s, %s)"
                    )
                    self.conn.commit()
                resumen[camara_id] = len(cambios)
            cur.close()
            print(f"[DB] Recalculo de zonas por base del box: {resumen}")
            return resumen
        return self._con_reconexion(_run, default={})

    def recalcular_zona_dominante_personas(self) -> int:
        """Recalcula 'personas.zona_id' (la zona dominante -- la mas
        frecuente entre los puntos de trayectoria de cada persona) para TODA
        la BD, no solo la sesion recien analizada como hace el paso 1 de
        auditar_sesion(). Hace falta correrlo despues de
        recalcular_zonas_por_pie(), que puede cambiar el zona_id de muchos
        puntos y dejar desactualizada la zona dominante ya guardada.
        Devuelve cuantas personas se actualizaron."""
        if not self.conn:
            return 0

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT t.persona_id AS persona_id, t.zona_id AS zona_id, count(*) AS n "
                "FROM trayectorias t WHERE t.zona_id IS NOT NULL "
                "GROUP BY t.persona_id, t.zona_id"
            )
            conteos = {}
            for r in cur.fetchall():
                conteos.setdefault(r["persona_id"], []).append((r["zona_id"], r["n"]))
            cambios = [(pid, max(pares, key=lambda x: x[1])[0]) for pid, pares in conteos.items()]
            if cambios:
                psycopg2.extras.execute_values(
                    cur,
                    "UPDATE personas AS p SET zona_id = v.zona::int "
                    "FROM (VALUES %s) AS v(id, zona) WHERE p.id = v.id::int",
                    cambios, template="(%s, %s)"
                )
                self.conn.commit()
            cur.close()
            print(f"[DB] Zona dominante recalculada para {len(cambios)} personas.")
            return len(cambios)
        return self._con_reconexion(_run, default=0)

    def _empleado_conocido_que_matchea(self, cur, descripcion: Optional[dict]) -> Optional[int]:
        """Compara 'descripcion' contra los empleados YA CONFIRMADOS
        (es_empleado = true) en la BD -- reemplaza la vieja heuristica de
        'color de uniforme + gorra' (es_uniforme_empleado en utils.py), que
        resulto demasiado floja: cualquier cliente con remera gris/verde/
        naranja y gorra (colores y accesorio comunisimos) terminaba marcado
        como personal, inflando la cantidad de 'empleados' muy por encima de
        los 2-3 reales del local (ver historial de limpieza manual). Ahora
        solo se marca es_empleado cuando la descripcion coincide (color de
        ropa obligatorio, ver _obligatorios_coinciden) con alguien que YA
        esta confirmado como empleado -- nunca se crea un empleado nuevo por
        heuristica sola. Devuelve el cliente_id del empleado que matchea, o
        None."""
        if not descripcion:
            return None
        cur.execute(
            "SELECT DISTINCT ON (cliente_id) cliente_id, descripcion_visual "
            "FROM personas WHERE es_empleado = true AND descripcion_visual IS NOT NULL "
            "ORDER BY cliente_id"
        )
        for cliente_id, descripcion_emp_json in cur.fetchall():
            try:
                descripcion_emp = json.loads(descripcion_emp_json)
            except (TypeError, ValueError):
                continue
            if _obligatorios_coinciden(descripcion, descripcion_emp, estricto=True):
                return cliente_id
        return None

    def guardar_descripcion_persona(self, sesion_id, sid: int, frame_num: int, fps: float,
                                      inicio: datetime, metodo_reid: str, descripcion: dict,
                                      cliente_id_hint: Optional[int] = None) -> Optional[int]:
        """Guarda (o actualiza) la fila de 'personas' apenas Gemini genera la
        descripcion visual de este cliente, sin esperar a que termine el
        analisis del video completo -- si el proceso se corta a mitad de
        camino, lo ya descrito no se pierde. 'cliente_id_hint', si viene, es
        el id de 'personas' de una sesion distinta (mismo dia) con la que
        Gemini reidentifico a esta persona. Si 'cliente_id_hint' YA es un
        empleado confirmado, esta fila hereda el flag -- NO se decide
        'es_empleado' comparando la descripcion de esta aparicion puntual
        contra la de los empleados conocidos (eso se probo fragil: una sola
        coincidencia de color entre docenas de apariciones de un mismo
        cliente_id contamina la cadena entera para siempre, y esa cadena mal
        marcada despues sirve de referencia para contaminar a otros -- ver
        historial). Ese chequeo mas laxo, acotado a Zona Caja, queda solo en
        auditar_sesion()."""
        def _run():
            if not self.conn or not sesion_id:
                return None
            ts = frame_to_dt(frame_num, fps, inicio)
            descripcion_json = json.dumps(descripcion, ensure_ascii=False) if descripcion else None
            cur = self.conn.cursor()
            if sid in self.persona_db_ids:
                db_id = self.persona_db_ids[sid]
                cur.execute(
                    "UPDATE personas SET ultima_deteccion = %s, metodo_reid = %s, descripcion_visual = %s "
                    "WHERE id = %s",
                    (ts, metodo_reid, descripcion_json, db_id)
                )
            else:
                cur.execute(
                    "INSERT INTO personas "
                    "(sesion_id, primera_deteccion, ultima_deteccion, metodo_reid, descripcion_visual) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (sesion_id, ts, ts, metodo_reid, descripcion_json)
                )
                db_id = cur.fetchone()[0]
                self.persona_db_ids[sid] = db_id
                cliente_id = cliente_id_hint if cliente_id_hint is not None else db_id
                cur.execute("UPDATE personas SET cliente_id = %s WHERE id = %s", (cliente_id, db_id))
            if cliente_id_hint is not None:
                cur.execute("SELECT es_empleado FROM personas WHERE id = %s", (cliente_id_hint,))
                row = cur.fetchone()
                if row and row[0]:
                    cur.execute("UPDATE personas SET es_empleado = TRUE WHERE id = %s", (db_id,))
            self.conn.commit()
            cur.close()
            extra = f" (mismo cliente que persona_id={cliente_id_hint})" if cliente_id_hint else ""
            print(f"[DB] Descripcion guardada durante el analisis -> persona_id={db_id}{extra}")
            return db_id
        return self._con_reconexion(_run, default=None)

    def candidatos_reid_del_dia(self, momento: datetime, camara_id: int, excluir_ids: set) -> list:
        """Personas con descripcion visual ya guardada, candidatas para que
        Gemini/Groq reidentifique a un cliente nuevo. Restringido a:
        - camaras del MISMO GRUPO fisico que 'camara_id' (self.grupos_camara)
          -- nunca se compara contra una camara que mira un espacio distinto,
          aunque sea el mismo dia (ej. la camara de la esquina no debe
          aportar candidatos para la zona de cajas).
        - una ventana de +/- self.reid_ventana_horas alrededor de 'momento'
          (el instante actual del video, no el inicio) -- no tiene sentido
          comparar a alguien visto a las 9am con alguien visto a las 5pm solo
          porque es el mismo dia calendario.
        Es la unica fuente de candidatos que usa Gemini para reidentificar --
        nunca su propia memoria en RAM -- para poder reconocer al mismo
        cliente tanto dentro del mismo video como entre videos distintos
        (misma camara u otra del mismo grupo)."""
        def _run():
            if not self.conn:
                return []
            camaras_grupo = self.grupos_camara.get(camara_id, [camara_id])
            ventana = timedelta(hours=self.reid_ventana_horas)
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT p.id, p.descripcion_visual, p.primera_deteccion, COALESCE(p.cliente_id, p.id) AS cliente_id "
                "FROM personas p "
                "JOIN sesiones_video sv ON sv.id = p.sesion_id "
                "WHERE p.descripcion_visual IS NOT NULL "
                "AND sv.camara_id = ANY(%s) "
                "AND p.primera_deteccion BETWEEN %s AND %s "
                "ORDER BY p.primera_deteccion DESC",
                (camaras_grupo, momento - ventana, momento + ventana)
            )
            rows = cur.fetchall()
            cur.close()
            candidatos = []
            for r in rows:
                if r["id"] in excluir_ids:
                    continue
                try:
                    desc = json.loads(r["descripcion_visual"])
                except (TypeError, ValueError):
                    continue
                if desc:
                    candidatos.append({
                        "persona_id": r["id"], "cliente_id": r["cliente_id"], "descripcion": desc,
                        "primera_deteccion": r["primera_deteccion"],
                    })
            return candidatos
        return self._con_reconexion(_run, default=[])

    def guardar_personas(self, sesion_id, rows: list, traj_buffer: list, fps: float, inicio: datetime,
                          camara_id: Optional[int] = None) -> None:
        """Sincronizacion final al cerrar el video: actualiza ultima_deteccion
        y metodo_reid definitivos de cada persona (la fila ya deberia existir
        gracias a crear_persona()/guardar_descripcion_persona() durante el
        analisis) e inserta lo que haya quedado en traj_buffer desde el ultimo
        guardar_trayectorias_parcial() periodico."""
        def _run():
            if not self.conn or not sesion_id:
                return
            cur = self.conn.cursor()
            ya_creadas = 0
            for r in rows:
                sid   = r["id"]
                p_fin = frame_to_dt(r["_last_frame"], fps, inicio)

                if sid in self.persona_db_ids:
                    db_id = self.persona_db_ids[sid]
                    cur.execute(
                        "UPDATE personas SET ultima_deteccion = %s, metodo_reid = %s WHERE id = %s",
                        (p_fin, r.get("metodo_reid"), db_id)
                    )
                    ya_creadas += 1
                else:
                    # Red de seguridad: este sid nunca paso por crear_persona()
                    # (ej. la BD estuvo caida justo al resolverlo). Se inserta
                    # recien aca para no perder a esa persona.
                    p_ini = frame_to_dt(r["_first_frame"], fps, inicio)
                    descripcion = r.get("descripcion")
                    descripcion_json = json.dumps(descripcion, ensure_ascii=False) if descripcion else None
                    cur.execute(
                        "INSERT INTO personas "
                        "(sesion_id, primera_deteccion, ultima_deteccion, metodo_reid, descripcion_visual) "
                        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                        (sesion_id, p_ini, p_fin, r.get("metodo_reid"), descripcion_json)
                    )
                    db_id = cur.fetchone()[0]
                    self.persona_db_ids[sid] = db_id
                    cliente_id_hint = r.get("cliente_id_hint")
                    cur.execute("UPDATE personas SET cliente_id = %s WHERE id = %s",
                                (cliente_id_hint if cliente_id_hint is not None else db_id, db_id))
                    if cliente_id_hint is not None:
                        cur.execute("SELECT es_empleado FROM personas WHERE id = %s", (cliente_id_hint,))
                        row = cur.fetchone()
                        if row and row[0]:
                            cur.execute("UPDATE personas SET es_empleado = TRUE WHERE id = %s", (db_id,))
            self.conn.commit()
            cur.close()
            print(f"[DB] {len(rows)} personas sincronizadas "
                  f"({ya_creadas} ya se habian creado durante el analisis).")
        self._con_reconexion(_run, default=None)

        if self.guardar_trayectorias and traj_buffer:
            self.guardar_trayectorias_parcial(traj_buffer, fps, inicio, camara_id)

    def guardar_heatmap(self, camara_id, sesion_id, inicio_dt, fin_dt, stats: dict,
                         imagen_path: str, total_detecciones: int, frames_procesados: int) -> Optional[int]:
        def _run():
            if not self.conn:
                return None
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO mapas_calor
                    (camara_id, sesion_id, periodo_inicio, periodo_fin, granularidad,
                     matriz, resolucion_x, resolucion_y, imagen_path,
                     punto_max_x, punto_max_y, valor_maximo,
                     area_activa_pct, concentracion, zona_id_mas_caliente,
                     total_detecciones, frames_procesados)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (camara_id, periodo_inicio, granularidad) DO UPDATE SET
                    sesion_id             = EXCLUDED.sesion_id,
                    periodo_fin           = EXCLUDED.periodo_fin,
                    matriz                = EXCLUDED.matriz,
                    imagen_path           = EXCLUDED.imagen_path,
                    punto_max_x           = EXCLUDED.punto_max_x,
                    punto_max_y           = EXCLUDED.punto_max_y,
                    valor_maximo          = EXCLUDED.valor_maximo,
                    area_activa_pct       = EXCLUDED.area_activa_pct,
                    concentracion         = EXCLUDED.concentracion,
                    zona_id_mas_caliente  = EXCLUDED.zona_id_mas_caliente,
                    total_detecciones     = EXCLUDED.total_detecciones,
                    frames_procesados     = EXCLUDED.frames_procesados
                RETURNING id
            """, (
                camara_id, sesion_id, inicio_dt, fin_dt, "dia",
                stats["matriz_json"], stats["resolucion"], stats["resolucion"], imagen_path,
                stats["punto_max_x"], stats["punto_max_y"], stats["valor_maximo"],
                stats["area_activa_pct"], stats["concentracion"], stats["zona_id_mas_caliente"],
                total_detecciones, frames_procesados,
            ))
            heatmap_id = cur.fetchone()[0]
            self.conn.commit()
            cur.close()
            print(f"[DB] Heatmap guardado -> id={heatmap_id}  "
                  f"| punto_max=({stats['punto_max_x']},{stats['punto_max_y']})  "
                  f"| area_activa={stats['area_activa_pct']:.1f}%  "
                  f"| concentracion={stats['concentracion']:.2f}")
            return heatmap_id
        return self._con_reconexion(_run, default=None)

    def obtener_matrices_camara(self, camara_id: int) -> list:
        """Grillas + estadisticas de todas las sesiones de heatmap guardadas
        para una camara, usadas para combinarlas en un mapa acumulado."""
        def _run():
            if not self.conn:
                return []
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT matriz, valor_maximo, total_detecciones, frames_procesados, resolucion_x "
                "FROM mapas_calor WHERE camara_id = %s ORDER BY periodo_inicio",
                (camara_id,)
            )
            rows = cur.fetchall()
            cur.close()
            return [dict(r) for r in rows]
        return self._con_reconexion(_run, default=[])

    def guardar_heatmap_camara(self, camara_id, stats: dict, imagen_path: str,
                                total_detecciones: int, frames_procesados: int,
                                sesiones_combinadas: int) -> Optional[int]:
        """Upsert del mapa de calor acumulado (todas las sesiones combinadas)
        de una camara en 'mapas_calor_camara'."""
        def _run():
            if not self.conn:
                return None
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO mapas_calor_camara
                    (camara_id, matriz, resolucion_x, resolucion_y, imagen_path,
                     punto_max_x, punto_max_y, valor_maximo, area_activa_pct,
                     concentracion, zona_id_mas_caliente, total_detecciones,
                     frames_procesados, sesiones_combinadas, actualizado_en)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
                ON CONFLICT (camara_id) DO UPDATE SET
                    matriz                = EXCLUDED.matriz,
                    resolucion_x          = EXCLUDED.resolucion_x,
                    resolucion_y          = EXCLUDED.resolucion_y,
                    imagen_path           = EXCLUDED.imagen_path,
                    punto_max_x           = EXCLUDED.punto_max_x,
                    punto_max_y           = EXCLUDED.punto_max_y,
                    valor_maximo          = EXCLUDED.valor_maximo,
                    area_activa_pct       = EXCLUDED.area_activa_pct,
                    concentracion         = EXCLUDED.concentracion,
                    zona_id_mas_caliente  = EXCLUDED.zona_id_mas_caliente,
                    total_detecciones     = EXCLUDED.total_detecciones,
                    frames_procesados     = EXCLUDED.frames_procesados,
                    sesiones_combinadas   = EXCLUDED.sesiones_combinadas,
                    actualizado_en        = NOW()
                RETURNING camara_id
            """, (
                camara_id, stats["matriz_json"], stats["resolucion"], stats["resolucion"], imagen_path,
                stats["punto_max_x"], stats["punto_max_y"], stats["valor_maximo"],
                stats["area_activa_pct"], stats["concentracion"], stats["zona_id_mas_caliente"],
                total_detecciones, frames_procesados, sesiones_combinadas,
            ))
            result = cur.fetchone()[0]
            self.conn.commit()
            cur.close()
            print(f"[DB] Heatmap combinado camara {camara_id} actualizado "
                  f"({sesiones_combinadas} sesiones, total_detecciones={total_detecciones}).")
            return result
        return self._con_reconexion(_run, default=None)

    def _fusionar_por_proximidad(self, cur, candidatos: list, umbral_seg: float,
                                  coincidencias_minimas: int = 3) -> int:
        """Recorre 'candidatos' (filas con id, cliente_id, primera_deteccion,
        descripcion_visual, camara_id -- YA ordenadas por primera_deteccion) y
        fusiona por cliente_id los que aparecen en camaras DISTINTAS a menos
        de 'umbral_seg' de diferencia, con color de ropa superior obligatorio
        (_obligatorios_coinciden) Y al menos 'coincidencias_minimas' campos
        coincidentes de los que sean comparables en ambos lados (escalado
        hacia abajo si hay menos campos comparables que ese minimo, mismo
        criterio que GeminiReID/GroqReID/ClaudeReID.clasificar()) -- misma
        persona vista desde dos angulos a la vez. Usado tanto por
        auditar_sesion() (acotado a una sesion) como por
        fusionar_cross_camara_dia() (todo un dia). Devuelve cuantas personas
        se fusionaron (nunca se borra nada, solo se reapunta cliente_id al
        canonico -- el minimo de cada grupo).

        OJO -- dos bugs reales detectados y corregidos en produccion (grupos
        de decenas de apariciones sin relacion visual entre si terminaron
        fusionadas):
        1) Antes se comparaba contra la descripcion de LA FILA que se
           estuviera visitando en ese momento (r/r2), no contra una
           descripcion fija por cliente_id -- un cliente_id con 2+ miembros
           (de una fusion de una pasada anterior) podia tener miembros con
           descripciones DISTINTAS entre si, y CUALQUIERA de ellos podia
           actuar de ancla con SU PROPIA descripcion. Ahora se ancla SIEMPRE
           contra la MISMA descripcion representativa por cliente_id (la
           primera vista en 'candidatos').
        2) El unico filtro visual era _obligatorios_coinciden (color
           superior) -- un solo campo de muy pocas categorias posibles (ej.
           'negro' es carisimo) hace que CASI CUALQUIER PAR dentro de la
           ventana pase el filtro, armando una cadena de "telefono
           descompuesto" a lo largo del dia aunque cada comparacion puntual
           sea correcta. Ahora TAMBIEN exige el minimo de coincidencias de
           _comparar_descriptores, igual que el resto del Re-ID.
        3) La ventana de tiempo se media contra 'r["primera_deteccion"]' --
           el timestamp de LA FILA que se estuviera visitando, no contra el
           origen real del grupo. Un cliente_id con 2+ miembros tiene un
           timestamp por fila (distintos entre si); si un miembro TARDIO se
           visita como ancla, su propia ventana de +/-umbral_seg arranca
           desde SU horario, no desde el del primer miembro -- eso deja que
           la ventana "camine" salto a salto y alcance horarios arbitrariamente
           lejanos del origen real del grupo (se detecto en produccion: un
           grupo llego a abarcar CASI UNA HORA de diferencia real, con una
           ventana nominal de apenas 90s). Ahora se ancla tambien el tiempo
           contra el PRIMER horario visto para ese cliente_id -- ningun
           miembro del grupo puede quedar mas lejos de 'umbral_seg' del
           origen real, sin importar cuantos saltos intermedios haya."""
        ventana = timedelta(seconds=umbral_seg)
        descripcion_por_cliente: dict = {}
        tiempo_por_cliente: dict = {}
        for r in candidatos:
            if r["cliente_id"] not in tiempo_por_cliente:
                tiempo_por_cliente[r["cliente_id"]] = r["primera_deteccion"]
            if r["descripcion_visual"] and r["cliente_id"] not in descripcion_por_cliente:
                descripcion_por_cliente[r["cliente_id"]] = json.loads(r["descripcion_visual"])

        usados = set()
        fusionadas = 0
        for i, r in enumerate(candidatos):
            if r["id"] in usados or not r["descripcion_visual"]:
                continue
            desc1 = descripcion_por_cliente[r["cliente_id"]]
            tiempo1 = tiempo_por_cliente[r["cliente_id"]]
            grupo_ids = {r["cliente_id"]}
            for j in range(i + 1, len(candidatos)):
                r2 = candidatos[j]
                if r2["primera_deteccion"] - r["primera_deteccion"] > ventana:
                    break
                if r2["id"] in usados or r2["camara_id"] == r["camara_id"] or not r2["descripcion_visual"]:
                    continue
                if r2["cliente_id"] in grupo_ids:
                    continue
                if abs(r2["primera_deteccion"] - tiempo1) > ventana:
                    continue
                desc2 = descripcion_por_cliente[r2["cliente_id"]]
                if not _obligatorios_coinciden(desc1, desc2):
                    continue
                coincidencias, comparables = _comparar_descriptores(desc1, desc2)
                if comparables == 0 or coincidencias < min(coincidencias_minimas, comparables):
                    continue
                grupo_ids.add(r2["cliente_id"])
                usados.add(r2["id"])
            if len(grupo_ids) > 1:
                canon = min(grupo_ids)
                resto = [c for c in grupo_ids if c != canon]
                cur.execute("UPDATE personas SET cliente_id = %s WHERE cliente_id = ANY(%s)", (canon, resto))
                fusionadas += len(resto)
            usados.add(r["id"])
        return fusionadas

    def fusionar_continuidad_sesiones(self, fecha, umbral_seg: float = 60.0,
                                       umbral_alta_confianza_seg: float = 15.0) -> int:
        """Fusiona personas divididas por el LIMITE entre dos videos
        CONSECUTIVOS de la MISMA camara -- los archivos del DVR se cortan
        cada ~1 hora sin coordinarse con quien esta en cuadro, y cada sesion
        corre su propio PersonTracker en memoria: alguien que sigue presente
        cuando termina un archivo queda 'perdido' en esa sesion y aparece
        como 'cliente nuevo' en la siguiente, sin que nada los compare entre
        si. Distinto de fusionar_cross_camara_dia(), que fusiona ENTRE
        camaras pero descarta a proposito los pares de la MISMA camara.
        Solo compara la ULTIMA persona vista antes de que termine una sesion
        contra la PRIMERA vista al arrancar la sesion siguiente de esa misma
        camara -- no cualquier par dentro del mismo video (eso ya lo resuelve
        el tracking en vivo). La decision de cada par (Re-ID temporal +
        visual: ventana de tiempo, color de ropa obligatorio, conteo de
        caracteristicas coincidentes, nivel de confianza Alta/Media) la toma
        _decidir_continuidad_temporal() -- ver ese docstring para las reglas
        completas. 'umbral_seg' es la ventana MAXIMA de hueco de tiempo total
        (ambos lados del corte sumados) para siquiera considerar dos personas
        como la misma; 'umbral_alta_confianza_seg' es el hueco por debajo del
        cual la coincidencia se marca 'Alta' en vez de 'Media' (practicamente
        el mismo instante, solo pudo pasar por el corte del archivo).
        'fecha' acota a las sesiones que TERMINAN ese dia (date o
        'YYYY-MM-DD'). Devuelve cuantas personas se fusionaron."""
        if not self.conn:
            return 0

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "WITH sesiones_ord AS ("
                "  SELECT id, camara_id, inicio, fin, "
                "         LEAD(id) OVER (PARTITION BY camara_id ORDER BY inicio) AS siguiente_id, "
                "         LEAD(inicio) OVER (PARTITION BY camara_id ORDER BY inicio) AS siguiente_inicio "
                "  FROM sesiones_video"
                ") "
                "SELECT p1.id AS id1, p1.cliente_id AS c1, p1.descripcion_visual AS d1, "
                "       p2.id AS id2, p2.cliente_id AS c2, p2.descripcion_visual AS d2, "
                "       (s.fin - p1.ultima_deteccion) + (p2.primera_deteccion - s.siguiente_inicio) AS brecha "
                "FROM sesiones_ord s "
                "JOIN personas p1 ON p1.sesion_id = s.id "
                "JOIN personas p2 ON p2.sesion_id = s.siguiente_id "
                "WHERE s.fin::date = %s "
                "AND p1.es_empleado = false AND p2.es_empleado = false "
                "AND p1.cliente_id <> p2.cliente_id "
                "AND p1.descripcion_visual IS NOT NULL AND p2.descripcion_visual IS NOT NULL "
                "AND (s.fin - p1.ultima_deteccion) < make_interval(secs => %s) "
                "AND (p2.primera_deteccion - s.siguiente_inicio) < make_interval(secs => %s) "
                "ORDER BY brecha",
                (fecha, umbral_seg, umbral_seg)
            )
            candidatos = cur.fetchall()
            usados = set()
            fusionadas = 0
            conteo_confianza = {"Alta": 0, "Media": 0}
            for r in candidatos:
                if r["id1"] in usados or r["id2"] in usados or r["c1"] == r["c2"]:
                    continue
                desc1, desc2 = json.loads(r["d1"]), json.loads(r["d2"])
                delta_seg = r["brecha"].total_seconds()
                decision = _decidir_continuidad_temporal(
                    desc1, desc2, delta_seg, umbral_seg, umbral_alta_confianza_seg
                )
                if not decision["es_coincidencia"]:
                    print(f"[DB] Continuidad personas {r['id1']}/{r['id2']}: {decision['justificacion']}")
                    continue
                canon = min(r["c1"], r["c2"])
                resto = max(r["c1"], r["c2"])
                cur.execute("UPDATE personas SET cliente_id = %s WHERE cliente_id = %s", (canon, resto))
                fusionadas += 1
                conteo_confianza[decision["confianza"]] += 1
                usados.add(r["id1"])
                usados.add(r["id2"])
                print(f"[DB] Continuidad personas {r['id1']}/{r['id2']} (confianza {decision['confianza']}): "
                      f"{decision['justificacion']}")
            self.conn.commit()
            cur.close()
            print(f"[DB] Fusion de continuidad entre sesiones ({fecha}): {fusionadas} personas fusionadas "
                  f"(confianza alta={conteo_confianza['Alta']}, media={conteo_confianza['Media']}).")
            return fusionadas
        return self._con_reconexion(_run, default=0)

    def fusionar_cross_camara_dia(self, fecha, umbral_mismo_momento_seg: float = 90.0,
                                   coincidencias_minimas: int = 3) -> dict:
        """Version retroactiva de la fusion cross-camara -- corre sobre UN DIA
        COMPLETO ya analizado (todas las sesiones ya cerradas), en vez de
        estar acotada a la ventana +/-3 minutos de una sola sesion como hace
        auditar_sesion() al vuelo. Hace falta porque cuando cada sesion se
        analiza por separado (una corrida de main.py por archivo de video),
        la sesion de la camara vecina puede no estar analizada todavia en ese
        momento -- esos pares quedan sin comparar. Aca, con el dia entero ya
        cargado en la BD, se puede comparar cualquier par de personas de
        camaras del mismo grupo fisico (self.grupos_camara) sin esa
        limitacion. 'fecha' es un date (o string 'YYYY-MM-DD'). Devuelve
        {grupo_camaras: personas_fusionadas}."""
        if not self.conn:
            return {}

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            resumen = {}
            grupos_unicos = {tuple(sorted(g)) for g in self.grupos_camara.values()}
            for grupo in grupos_unicos:
                cur.execute(
                    "SELECT p.id, p.cliente_id, p.primera_deteccion, p.descripcion_visual, sv.camara_id "
                    "FROM personas p JOIN sesiones_video sv ON sv.id = p.sesion_id "
                    "WHERE sv.camara_id = ANY(%s) AND p.es_empleado = false "
                    "AND p.primera_deteccion::date = %s "
                    "ORDER BY p.primera_deteccion",
                    (list(grupo), fecha)
                )
                candidatos = cur.fetchall()
                fusionadas = self._fusionar_por_proximidad(
                    cur, candidatos, umbral_mismo_momento_seg, coincidencias_minimas
                )
                self.conn.commit()
                resumen[grupo] = fusionadas
            cur.close()
            print(f"[DB] Fusion cross-camara retroactiva ({fecha}): {resumen}")
            return resumen
        return self._con_reconexion(_run, default={})

    def fusionar_dia_hasta_converger(self, fecha, umbral_continuidad_seg: float = 60.0,
                                      umbral_alta_confianza_seg: float = 15.0,
                                      umbral_cross_camara_seg: float = 90.0,
                                      coincidencias_minimas: int = 3,
                                      max_pasadas: int = 10) -> dict:
        """Corre fusionar_continuidad_sesiones() + fusionar_cross_camara_dia()
        repetidamente para 'fecha' hasta que una pasada completa no encuentre
        NINGUNA fusion nueva (o hasta 'max_pasadas', limite de seguridad).
        Hace falta repetir porque cada pasada lee un snapshot de 'personas'
        ANTES de aplicar sus propios UPDATE -- una cadena de 3+ sesiones
        consecutivas de la misma camara (una persona que sigue en cuadro a
        traves de dos cortes de archivo seguidos) no siempre se resuelve
        entera en una sola pasada. Pensada para llamarse SOLA, automatica,
        justo despues de cerrar_sesion() en cada corrida de main.py -- asi
        cada video que termina de analizarse deja el dia consistente sin
        depender de correr deteccion/mantenimiento/fusionar_dia.py a mano.

        OJO -- dos bugs reales de sobre-fusion detectados y corregidos en
        produccion (grupos de decenas de apariciones sin relacion visual
        entre si terminaron fusionadas, algunas separadas por MAS TIEMPO del
        que la ventana permitiria en una sola comparacion):
        1) Hubo una tercera fusion aca ('mismo dia, por descriptor, cualquier
           camara, ventana de 30 min') que se elimino directamente: correrla
           a convergencia en multiples pasadas equivale a clustering de
           enlace simple sobre el descriptor, y con una ventana tan ancha sin
           acotar por camara, cualquier cadena de apariciones parecidas
           termina fusionando gente sin relacion real. No reintroducir sin
           un diseño que evite el efecto cadena.
        2) _fusionar_por_proximidad (usada aca por fusionar_cross_camara_dia)
           SI se mantiene, pero tenia el mismo problema por otra via: su
           unico filtro era el color de ropa superior obligatorio, un solo
           campo de muy pocas categorias (ej. 'negro' es carisimo) -- eso
           bastaba para que casi cualquier par dentro de la ventana de 90s
           pasara el filtro, y una secuencia de apariciones asi encadenadas
           terminaba fusionando gente de puntas opuestas del dia. Se
           corrigio exigiendo TAMBIEN el minimo de coincidencias de
           _comparar_descriptores (ver ese metodo), no solo el color.
        Devuelve {'continuidad', 'cross_camara', 'pasadas'}."""
        continuidad_total = cross_camara_total = 0
        pasada = 0
        for pasada in range(1, max_pasadas + 1):
            continuidad = self.fusionar_continuidad_sesiones(
                fecha, umbral_continuidad_seg, umbral_alta_confianza_seg
            )
            cross_camara = sum(self.fusionar_cross_camara_dia(
                fecha, umbral_cross_camara_seg, coincidencias_minimas
            ).values())
            continuidad_total += continuidad
            cross_camara_total += cross_camara
            if continuidad == 0 and cross_camara == 0:
                break
        return {"continuidad": continuidad_total, "cross_camara": cross_camara_total, "pasadas": pasada}

    def limpiar_detecciones_espurias(self, fecha, duracion_min_seg: float = 2.0) -> int:
        """Borra retroactivamente 'personas' que son ruido de deteccion (un
        falso positivo de YOLO/ByteTrack que dura un frame o casi, no una
        persona real) -- correccion para datos analizados ANTES de que
        PersonTracker.min_frames_confirmacion existiera, que exige que un id
        sobreviva unos frames consecutivos antes de crear su fila (ver
        tracking.py). Candidato a 'ruido': dura menos de duracion_min_seg Y
        nadie depende de el via cliente_id (no es la raiz de una cadena
        fusionada por auditar_sesion()/fusionar_cross_camara_dia() -- correr
        esta limpieza DESPUES de fusionar, nunca antes, para no borrar una
        raiz que ya tiene dependientes). Borra en cascada (trayectorias/
        visitas) via ON DELETE CASCADE del schema. 'fecha' es un date (o
        string 'YYYY-MM-DD'). Devuelve cuantas filas se borraron."""
        if not self.conn:
            return 0

        def _run():
            cur = self.conn.cursor()
            cur.execute(
                "DELETE FROM personas p "
                "USING sesiones_video sv "
                "WHERE sv.id = p.sesion_id "
                "AND sv.inicio::date = %s "
                "AND p.es_empleado = false "
                "AND p.ultima_deteccion - p.primera_deteccion < make_interval(secs => %s) "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM personas p2 WHERE p2.cliente_id = p.id AND p2.id <> p.id"
                ")",
                (fecha, duracion_min_seg)
            )
            borradas = cur.rowcount
            self.conn.commit()
            cur.close()
            print(f"[DB] Limpieza retroactiva ({fecha}): {borradas} detecciones espurias "
                  f"(<{duracion_min_seg}s, sin dependientes) borradas.")
            return borradas
        return self._con_reconexion(_run, default=0)

    def borrar_sin_descripcion(self, fecha=None) -> int:
        """Borra 'personas' sin descripcion_visual -- nunca llegaron a
        describirse (el streak de DESCRIPCION_STREAK_FRAMES nunca se
        completo, o Gemini/Groq fallo) asi que no hay forma de compararlas ni
        fusionarlas con nada; no aportan valor y solo inflan el conteo. Antes
        de borrar una raiz (id = cliente_id) que tenga dependientes (otras
        filas fusionadas contra ella via cliente_id), esos dependientes se
        reapuntan al proximo id CON descripcion real que quede vivo en el
        mismo grupo -- la FK personas.cliente_id es ON DELETE SET NULL, y sin
        este paso quedarian huerfanos (cliente_id=NULL) en vez de seguir
        agrupados. Si ningun dependiente tiene descripcion tampoco, no hay
        nada que preservar: se borran todos junto con la raiz. 'fecha', si
        viene (date o 'YYYY-MM-DD'), acota el borrado a las sesiones de ese
        dia; si es None, aplica a TODA la BD. Devuelve cuantas filas se
        borraron."""
        if not self.conn:
            return 0

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            filtro_fecha = "AND sv.inicio::date = %s" if fecha else ""
            params_base = (fecha,) if fecha else ()

            cur.execute(
                f"SELECT p.id, "
                f"  (SELECT min(p2.id) FROM personas p2 "
                f"     WHERE p2.cliente_id = p.id AND p2.id <> p.id "
                f"     AND p2.descripcion_visual IS NOT NULL) AS nuevo_canon "
                f"FROM personas p JOIN sesiones_video sv ON sv.id = p.sesion_id "
                f"WHERE p.descripcion_visual IS NULL AND p.id = p.cliente_id "
                f"AND EXISTS (SELECT 1 FROM personas p2 WHERE p2.cliente_id = p.id AND p2.id <> p.id) "
                f"{filtro_fecha}",
                params_base
            )
            raices = cur.fetchall()
            for r in raices:
                if r["nuevo_canon"] is not None:
                    cur.execute(
                        "UPDATE personas SET cliente_id = %s WHERE cliente_id = %s AND id <> %s",
                        (r["nuevo_canon"], r["id"], r["id"])
                    )

            cur.execute(
                f"DELETE FROM personas p USING sesiones_video sv "
                f"WHERE sv.id = p.sesion_id AND p.descripcion_visual IS NULL {filtro_fecha}",
                params_base
            )
            borradas = cur.rowcount
            self.conn.commit()
            cur.close()
            alcance = f"dia {fecha}" if fecha else "TODA la BD"
            print(f"[DB] Borrado sin descripcion ({alcance}): {len(raices)} raices reapuntadas, "
                  f"{borradas} filas borradas.")
            return borradas
        return self._con_reconexion(_run, default=0)

    def auditar_sesion(self, sesion_id: Optional[int], camara_id: int,
                        umbral_mismo_momento_seg: float = 90.0,
                        coincidencias_minimas: int = 3) -> dict:
        """Corre UNA VEZ terminado el analisis de un video, ANTES de cerrar la
        sesion (ver main.py) -- red de seguridad para lo que el matching en
        vivo (PersonTracker/GeminiReID.clasificar) puede haber dejado pasar:

        1) Calcula zona_id de cada persona de ESTA sesion (la zona con mas
           puntos de trayectoria) -- no se hace en ningun otro lugar del
           pipeline normal. Usado para reportes (no para decidir empleado).
        2) Busca, entre TODAS las personas de HOY en camaras del mismo grupo
           fisico que 'camara_id' (self.grupos_camara), pares con horario de
           'primera_deteccion' a menos de 'umbral_mismo_momento_seg' de
           diferencia, en camaras distintas, con cliente_id distinto pero
           colores de ropa compatibles -- son casi siempre la MISMA persona
           vista por dos angulos a la vez que el matching en vivo no llego a
           unir (ej. un angulo describe menos prendas que otro). Se fusionan
           por cliente_id (nunca se borra nada).

        OJO: la decision empleado-vs-cliente por Zona Caja YA NO vive aca --
        vivia en un paso 2 que se elimino porque nulificaba trayectorias.zona_id
        de quien no matcheara un empleado conocido, y eso le destruia a
        reclasificar_por_mayoria_zona() (que corre DESPUES, ver main.py) la
        evidencia cruda que necesita para calcular la mayoria de cada
        persona -- un empleado real con una descripcion nueva que este paso
        no lograra matchear terminaba con TODOS sus puntos de Caja en NULL
        antes de que la mayoria pudiera siquiera evaluarlo. Ver
        Persistencia.reclasificar_por_mayoria_zona(), la unica fuente de
        verdad para esa decision ahora.

        Devuelve un resumen {'fusiones_cross_camara'} para loggear en consola."""
        if not self.conn or not sesion_id:
            return {}

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            resumen = {"fusiones_cross_camara": 0}

            # ── 1) zona_id por persona de esta sesion (moda de su trayectoria) ──
            # OJO: 'zona_id' existe tanto en trayectorias como en personas --
            # hay que calificar todas las referencias o Postgres tira
            # "column reference is ambiguous" y aborta la transaccion entera.
            cur.execute(
                "SELECT t.persona_id AS persona_id, t.zona_id AS zona_id, count(*) AS n "
                "FROM trayectorias t JOIN personas p ON p.id = t.persona_id "
                "WHERE p.sesion_id = %s AND t.zona_id IS NOT NULL "
                "GROUP BY t.persona_id, t.zona_id",
                (sesion_id,)
            )
            conteos: dict = {}
            for r in cur.fetchall():
                conteos.setdefault(r["persona_id"], []).append((r["zona_id"], r["n"]))
            for pid, pares in conteos.items():
                zona_dominante = max(pares, key=lambda x: x[1])[0]
                cur.execute("UPDATE personas SET zona_id = %s WHERE id = %s", (zona_dominante, pid))

            # ── 2) fusion cross-camara por horario cercano (mismo grupo fisico) ──
            camaras_grupo = self.grupos_camara.get(camara_id, [camara_id])
            cur.execute(
                "SELECT p.id, p.cliente_id, p.primera_deteccion, p.descripcion_visual, sv.camara_id "
                "FROM personas p JOIN sesiones_video sv ON sv.id = p.sesion_id "
                "WHERE sv.camara_id = ANY(%s) AND p.es_empleado = false "
                "AND p.primera_deteccion BETWEEN "
                "  (SELECT min(primera_deteccion) - interval '3 minutes' FROM personas WHERE sesion_id = %s) "
                "  AND (SELECT max(primera_deteccion) + interval '3 minutes' FROM personas WHERE sesion_id = %s) "
                "ORDER BY p.primera_deteccion",
                (camaras_grupo, sesion_id, sesion_id)
            )
            candidatos = cur.fetchall()
            resumen["fusiones_cross_camara"] = self._fusionar_por_proximidad(
                cur, candidatos, umbral_mismo_momento_seg, coincidencias_minimas
            )

            self.conn.commit()
            cur.close()
            print(f"[DB] Auditoria post-analisis (sesion {sesion_id}): "
                  f"{resumen['fusiones_cross_camara']} fusionadas por horario cruzado entre camaras.")
            return resumen
        return self._con_reconexion(_run, default={})

    def cerrar(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

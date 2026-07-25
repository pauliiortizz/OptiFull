"""Capa de persistencia contra Supabase (Postgres). Todos los metodos son
no-op si no hay conexion (BD deshabilitada o inalcanzable) -- el pipeline
sigue funcionando solo con el reporte por consola."""
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

from deteccion.utils import frame_to_dt
from deteccion.gemini_reid import _obligatorios_coinciden


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

    def limpiar_sesiones_incompletas(self, excluir_id: Optional[int] = None) -> int:
        """Busca sesiones de video sin 'fin' -- quedaron a medio analizar en
        una corrida anterior que se corto antes de llegar a cerrar_sesion()
        (crash, Ctrl+C, cupo de API agotado, corte de luz, etc.) -- y las
        borra junto con todos sus datos dependientes. Se llama al arrancar
        CADA analisis nuevo, asi las sesiones fantasma de una corrida
        interrumpida nunca llegan a contaminar el Re-ID entre camaras ni los
        reportes. 'excluir_id', si viene, es la sesion recien creada en ESTA
        corrida (nunca hay que borrarla a si misma)."""
        def _run():
            if not self.conn:
                return 0
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, camara_id, inicio, archivo_path FROM sesiones_video WHERE fin IS NULL"
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

    def guardar_trayectorias_parcial(self, traj_chunk: list, fps: float, inicio: datetime) -> int:
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
            batch = []
            for t in traj_chunk:
                persona_db_id = self.persona_db_ids.get(t["sid"])
                if persona_db_id is None:
                    continue
                ts = frame_to_dt(t["frame"], fps, inicio)
                batch.append((
                    persona_db_id, t["zona_id"], ts,
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
                "(persona_id, zona_id, timestamp, centroide_x, centroide_y, "
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
            if _obligatorios_coinciden(descripcion, descripcion_emp):
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
        Gemini reidentifico a esta persona. Si la descripcion matchea a un
        empleado YA CONFIRMADO (ver _empleado_conocido_que_matchea), se marca
        es_empleado automaticamente en la fila raiz de la cadena."""
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
            match_empleado = self._empleado_conocido_que_matchea(cur, descripcion)
            if match_empleado is not None:
                if cliente_id_hint is None:
                    # Fila nueva, sin nadie mas dependiendo de ella todavia --
                    # se puede fusionar directo con el empleado conocido sin
                    # dejar cadenas rotas.
                    cur.execute("UPDATE personas SET es_empleado = TRUE, cliente_id = %s WHERE id = %s",
                                (match_empleado, db_id))
                else:
                    # Ya es parte de una cadena existente (otras filas pueden
                    # depender de raiz_id via cliente_id) -- solo se marca el
                    # flag aca; el merge completo con reapuntado seguro de
                    # dependientes lo hace auditar_sesion() al final del video.
                    raiz_id = cliente_id_hint
                    cur.execute("UPDATE personas SET es_empleado = TRUE WHERE id = %s", (raiz_id,))
                print(f"[DB] Persona {db_id} matchea al empleado conocido {match_empleado}.")
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

    def guardar_personas(self, sesion_id, rows: list, traj_buffer: list, fps: float, inicio: datetime) -> None:
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
                    match_empleado = self._empleado_conocido_que_matchea(cur, descripcion)
                    if match_empleado is not None:
                        if cliente_id_hint is None:
                            cur.execute("UPDATE personas SET es_empleado = TRUE, cliente_id = %s WHERE id = %s",
                                        (match_empleado, db_id))
                        else:
                            cur.execute("UPDATE personas SET es_empleado = TRUE WHERE id = %s", (cliente_id_hint,))
                        print(f"[DB] Persona {db_id} matchea al empleado conocido {match_empleado}.")
            self.conn.commit()
            cur.close()
            print(f"[DB] {len(rows)} personas sincronizadas "
                  f"({ya_creadas} ya se habian creado durante el analisis).")
        self._con_reconexion(_run, default=None)

        if self.guardar_trayectorias and traj_buffer:
            self.guardar_trayectorias_parcial(traj_buffer, fps, inicio)

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

    def auditar_sesion(self, sesion_id: Optional[int], camara_id: int,
                        umbral_mismo_momento_seg: float = 90.0) -> dict:
        """Corre UNA VEZ terminado el analisis de un video, ANTES de cerrar la
        sesion (ver main.py) -- red de seguridad para lo que el matching en
        vivo (PersonTracker/GeminiReID.clasificar) puede haber dejado pasar:

        1) Calcula zona_id de cada persona de ESTA sesion (la zona con mas
           puntos de trayectoria) -- no se hace en ningun otro lugar del
           pipeline normal.
        2) Zona Caja es exclusiva de empleados (regla del negocio: como mucho
           3 en todo el local). Cualquier persona de esta sesion que quede
           con zona dominante = Caja y NO matchee la descripcion de ningun
           empleado ya conocido en la BD pierde esa zona (se recalcula con el
           resto de su trayectoria, igual que si nunca hubiera pasado por
           ahi). Si SI matchea a un empleado conocido, se fusiona con el
           (mismo cliente_id, es_empleado=true) en vez de contar como una
           persona nueva.
        3) Busca, entre TODAS las personas de HOY en camaras del mismo grupo
           fisico que 'camara_id' (self.grupos_camara), pares con horario de
           'primera_deteccion' a menos de 'umbral_mismo_momento_seg' de
           diferencia, en camaras distintas, con cliente_id distinto pero
           colores de ropa compatibles -- son casi siempre la MISMA persona
           vista por dos angulos a la vez que el matching en vivo no llego a
           unir (ej. un angulo describe menos prendas que otro). Se fusionan
           por cliente_id (nunca se borra nada).

        Devuelve un resumen {'zona_recalculada', 'reasignados_a_empleado',
        'fusiones_cross_camara'} para loggear en consola."""
        if not self.conn or not sesion_id:
            return {}

        def _run():
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            resumen = {"zona_recalculada": 0, "reasignados_a_empleado": 0, "fusiones_cross_camara": 0}

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

            # ── 2) Zona Caja exclusiva de empleados ──────────────────────────────
            cur.execute(
                "SELECT p.id, p.descripcion_visual "
                "FROM personas p JOIN zonas z ON z.id = p.zona_id "
                "WHERE p.sesion_id = %s AND z.tipo = 'caja' AND p.es_empleado = false",
                (sesion_id,)
            )
            sospechosos = cur.fetchall()
            if sospechosos:
                cur.execute(
                    "SELECT DISTINCT ON (cliente_id) cliente_id, descripcion_visual "
                    "FROM personas WHERE es_empleado = true AND descripcion_visual IS NOT NULL "
                    "ORDER BY cliente_id"
                )
                empleados_conocidos = [
                    (r["cliente_id"], json.loads(r["descripcion_visual"])) for r in cur.fetchall()
                ]
                for s in sospechosos:
                    desc = json.loads(s["descripcion_visual"]) if s["descripcion_visual"] else None
                    match = next(
                        (cid for cid, edesc in empleados_conocidos if desc and _obligatorios_coinciden(desc, edesc)),
                        None
                    )
                    if match is not None:
                        cur.execute(
                            "UPDATE personas SET cliente_id = %s, es_empleado = true WHERE id = %s",
                            (match, s["id"])
                        )
                        resumen["reasignados_a_empleado"] += 1
                    else:
                        # No matchea a ningun empleado conocido -- no puede ser
                        # un cliente "en Zona Caja" (regla del negocio), asi que
                        # se le saca esa zona y se recalcula con el resto de su
                        # trayectoria (misma logica que la limpieza manual).
                        cur.execute(
                            "UPDATE trayectorias SET zona_id = NULL "
                            "WHERE persona_id = %s AND zona_id IN (SELECT id FROM zonas WHERE tipo = 'caja')",
                            (s["id"],)
                        )
                        cur.execute(
                            "SELECT zona_id FROM trayectorias WHERE persona_id = %s AND zona_id IS NOT NULL "
                            "GROUP BY zona_id ORDER BY count(*) DESC LIMIT 1",
                            (s["id"],)
                        )
                        row = cur.fetchone()
                        cur.execute(
                            "UPDATE personas SET zona_id = %s WHERE id = %s",
                            (row["zona_id"] if row else None, s["id"])
                        )
                        resumen["zona_recalculada"] += 1

            # ── 3) fusion cross-camara por horario cercano (mismo grupo fisico) ──
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
            ventana = timedelta(seconds=umbral_mismo_momento_seg)
            usados = set()
            for i, r in enumerate(candidatos):
                if r["id"] in usados or not r["descripcion_visual"]:
                    continue
                desc1 = json.loads(r["descripcion_visual"])
                grupo_ids = {r["cliente_id"]}
                for j in range(i + 1, len(candidatos)):
                    r2 = candidatos[j]
                    if r2["primera_deteccion"] - r["primera_deteccion"] > ventana:
                        break
                    if r2["id"] in usados or r2["camara_id"] == r["camara_id"] or not r2["descripcion_visual"]:
                        continue
                    if r2["cliente_id"] == r["cliente_id"]:
                        continue
                    desc2 = json.loads(r2["descripcion_visual"])
                    if _obligatorios_coinciden(desc1, desc2):
                        grupo_ids.add(r2["cliente_id"])
                        usados.add(r2["id"])
                if len(grupo_ids) > 1:
                    canon = min(grupo_ids)
                    resto = [c for c in grupo_ids if c != canon]
                    cur.execute("UPDATE personas SET cliente_id = %s WHERE cliente_id = ANY(%s)", (canon, resto))
                    resumen["fusiones_cross_camara"] += len(resto)
                usados.add(r["id"])

            self.conn.commit()
            cur.close()
            print(f"[DB] Auditoria post-analisis (sesion {sesion_id}): "
                  f"{resumen['zona_recalculada']} sacadas de Zona Caja (no matcheaban a un empleado), "
                  f"{resumen['reasignados_a_empleado']} vinculadas a un empleado ya conocido, "
                  f"{resumen['fusiones_cross_camara']} fusionadas por horario cruzado entre camaras.")
            return resumen
        return self._con_reconexion(_run, default={})

    def cerrar(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

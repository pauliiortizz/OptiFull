"""Capa de persistencia contra Supabase (Postgres). Todos los metodos son
no-op si no hay conexion (BD deshabilitada o inalcanzable) -- el pipeline
sigue funcionando solo con el reporte por consola."""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

from deteccion.utils import frame_to_dt


class Persistencia:
    def __init__(self, database_url: Optional[str], has_db: bool, guardar_trayectorias: bool,
                 camara_nombres: dict) -> None:
        self.database_url         = database_url
        self.has_db                = has_db
        self.guardar_trayectorias = guardar_trayectorias
        self.camara_nombres        = camara_nombres
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

    def guardar_descripcion_persona(self, sesion_id, sid: int, frame_num: int, fps: float,
                                      inicio: datetime, metodo_reid: str, descripcion: dict,
                                      cliente_id_hint: Optional[int] = None) -> Optional[int]:
        """Guarda (o actualiza) la fila de 'personas' apenas Gemini genera la
        descripcion visual de este cliente, sin esperar a que termine el
        analisis del video completo -- si el proceso se corta a mitad de
        camino, lo ya descrito no se pierde. 'cliente_id_hint', si viene, es
        el id de 'personas' de una sesion distinta (mismo dia) con la que
        Gemini reidentifico a esta persona."""
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
            self.conn.commit()
            cur.close()
            extra = f" (mismo cliente que persona_id={cliente_id_hint})" if cliente_id_hint else ""
            print(f"[DB] Descripcion guardada durante el analisis -> persona_id={db_id}{extra}")
            return db_id
        return self._con_reconexion(_run, default=None)

    def candidatos_reid_del_dia(self, fecha, excluir_ids: set) -> list:
        """Personas con descripcion visual ya guardada cuya primera deteccion
        fue el mismo dia calendario (en cualquier camara/sesion). Es la unica
        fuente de candidatos que usa Gemini para reidentificar -- nunca su
        propia memoria en RAM -- para poder reconocer al mismo cliente tanto
        dentro del mismo video como entre videos distintos del mismo dia."""
        def _run():
            if not self.conn:
                return []
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                "SELECT id, descripcion_visual, COALESCE(cliente_id, id) AS cliente_id "
                "FROM personas "
                "WHERE descripcion_visual IS NOT NULL AND primera_deteccion::date = %s "
                "ORDER BY primera_deteccion DESC",
                (fecha,)
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
                    candidatos.append({"persona_id": r["id"], "cliente_id": r["cliente_id"], "descripcion": desc})
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

    def cerrar(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

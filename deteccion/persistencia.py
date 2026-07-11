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

    def cargar_zonas(self, camara_id: int) -> list:
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

    def cerrar_sesion(self, sesion_id, fin: datetime) -> None:
        if not self.conn or not sesion_id:
            return
        cur = self.conn.cursor()
        cur.execute("UPDATE sesiones_video SET fin = %s WHERE id = %s", (fin, sesion_id))
        self.conn.commit()
        cur.close()
        print(f"[DB] Sesion cerrada -> fin={fin}")

    def guardar_personas(self, sesion_id, rows: list, traj_buffer: list, fps: float, inicio: datetime) -> None:
        if not self.conn or not sesion_id:
            return
        cur = self.conn.cursor()
        stable_to_db = {}
        for r in rows:
            sid         = r["id"]
            p_ini       = frame_to_dt(r["_first_frame"], fps, inicio)
            p_fin       = frame_to_dt(r["_last_frame"],  fps, inicio)
            descripcion = r.get("descripcion")
            # descripcion es un dict estructurado (rasgos de Re-ID); se guarda
            # como texto JSON en la columna TEXT (sin necesidad de cambiar el schema).
            descripcion_json = json.dumps(descripcion, ensure_ascii=False) if descripcion else None
            cur.execute(
                "INSERT INTO personas "
                "(sesion_id, primera_deteccion, ultima_deteccion, metodo_reid, descripcion_visual) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (sesion_id, p_ini, p_fin, r.get("metodo_reid"), descripcion_json)
            )
            stable_to_db[sid] = cur.fetchone()[0]
        self.conn.commit()
        print(f"[DB] {len(rows)} personas insertadas.")

        if self.guardar_trayectorias and traj_buffer:
            batch = []
            for t in traj_buffer:
                persona_db_id = stable_to_db.get(t["sid"])
                if persona_db_id is None:
                    continue
                ts = frame_to_dt(t["frame"], fps, inicio)
                batch.append((
                    persona_db_id, t["zona_id"], ts,
                    round(t["cx"], 2), round(t["cy"], 2),
                    round(t["box"][0], 2), round(t["box"][1], 2),
                    round(t["box"][2], 2), round(t["box"][3], 2),
                ))
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO trayectorias "
                "(persona_id, zona_id, timestamp, centroide_x, centroide_y, "
                " bbox_x1, bbox_y1, bbox_x2, bbox_y2) "
                "VALUES %s",
                batch,
            )
            self.conn.commit()
            print(f"[DB] {len(batch)} trayectorias insertadas.")
        cur.close()

    def guardar_heatmap(self, camara_id, sesion_id, inicio_dt, fin_dt, stats: dict,
                         imagen_path: str, total_detecciones: int, frames_procesados: int) -> Optional[int]:
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

    def cerrar(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

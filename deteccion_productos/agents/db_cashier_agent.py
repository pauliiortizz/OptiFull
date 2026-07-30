"""
DbCashierInterfaceAgent
------------------------
Cumple el mismo contrato que CashierInterfaceAgent (confirmar_producto,
elegir_entre_candidatos, producto_manual) pero en vez de esperar
input() de teclado, escribe en la tabla 'caja_estado' de la base
compartida y espera (sondeando cada POLL_INTERVAL_SEG) a que el
endpoint web (frontend/api/productos.py) escriba una respuesta ahí,
tras el clic de la cajera en el navegador.

Mismo patrón que el resto del sistema: este proceso
(deteccion_productos/main.py) y el proceso de Flask
(frontend/serve_dashboard.py) NO se importan entre sí -- se comunican
solo a través de la base de datos compartida (ver db/schema.sql,
tabla caja_estado).

También expone debe_detenerse(), que main.py chequea entre frame y
frame para cortar el loop en un punto seguro cuando se pide
"Detener caja" desde el navegador, en vez de matar el proceso a la
fuerza.
"""

import json
import os
import time

import psycopg2


POLL_INTERVAL_SEG = 1.0


def _conectar():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "Falta DATABASE_URL en el .env (la misma conexión a Supabase "
            "que usa frontend/api/db.py)."
        )
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    return conn


class DetenerCaja(Exception):
    """Señal de que se pidió 'Detener caja' desde el navegador mientras
    se esperaba una decisión de la cajera."""


class DbCashierInterfaceAgent:
    def __init__(self):
        self.conn = _conectar()

    def debe_detenerse(self):
        cur = self.conn.cursor()
        cur.execute("SELECT estado FROM caja_estado WHERE id = 1")
        row = cur.fetchone()
        cur.close()
        return row is not None and row[0] == "detener"

    def marcar_inactivo(self):
        """Se llama al terminar el loop (ver main.py, finally de run()),
        para que 'estado' no quede pegado en 'detener' -- si no, la
        próxima consulta a /productos/estado mostraría un estado que ya
        no es cierto (el proceso ya terminó, no está "por detenerse")."""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE caja_estado
            SET estado = 'inactivo', pendiente = NULL, respuesta = NULL,
                actualizado_en = NOW()
            WHERE id = 1
        """)
        cur.close()

    def _pedir_decision(self, pendiente):
        """Escribe 'pendiente' en caja_estado y bloquea (sondeando) hasta
        que el endpoint web escriba una 'respuesta', o hasta que pidan
        detener la caja."""
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE caja_estado
            SET estado = 'esperando_decision', pendiente = %s,
                respuesta = NULL, actualizado_en = NOW()
            WHERE id = 1
        """, (json.dumps(pendiente, ensure_ascii=False),))
        cur.close()

        while True:
            time.sleep(POLL_INTERVAL_SEG)
            cur = self.conn.cursor()
            cur.execute("SELECT estado, respuesta FROM caja_estado WHERE id = 1")
            estado, respuesta = cur.fetchone()
            cur.close()

            if estado == "detener":
                raise DetenerCaja()

            if respuesta is not None:
                cur = self.conn.cursor()
                cur.execute("""
                    UPDATE caja_estado
                    SET estado = 'inactivo', pendiente = NULL, respuesta = NULL,
                        actualizado_en = NOW()
                    WHERE id = 1
                """)
                cur.close()
                return respuesta  # psycopg2 ya lo devuelve como dict (JSONB)

    def confirmar_producto(self, producto, confianza_llm):
        respuesta = self._pedir_decision({
            "tipo": "confirmar",
            "producto": producto,
            "confianza": confianza_llm,
        })
        if respuesta.get("accion") == "cancelar":
            return None, 0
        if respuesta.get("accion") == "manual":
            return self.producto_manual()
        return producto, int(respuesta.get("cantidad") or 0)

    def elegir_entre_candidatos(self, candidatos, datos_llm=None):
        respuesta = self._pedir_decision({
            "tipo": "elegir",
            "candidatos": candidatos,
            "datos_llm": datos_llm,
        })
        if respuesta.get("accion") == "cancelar":
            return None, 0
        if respuesta.get("accion") == "manual":
            return self.producto_manual()
        indice = respuesta.get("indice")
        if indice is None or not (0 <= indice < len(candidatos)):
            return None, 0
        return candidatos[indice], int(respuesta.get("cantidad") or 0)

    def producto_manual(self):
        respuesta = self._pedir_decision({"tipo": "manual"})
        if respuesta.get("accion") == "cancelar":
            return None, 0
        sku = respuesta.get("sku")
        cantidad = int(respuesta.get("cantidad") or 0)
        if not sku or cantidad <= 0:
            return None, 0
        return {"sku": sku, "nombre": f"(cargado manualmente: {sku})"}, cantidad

    def close(self):
        self.conn.close()

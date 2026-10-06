"""
main.py
-------
Orquestador del pipeline de checkout.

Flujo:
  1. CaptureAgent obtiene frames del video/cámara
  2. MotionAgent decide si hay que analizar (estable + escena nueva)
  3. VisionAgent llama al LLM (Claude) y extrae JSON con datos del producto
  4. MatchingAgent busca el producto en la base
  5. CashierInterfaceAgent muestra a la cajera y espera confirmación
     con la cantidad
  6. StockAgent descuenta stock

Reglas importantes:
  - El LLM se llama SOLO cuando MotionAgent lo autoriza. Nunca en
    cada frame.
  - La cajera siempre confirma antes de descontar (nunca automático).
  - Si el LLM no detecta producto (frame vacío/borroso), no bloquea:
    solo ignora y sigue procesando.

Uso:
  python main.py --source data/videos/prueba1.mp4
  python main.py --source http://ip.del.celular:8080/video    # IP Webcam
  python main.py --source data/videos/prueba1.mp4 --roi 100,50,700,400
"""

import argparse
import sys
import time
import traceback

# Forzar UTF-8 en stdout/stderr: corriendo como subproceso (ver
# frontend/api/productos.py, botón "Iniciar caja") no hay una consola
# interactiva detrás, y la codificación por default de Windows en ese
# caso no soporta los símbolos ✔/⚠ que se imprimen más abajo -- sin
# esto, el proceso se caía después de CADA venta, justo en el print de
# confirmación (el descuento de stock ya se había guardado bien; era
# puramente el print el que reventaba).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Cargar variables del archivo .env (donde está la API key).
# Tiene que ir ANTES de importar los agentes que la usan.
from dotenv import load_dotenv
load_dotenv()

from config import TARGET_FPS
from agents.capture_agent import CaptureAgent
from agents.motion_agent import MotionAgent
from agents.vision_agent import VisionAgent
from agents.matching_agent import MatchingAgent
from agents.cashier_interface_agent import CashierInterfaceAgent
from agents.db_cashier_agent import DbCashierInterfaceAgent, DetenerCaja
from agents.stock_agent import StockAgent


class CheckoutOrchestrator:
    def __init__(self, source, roi=None, cashier=None):
        """
        cashier: agente de cajera a usar. Por default, la consola
        (CashierInterfaceAgent) para pruebas locales con teclado. Para
        que la caja se maneje desde la web, pasar un
        DbCashierInterfaceAgent() -- mismo contrato, espera la
        decisión de la cajera vía la base de datos en vez de input().
        """
        self.stock = StockAgent()
        productos = self.stock.cargar_productos()
        if not productos:
            raise RuntimeError("Base vacía. Corré: python setup_db.py")
        print(f"[Orquestador] {len(productos)} productos cargados")

        self.capture = CaptureAgent(source, target_fps=TARGET_FPS)
        self.motion = MotionAgent(roi=roi)
        self.vision = VisionAgent(roi=roi)
        self.matcher = MatchingAgent(productos)
        self.cashier = cashier if cashier is not None else CashierInterfaceAgent()

        # Índice para resolver SKU cuando la cajera carga manual
        self._por_sku = {p["sku"]: p for p in productos}

    def _procesar_deteccion(self, datos_llm, ts):
        """
        Recibe el JSON del VisionAgent y decide qué hacer:
          - reconocido -> cajera confirma y pone cantidad
          - confirmar (ambiguo) -> cajera elige y pone cantidad
          - no_reconocido con producto detectado por LLM pero no en base
              -> cajera carga manual
          - no_reconocido porque LLM no vio producto claro
              -> ignoramos y seguimos (no bloqueamos el video)
        """
        resultado = self.matcher.identificar(datos_llm)
        estado = resultado["estado"]

        producto = None
        cantidad = 0

        if estado == "reconocido":
            print(f"[{ts:.1f}] Matching: reconocido ({resultado['producto']['nombre']})")
            producto, cantidad = self.cashier.confirmar_producto(
                resultado["producto"], resultado["confianza"],
            )

        elif estado == "confirmar":
            print(f"[{ts:.1f}] Matching: varios candidatos, pidiendo confirmación")
            producto, cantidad = self.cashier.elegir_entre_candidatos(
                resultado["candidatos"], datos_llm=datos_llm,
            )

        else:  # no_reconocido
            razon = resultado.get("razon", "desconocida")
            # Si el LLM directamente no vio nada claro, no bloqueamos:
            # solo lo registramos y seguimos. Estos casos incluyen frames
            # vacíos, borrosos, o donde solo hay una mano.
            if razon in ("sin_producto", "confianza_llm_baja"):
                print(f"[{ts:.1f}] Sin producto claro en cámara ({razon}). Ignorado.")
                return False
            # Si el LLM SÍ vio un producto pero no está en la base
            # (marca/tamaño desconocidos), pedimos carga manual.
            print(f"[{ts:.1f}] Producto no está en base ({razon}). Carga manual.")
            producto, cantidad = self.cashier.producto_manual()

        if producto is None or cantidad <= 0:
            print(f"[{ts:.1f}] Cajera canceló la operación.\n")
            return False

        # Si vino de carga manual, resolver contra la BD para tener
        # nombre completo y validar que existe.
        if producto["sku"] not in self._por_sku:
            print(f"[{ts:.1f}] SKU {producto['sku']} no existe en la base. Cancelado.\n")
            return False
        producto = self._por_sku[producto["sku"]]

        nuevo_stock = self.stock.descontar(
            sku=producto["sku"],
            cantidad=cantidad,
            confianza_llm=datos_llm.get("confianza", 0),
            estado_matching=estado,
            datos_llm=datos_llm,
            confirmado_por_cajera=True,
        )
        print(f"[{ts:.1f}] ✔ Descontadas {cantidad} unidad(es) de "
              f"{producto['nombre']}. Stock restante: {nuevo_stock}\n")
        return True

    def run(self):
        print("\n[Orquestador] Iniciando...\n")
        llm_calls = 0
        ventas = 0

        # Si la cajera es la de base de datos (modo web), chequeamos entre
        # frame y frame si pidieron "Detener caja" -- así cortamos en un
        # punto seguro en vez de matar el proceso a la fuerza. La cajera de
        # consola no tiene este método (se corta con Ctrl+C como siempre).
        debe_detenerse = getattr(self.cashier, "debe_detenerse", lambda: False)

        try:
            for frame, ts in self.capture.frames():
                if debe_detenerse():
                    print("\n[Orquestador] Detenido desde la web.")
                    break

                if not self.motion.deberia_analizar(frame, ts):
                    continue

                print(f"[{ts:.1f}] Escena estable y nueva -> consultando LLM...")
                llm_calls += 1

                try:
                    t0 = time.perf_counter()
                    datos_llm = self.vision.analizar(frame)
                    print(f"[{ts:.1f}] LLM respondió en {time.perf_counter() - t0:.2f}s")
                except Exception as e:
                    # No queremos que un error de red / API caiga todo el
                    # sistema. Logueamos, marcamos el frame como analizado
                    # (para no reintentar el mismo), y seguimos.
                    print(f"[{ts:.1f}] Error del VisionAgent: {e}")
                    self.motion.marcar_analizado(frame)
                    continue

                # Marcamos analizado SIEMPRE (con o sin producto detectado)
                # para no re-analizar la misma escena en bucle si el LLM
                # devolvió "no producto".
                self.motion.marcar_analizado(frame)

                print(f"[{ts:.1f}] LLM: {datos_llm}")
                try:
                    if self._procesar_deteccion(datos_llm, ts):
                        ventas += 1
                except DetenerCaja:
                    print("\n[Orquestador] Detenido desde la web "
                          "(mientras se esperaba una decisión).")
                    break

        except KeyboardInterrupt:
            print("\n[Orquestador] Interrumpido por usuario (Ctrl+C)")
        except Exception as e:
            print(f"\n[Orquestador] Error inesperado: {e}")
            traceback.print_exc()
        finally:
            print(f"\n[Orquestador] Fin. Llamadas al LLM: {llm_calls}, "
                  f"ventas confirmadas: {ventas}")
            marcar_inactivo = getattr(self.cashier, "marcar_inactivo", None)
            if marcar_inactivo is not None:
                marcar_inactivo()
            self.capture.release()
            self.stock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--roi", default=None, help="x1,y1,x2,y2")
    parser.add_argument(
        "--web", action="store_true",
        help="Usar la cajera web (base de datos) en vez de la consola. "
             "La usa frontend/api/productos.py al arrancar la caja desde "
             "el botón 'Iniciar caja'.",
    )
    args = parser.parse_args()

    roi = None
    if args.roi:
        roi = tuple(int(v) for v in args.roi.split(","))
        assert len(roi) == 4

    cashier = DbCashierInterfaceAgent() if args.web else None
    CheckoutOrchestrator(args.source, roi=roi, cashier=cashier).run()

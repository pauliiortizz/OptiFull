"""
test_un_frame.py
----------------
Prueba el VisionAgent + MatchingAgent con UN SOLO frame de un video,
para verificar que el LLM identifica bien un producto sin gastar
muchas llamadas de más.

Uso:
  python test_un_frame.py data/videos/prueba1.mp4 45

  donde 45 es el SEGUNDO del video donde sabés que hay un producto
  bien mostrado de frente. Extrae ese frame, lo manda al modelo, y
  muestra qué identificó + contra qué producto matcheó.

Esto hace UNA sola llamada al LLM. Ideal para probar sin gastar de más.
"""

import sys
import cv2

from dotenv import load_dotenv
load_dotenv()

from agents.vision_agent import VisionAgent
from agents.matching_agent import MatchingAgent
from agents.stock_agent import StockAgent


def extraer_frame(video_path, segundo):
    """Extrae el frame del video en el segundo indicado."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    frame_objetivo = int(fps * segundo)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_objetivo)

    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"No se pudo leer el frame en el segundo {segundo}")
    return frame


def main():
    if len(sys.argv) < 3:
        print("Uso: python test_un_frame.py <video> <segundo>")
        print("Ejemplo: python test_un_frame.py data/videos/prueba1.mp4 45")
        return

    video_path = sys.argv[1]
    segundo = float(sys.argv[2])

    print(f"Extrayendo frame del segundo {segundo} de {video_path}...")
    frame = extraer_frame(video_path, segundo)

    # Guardamos el frame extraído para que puedas verlo y confirmar
    # que efectivamente muestra el producto de frente.
    cv2.imwrite("frame_prueba.jpg", frame)
    print("Frame guardado como 'frame_prueba.jpg' (abrilo para ver qué se mandó)")

    print("\nEnviando al LLM (1 sola llamada)...")
    vision = VisionAgent()
    datos = vision.analizar(frame)
    print(f"\n--- El LLM devolvió ---")
    for k, v in datos.items():
        print(f"  {k}: {v}")

    if not datos.get("producto_detectado"):
        print("\n⚠ El LLM no detectó un producto claro en este frame.")
        print("  Probá otro segundo donde el producto se vea mejor de frente.")
        return

    print(f"\n--- Matching contra la base ---")
    stock = StockAgent()
    matcher = MatchingAgent(stock.cargar_productos())
    resultado = matcher.identificar(datos)
    print(f"  Estado: {resultado['estado']}")
    if resultado["estado"] == "reconocido":
        print(f"  ✔ Producto: {resultado['producto']['nombre']} "
              f"(SKU {resultado['producto']['sku']})")
    elif resultado["estado"] == "confirmar":
        print(f"  Candidatos:")
        for c in resultado["candidatos"]:
            print(f"    - {c['nombre']} (SKU {c['sku']})")
    else:
        print(f"  ✘ No reconocido: {resultado.get('razon')}")
    stock.close()


if __name__ == "__main__":
    main()

"""
VisionAgent (versión Claude / Anthropic)
----------------------------------------
Envía un frame al modelo Claude Haiku 4.5 y recibe JSON estructurado
con los datos del producto.

Por qué Claude Haiku 4.5:
  - Rápido y de bajo costo (~$0.001 por imagen), ideal para procesar
    muchos frames.
  - Excelente calidad de visión para identificar productos comunes.
  - Sin los problemas de cuota-cero del free tier de otros proveedores:
    pagás por uso real desde el crédito cargado.

La API key se lee de la variable de entorno ANTHROPIC_API_KEY, que a
su vez se carga desde el archivo .env (ver más abajo).

Para cambiar de proveedor (OpenAI, Gemini, etc):
  - SOLO se toca este archivo. El resto del pipeline no se entera.

Formato JSON que devuelve (idéntico a las versiones anteriores):
  {
    "producto_detectado": true,
    "marca": "Coca-Cola",
    "nombre_producto": "Coca-Cola Zero",
    "variante": "Zero",
    "tamano": {"valor": 500, "unidad": "ml"},
    "categoria": "gaseosa",
    "confianza": 0.92
  }

Latencia: el modelo tarda en proporción a lo que ESCRIBE. Por eso se le
pide el JSON en una sola línea y sin campos que el pipeline no usa (antes
había un campo "observaciones": medido con frames reales, sacarlo y
compactar el JSON bajó la respuesta de ~122 a ~78 tokens y la llamada de
~1.8s a ~1.45s en promedio).
"""

import base64
import json
import os
import time

import cv2
import httpx
from anthropic import Anthropic, DefaultHttpxClient

from config import MODEL

MAX_LADO_IMAGEN = 1024


PROMPT_SISTEMA = """Sos un analizador de productos para el sistema de caja de una tienda de conveniencia en una estación de servicio YPF de Argentina.

Recibís una imagen tomada desde una cámara en la zona de escaneo de la caja. Tenés que identificar el producto que se ve y devolver sus datos en JSON.

Reglas:
- Solo respondé con el JSON, sin texto adicional, sin backticks, sin markdown.
- Si no ves un producto claro (solo mano, fondo, o imagen borrosa), devolvé: {"producto_detectado": false}
- Si ves un producto, devolvé el JSON con este formato EXACTO:

{
  "producto_detectado": true,
  "marca": "string",
  "nombre_producto": "string",
  "variante": "string o null",
  "tamano": {"valor": number, "unidad": "ml|l|g|kg|cc|unidades"},
  "categoria": "string",
  "confianza": number
}

Definición de cada campo (para NO confundirlos):
- "marca": el nombre de fabricante/marca impreso en el envase (ej: "Coca-Cola", "Tofi", "Milka", "Lays", "Guaymallen"). NUNCA pongas acá el tipo genérico de producto (alfajor, gaseosa, snack, chocolate, golosina, agua) — eso va en "categoria".
- "nombre_producto": el nombre comercial completo tal como aparece en el envase (ej: "Alfajor Tofi Negro"). Esto NO reemplaza a "marca": la marca va igual en su propio campo, aunque se repita.
- "categoria": el tipo genérico de producto (alfajor, gaseosa, snack, chocolate, agua, energizante, etc.).
- "tamano": preferí SIEMPRE el peso o volumen neto real impreso en el envase (ej: "Contenido neto 46 g"), incluso en productos que se venden como pieza entera (alfajores, chocolates, snacks). Usá "unidades" solo si genuinamente no hay ningún peso/volumen legible en el envase.

Ejemplos (marca real vs. categoría, no los confundas):
  Coca-Cola Zero 500ml -> {"marca": "Coca-Cola", "nombre_producto": "Coca-Cola Zero", "variante": "Zero", "tamano": {"valor": 500, "unidad": "ml"}, "categoria": "gaseosa"}
  Alfajor Tofi Negro    -> {"marca": "Tofi", "nombre_producto": "Alfajor Tofi Negro", "variante": "Chocolate Negro", "tamano": {"valor": 46, "unidad": "g"}, "categoria": "alfajor"}

Sé preciso con la variante y el tamaño: esos son los campos que distinguen productos similares (Coca 500ml vs Coca 1.5L, Coca Original vs Coca Zero, Ades Manzana vs Ades Naranja).
Si no podés leer un campo con certeza, ponelo como null y bajá la confianza.
Devolvé el JSON en UNA sola línea, sin espacios ni saltos de línea extra."""


class VisionAgent:
    def __init__(self, model=MODEL, roi=None):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Falta ANTHROPIC_API_KEY. Ponela en el archivo .env "
                "(ver .env.ejemplo) o como variable de entorno."
            )
        # Mantener viva la conexión con la API entre productos: por default
        # se cierra tras 5s sin uso, y en una caja real casi siempre pasan
        # más de 5s entre un producto y otro -- cada detección tenía que
        # volver a abrir la conexión (TCP + TLS hasta EE.UU.).
        self.client = Anthropic(api_key=api_key, http_client=DefaultHttpxClient(
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5,
                                keepalive_expiry=300)))
        self.model = model
        self.roi = roi

    def _frame_a_base64(self, frame):
        if self.roi is not None:
            x1, y1, x2, y2 = self.roi
            frame = frame[y1:y2, x1:x2]
        # La cámara del celular manda 1920x1080: ~6 veces más datos que el
        # video de prueba (832x464) para subir a la API en cada producto.
        # Achicar a 1024 px de lado mayor alcanza para leer el envase.
        alto, ancho = frame.shape[:2]
        if max(alto, ancho) > MAX_LADO_IMAGEN:
            escala = MAX_LADO_IMAGEN / max(alto, ancho)
            frame = cv2.resize(frame, (int(ancho * escala), int(alto * escala)),
                               interpolation=cv2.INTER_AREA)
        ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise RuntimeError("No se pudo codificar el frame como JPEG")
        return base64.standard_b64encode(buffer).decode("utf-8")

    def _llamar_llm(self, img_b64):
        """Una llamada al modelo. Devuelve el texto crudo de la respuesta."""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            system=PROMPT_SISTEMA,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": img_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Analizá el producto en la imagen y devolveme el JSON.",
                    },
                ],
            }],
        )
        return message.content[0].text.strip()

    def analizar(self, frame, max_retries=1):
        """
        Envía el frame al modelo y devuelve el dict parseado.
        Reintenta ante errores transitorios (red, sobrecarga).
        """
        img_b64 = self._frame_a_base64(frame)

        for intento in range(max_retries + 1):
            try:
                texto = self._llamar_llm(img_b64)
            except Exception as e:
                error_str = str(e)
                # 429 (rate limit) o 529 (overloaded) son transitorios
                transitorio = ("429" in error_str or "529" in error_str
                                or "overloaded" in error_str.lower())
                if transitorio and intento < max_retries:
                    print("[VisionAgent] API ocupada, reintentando en 5s...")
                    time.sleep(5)
                    continue
                raise

            # Limpiar posibles backticks por las dudas
            if texto.startswith("```"):
                texto = texto.strip("`").lstrip("json").strip()
            try:
                return json.loads(texto)
            except json.JSONDecodeError:
                if intento < max_retries:
                    print("[VisionAgent] JSON inválido, reintentando...")
                    continue
                print(f"[VisionAgent] Respuesta no parseable: {texto[:150]}")
                return {"producto_detectado": False, "error": "json_invalido"}

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from PIL import Image

load_dotenv()

# 1. API keys disponibles: si una se queda sin cupo, se prueba con la siguiente
API_KEYS = [
    clave
    for clave in (os.environ.get("GEMINI_API_KEY_1"), os.environ.get("GEMINI_API_KEY_2"))
    if clave
]
if not API_KEYS:
    raise RuntimeError("No hay ninguna API key configurada (revisá el archivo .env)")

# 2. Ruta del archivo a analizar: puede ser una imagen o un video
RUTA_ARCHIVO = "videos/video_productos.mp4"

EXTENSIONES_VIDEO = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

PROMPT = (
    "Identifica los productos de consumo masivo en la imagen o video. "
    "Cada objeto físico distinto debe aparecer una sola vez en el resultado: no repitas el mismo producto "
    "aunque se vea desde otro ángulo, reflejo, parcialmente tapado, o en distintos frames del video. "
    "Si hay varias unidades idénticas del mismo producto, agrúpalas en un solo elemento e indica cuántas hay en el campo 'cantidad'. "
    "Devuelve el resultado estrictamente en formato JSON, como una lista de objetos con los campos "
    "'marca', 'producto', 'variante' y 'cantidad'."
)


def cargar_contenido(client, ruta):
    """Devuelve el contenido listo para pasarle a generate_content, sea imagen o video."""
    extension = Path(ruta).suffix.lower()

    if extension in EXTENSIONES_VIDEO:
        archivo = client.files.upload(file=ruta)
        # Gemini procesa el video de forma asíncrona antes de poder usarlo
        while archivo.state.name == "PROCESSING":
            time.sleep(3)
            archivo = client.files.get(name=archivo.name)
        if archivo.state.name == "FAILED":
            raise RuntimeError(f"Gemini no pudo procesar el video: {archivo.state}")
        return archivo

    return Image.open(ruta)


def analizar(ruta_archivo):
    """Prueba cada API key en orden; si una devuelve 429 (cupo agotado), pasa a la siguiente."""
    ultimo_error = None
    for indice, api_key in enumerate(API_KEYS, start=1):
        client = genai.Client(api_key=api_key)
        try:
            contenido = cargar_contenido(client, ruta_archivo)
            return client.models.generate_content(
                model="gemini-2.5-flash",  # El modelo más rápido y económico para visión
                contents=[contenido, PROMPT],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
        except ClientError as error:
            if error.code == 429:
                print(f"[api key {indice}] cupo agotado, probando con la siguiente...")
                ultimo_error = error
                continue
            raise
    raise ultimo_error


response = analizar(RUTA_ARCHIVO)
print(response.text)

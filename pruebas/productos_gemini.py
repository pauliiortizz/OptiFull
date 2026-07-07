import time
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

# 1. Inicializa el cliente con tu API Key
client = genai.Client(api_key="AQ.Ab8RN6IuxXuipxaVaXsei6XR1muDMoieQ--VokyEvNvjo90mQw")

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


def cargar_contenido(ruta):
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


# 3. Cargo el archivo y se lo envío al modelo junto con el prompt
contenido = cargar_contenido(RUTA_ARCHIVO)

response = client.models.generate_content(
    model="gemini-2.5-flash",  # El modelo más rápido y económico para visión
    contents=[contenido, PROMPT],
    config=types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
    ),
)

print(response.text)

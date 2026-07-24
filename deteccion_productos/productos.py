import os
import re
from PIL import Image, ImageDraw
import torch
from transformers import AutoProcessor, PaliGemmaForConditionalGeneration

# Configura tu token de Hugging Face
os.environ["HF_TOKEN"] = "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"

model_id = "google/paligemma-3b-mix-224"
device = "cuda" if torch.cuda.is_available() else "cpu"

# 1. Cargar el procesador y el modelo (usando cuantización si tu GPU es ajustada)
processor = AutoProcessor.from_pretrained(model_id)
model = PaliGemmaForConditionalGeneration.from_pretrained(
    model_id,
    torch_dtype=torch.float32,
).to(device)

# 2. Cargar una imagen de prueba (por ejemplo, un paquete o botella en una góndola)
image_path = "videos/resaltador.jpeg"
image = Image.open(image_path).convert("RGB")

# 3. Definir el prompt en formato de texto
# PaliGemma responde muy bien a tareas directas como "detect [object]" o "caption [image]"
prompt = "detect product" 

# 4. Procesar y generar la respuesta
inputs = processor(text=prompt, images=image, return_tensors="pt").to(device)

with torch.no_grad():
    # min_new_tokens evita que el modelo corte con <eos> antes de emitir la caja detectada
    output = model.generate(**inputs, max_new_tokens=100, min_new_tokens=8, do_sample=False)

input_len = inputs["input_ids"].shape[-1]
generacion = output[0][input_len:]
resultado = processor.decode(generacion, skip_special_tokens=False)
print("Respuesta del modelo:", resultado)

# 5. Tomar solo la primera deteccion (las siguientes suelen ser ruido forzado por min_new_tokens)
primera = resultado.split(";")[0]
match = re.match(r"(<loc\d{4}>){4}\s*(.+?)<", primera + "<")
if match:
    locs = [int(n) for n in re.findall(r"<loc(\d{4})>", primera)]
    y_min, x_min, y_max, x_max = locs
    w, h = image.size
    caja = (
        round(x_min / 1024 * w),
        round(y_min / 1024 * h),
        round(x_max / 1024 * w),
        round(y_max / 1024 * h),
    )
    print(f"Objeto: {match.group(2).strip()} | Caja (x_min, y_min, x_max, y_max): {caja}")

    # 6. Dibujar la caja sobre la imagen para verificar visualmente la deteccion
    imagen_anotada = image.copy()
    draw = ImageDraw.Draw(imagen_anotada)
    draw.rectangle(caja, outline="red", width=5)
    salida_path = "videos/resaltador_deteccion.jpeg"
    imagen_anotada.save(salida_path)
    print(f"Imagen con la caja guardada en: {salida_path}")
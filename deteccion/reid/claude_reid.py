"""Cliente de Claude (Anthropic) para el Re-ID en la nube: misma funcion que
gemini_reid.py/groq_reid.py (describe personas una unica vez y clasifica IDs
nuevos contra candidatos perdidos, con rate limiting local), pero contra
Claude en vez de Gemini/Groq. Pensado como alternativa intercambiable --
PersonTracker solo necesita un objeto con '.activo', '.generar_descripcion()'
y '.clasificar()', asi que ClaudeReID es compatible con GeminiReID/GroqReID.

A diferencia de Gemini/Groq, ac forzamos el JSON con output_config.format
(json_schema) en vez de pedirlo por prompt -- la API garantiza que la
respuesta cumple el esquema exacto, asi que _parsear_json/_reparar_json_
truncado quedan solo como red de seguridad ante una respuesta cortada por
max_tokens, no como el camino principal.

La logica comun a los tres proveedores (rate limiting, descripcion, clasificacion, parseo) esta en comun.py."""
import base64
import json
import time
from typing import Optional

import cv2
import numpy as np

try:
    import anthropic
except ImportError:
    anthropic = None

from deteccion.reid.comun import (  # noqa: F401 -- se re-exportan: los usan persistencia.py y los tests
    CAMPOS_DESCRIPTOR, CAMPOS_OBLIGATORIOS, CAMPOS_OBLIGATORIOS_EMPLEADO, ReIDNube, _comparar_descriptores,
    _obligatorios_coinciden, _parsear_json, _reparar_json_truncado, _valor_visible, _valores_coinciden,
)

DESCRIPTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "color_ropa_superior": {"type": "string"},
        "color_ropa_inferior": {"type": "string"},
        "complexion": {"type": "string"},
        "cabello": {"type": "string"},
        "accesorios": {"type": "string"},
    },
    "required": ["color_ropa_superior", "color_ropa_inferior", "complexion", "cabello", "accesorios"],
    "additionalProperties": False,
}

# A diferencia de Gemini/Groq, el formato JSON lo fuerza la API (DESCRIPTOR_SCHEMA): el prompt no lo pide.
PROMPT_CLAUDE = (
    "Actuas como un sistema de Re-Identificacion de personas (Person Re-ID) para "
    "tracking multi-camara en un local comercial, SIN reconocimiento facial (esta "
    "prohibido por privacidad). El objetivo NO es describir la moda de la persona, "
    "sino extraer caracteristicas visuales ESTABLES que permitan reconocerla mas "
    "adelante si sale de cuadro, queda oculta detras de otra persona o gondola, o "
    "reaparece en otra camara minutos despues. Otra parte del sistema va a comparar "
    "este JSON contra descripciones generadas en otros momentos de la MISMA persona, "
    "asi que los valores tienen que ser SIMPLES y GENERALES, no un detalle exacto que "
    "probablemente cambie entre una descripcion y otra.\n"
    "Completa estos campos:\n"
    "- color_ropa_superior / color_ropa_inferior: SOLO el color predominante y basico "
    "('azul', 'negro', 'rojo', 'blanco', 'gris', 'verde', etc.), sin matices ni tonos "
    "especificos (NO 'azul marino con reflejos claros', SI 'azul'). Unicamente si la "
    "prenda combina dos colores bien diferenciados en partes similares, indica ambos "
    "separados por '/' (ej. 'rojo/negro').\n"
    "- complexion: delgada, media o robusta.\n"
    "- cabello: color y largo aproximado, en pocas palabras (ej. 'corto oscuro', "
    "'largo claro', 'calvo').\n"
    "- accesorios: mochila, cartera, gorra, lentes, ninguno, etc. (el mas notorio).\n"
    "Si algun campo no se puede determinar desde la imagen, usa 'no visible'. "
    "No inventes datos."
)


class ClaudeReID(ReIDNube):
    """Encapsula el rate limiter y las llamadas a la API de Claude (Anthropic
    Messages API, entrada de imagen + salida JSON forzada por esquema). Si no
    esta activo (dependencias faltantes, sin API keys, o desactivado por
    config), todos los metodos son no-ops que devuelven None -- misma
    semantica que GeminiReID/GroqReID."""

    ETIQUETA = "Claude"
    MSG_SIN_DEPENDENCIAS = "Paquete 'anthropic' no instalado. ReID en la nube desactivado."
    PROMPT = PROMPT_CLAUDE
    CROP_ALTO_MINIMO = 384  # px de alto minimo del crop enviado (ver _crop_a_base64)

    def __init__(
        self,
        usar_claude_reid: bool,
        has_claude: bool,
        api_keys: list,
        model: str,
        min_intervalo_seg: float,
        rafaga_umbral: int,
        pausa_rafaga_seg: float,
        ventana_rafaga_seg: float,
        coincidencias_minimas: int = 4,
        umbral_mismo_momento_seg: float = 90.0,
    ) -> None:
        super().__init__(usar_claude_reid, has_claude, api_keys, model, min_intervalo_seg, rafaga_umbral,
                         pausa_rafaga_seg, ventana_rafaga_seg, coincidencias_minimas, umbral_mismo_momento_seg)

    # ── Llamadas a la API ───────────────────────────────────────────────────────
    def _crop_a_base64(self, crop_bgr: np.ndarray) -> Optional[str]:
        try:
            # Con streams de baja resolucion (RTSP 640x360) una persona ocupa
            # ~40x100 px: se agranda a una altura minima antes de enviarla. No
            # agrega detalle real, pero la imagen chica produce muy pocos
            # tokens de vision y el modelo describe peor la ropa; el realce
            # leve evita que el agrandado quede empastado. Crops grandes
            # (videos 1920x1080) no se tocan.
            alto, ancho = crop_bgr.shape[:2]
            if 0 < alto < self.CROP_ALTO_MINIMO:
                escala = self.CROP_ALTO_MINIMO / alto
                crop_bgr = cv2.resize(
                    crop_bgr, (max(1, round(ancho * escala)), self.CROP_ALTO_MINIMO),
                    interpolation=cv2.INTER_CUBIC,
                )
                suavizado = cv2.GaussianBlur(crop_bgr, (0, 0), 1.5)
                crop_bgr = cv2.addWeighted(crop_bgr, 1.4, suavizado, -0.4, 0)
            ok, buf = cv2.imencode(".jpg", crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ok:
                return None
            return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception as error:
            print(f"[Claude] No se pudo preparar el crop: {error}")
            return None

    def _generar_contenido(self, imagen_b64: str, prompt: str) -> Optional[str]:
        """Prueba cada API key en orden; si una se queda sin cupo (429) o
        Anthropic tiene un problema transitorio (5xx), pasa a la siguiente en
        silencio. Fuerza la salida a cumplir DESCRIPTOR_SCHEMA via
        output_config.format (json_schema) -- no dependemos de que el prompt
        "pida bien" el JSON. thinking queda deshabilitado (efimero para esta
        tarea de clasificacion corta, no vale el costo/latencia extra) con
        effort bajo, que es el combo permitido en Claude Opus 5 (thinking
        deshabilitado solo se acepta con effort <= high). Devuelve el texto
        crudo del bloque de texto de la respuesta, o None si fallan todas las
        keys, hay un error de cliente no recuperable, o la respuesta fue
        rechazada por los filtros de seguridad."""
        ultimo_error: Optional[Exception] = None
        for api_key in self.api_keys:
            try:
                client = anthropic.Anthropic(api_key=api_key)
                kwargs = {
                    "model": self.model,
                    "max_tokens": 512,
                    "output_config": {"format": {"type": "json_schema", "schema": DESCRIPTOR_SCHEMA}},
                }
                if "haiku" in self.model:
                    # Igual que Gemini/Groq (temperature=0): reduce la variabilidad
                    # entre llamadas para la misma persona. Los modelos Opus/Sonnet/
                    # Fable de la familia actual RECHAZAN temperature (400) -- ahi
                    # el control de determinismo es otro (thinking/effort, abajo).
                    kwargs["temperature"] = 0
                else:
                    # Haiku 4.5 no acepta 'thinking'/'effort' configurables (400) --
                    # solo los modelos Opus/Sonnet/Fable de la familia actual. Sin
                    # thinking configurado, Haiku ya corre sin pensar por default.
                    kwargs["thinking"] = {"type": "disabled"}
                    kwargs["output_config"]["effort"] = "low"
                response = client.messages.create(
                    **kwargs,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": imagen_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }],
                )
                if response.stop_reason == "refusal":
                    print("[Claude] Respuesta rechazada por los filtros de seguridad, se omite.")
                    return None
                print(f"[Claude] Llamada a la API OK ({self.model}) -- "
                      f"{response.usage.input_tokens} tokens in / {response.usage.output_tokens} out")
                texto = next((b.text for b in response.content if b.type == "text"), None)
                if texto is None:
                    print(f"[Claude] Respuesta sin bloque de texto (stop_reason={response.stop_reason}).")
                    return None
                return texto
            except anthropic.RateLimitError as error:
                ultimo_error = error
                continue
            except anthropic.APIConnectionError as error:
                # Error transitorio de red -- se prueba con la siguiente key
                # tras una pausa breve, en vez de abandonar la llamada de una.
                ultimo_error = error
                time.sleep(2)
                continue
            except anthropic.APIStatusError as error:
                if error.status_code >= 500:
                    ultimo_error = error
                    time.sleep(2)
                    continue
                print(f"[Claude] Error de cliente en la llamada: {error}")
                return None
            except Exception as error:
                print(f"[Claude] Error inesperado en la llamada: {error}")
                return None

        print(f"[Claude] Todas las API keys fallaron (cupo agotado o error del servidor), "
              f"se omite la llamada. Ultimo error: {ultimo_error}")
        return None

    def _preparar_imagen(self, crop_bgr: np.ndarray):
        return self._crop_a_base64(crop_bgr)

    def _pedir_descripcion(self, imagen_b64: str, prompt: str) -> Optional[str]:
        return self._generar_contenido(imagen_b64, prompt)

    def _antes_de_pedir(self) -> None:
        print("[Claude] Enviando crop de persona para describirla...")

    def _descripcion_obtenida(self, descripcion: dict) -> None:
        print(f"[Claude] Descripcion: {json.dumps(descripcion, ensure_ascii=False)}")

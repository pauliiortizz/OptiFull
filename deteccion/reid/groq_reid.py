"""Cliente de Groq para el Re-ID en la nube: misma funcion que gemini_reid.py
(describe personas una unica vez y clasifica IDs nuevos contra candidatos
perdidos, con rate limiting local), pero contra modelos de vision alojados en
Groq en vez de Gemini. Pensado como alternativa intercambiable -- PersonTracker
solo necesita un objeto con '.activo', '.generar_descripcion()' y
'.clasificar()', asi que GeminiReID y GroqReID son compatibles entre si.

La logica comun a los tres proveedores (rate limiting, descripcion, clasificacion, parseo) esta en comun.py."""
import base64
import time
from typing import Optional

import cv2
import numpy as np

try:
    from groq import Groq
    from groq import APIStatusError, APIConnectionError
except ImportError:
    Groq = APIStatusError = APIConnectionError = None

from deteccion.reid.comun import (  # noqa: F401 -- se re-exportan: los usan persistencia.py y los tests
    CAMPOS_DESCRIPTOR, CAMPOS_OBLIGATORIOS, CAMPOS_OBLIGATORIOS_EMPLEADO, ReIDNube, _comparar_descriptores,
    _obligatorios_coinciden, _parsear_json, _reparar_json_truncado, _valor_visible, _valores_coinciden,
)


class GroqReID(ReIDNube):
    """Encapsula el rate limiter y las llamadas a la API de Groq (modelo de
    vision con salida JSON). Si no esta activo (dependencias faltantes, sin
    API keys, o desactivado por config), todos los metodos son no-ops que
    devuelven None -- misma semantica que GeminiReID."""

    ETIQUETA = "Groq"
    MSG_SIN_DEPENDENCIAS = "Dependencias no instaladas (paquete 'groq'). ReID en la nube desactivado."

    def __init__(
        self,
        usar_groq_reid: bool,
        has_groq: bool,
        api_keys: list,
        model: str,
        min_intervalo_seg: float,
        rafaga_umbral: int,
        pausa_rafaga_seg: float,
        ventana_rafaga_seg: float,
        coincidencias_minimas: int = 4,
        umbral_mismo_momento_seg: float = 90.0,
    ) -> None:
        super().__init__(usar_groq_reid, has_groq, api_keys, model, min_intervalo_seg, rafaga_umbral,
                         pausa_rafaga_seg, ventana_rafaga_seg, coincidencias_minimas, umbral_mismo_momento_seg)

    # ── Llamadas a la API ───────────────────────────────────────────────────────
    def _crop_a_base64(self, crop_bgr: np.ndarray) -> Optional[str]:
        try:
            ok, buf = cv2.imencode(".jpg", crop_bgr)
            if not ok:
                return None
            return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception as error:
            print(f"[Groq] No se pudo preparar el crop: {error}")
            return None

    def _generar_contenido(self, imagen_b64: str, prompt: str, json_response: bool = False) -> Optional[str]:
        """Prueba cada API key en orden; si una se queda sin cupo (429) o Groq
        tiene un problema transitorio (5xx), pasa a la siguiente en silencio.
        Devuelve el texto crudo de la respuesta, o None si fallan todas las
        keys o hay un error de cliente no recuperable."""
        ultimo_error: Optional[Exception] = None
        for api_key in self.api_keys:
            try:
                client = Groq(api_key=api_key)
                kwargs = {"response_format": {"type": "json_object"}} if json_response else {}
                response = client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/jpeg;base64,{imagen_b64}"
                            }},
                        ],
                    }],
                    **kwargs,
                )
                return response.choices[0].message.content
            except APIStatusError as error:
                status = getattr(error, "status_code", None)
                if status == 429 or (isinstance(status, int) and status >= 500):
                    ultimo_error = error
                    continue
                print(f"[Groq] Error de cliente en la llamada: {error}")
                return None
            except APIConnectionError as error:
                # Error transitorio de red -- se prueba con la siguiente key
                # tras una pausa breve, en vez de abandonar la llamada de una.
                ultimo_error = error
                time.sleep(2)
                continue
            except Exception as error:
                print(f"[Groq] Error inesperado en la llamada: {error}")
                return None

        print(f"[Groq] Todas las API keys fallaron (cupo agotado o error del servidor), "
              f"se omite la llamada. Ultimo error: {ultimo_error}")
        return None

    def _preparar_imagen(self, crop_bgr: np.ndarray):
        return self._crop_a_base64(crop_bgr)

    def _pedir_descripcion(self, imagen_b64: str, prompt: str) -> Optional[str]:
        return self._generar_contenido(imagen_b64, prompt, json_response=True)

"""Cliente de Gemini para el Re-ID en la nube: describe personas una unica vez
y clasifica IDs nuevos contra candidatos perdidos, con rate limiting local.

La logica comun a los tres proveedores (rate limiting, descripcion, clasificacion, parseo) esta en comun.py."""
import time
from typing import Optional

import cv2
import numpy as np

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError, ServerError
    from PIL import Image
except ImportError:
    genai = types = ClientError = ServerError = Image = None

from deteccion.reid.comun import (  # noqa: F401 -- se re-exportan: los usan persistencia.py y los tests
    CAMPOS_DESCRIPTOR, CAMPOS_OBLIGATORIOS, CAMPOS_OBLIGATORIOS_EMPLEADO, ReIDNube, _comparar_descriptores,
    _obligatorios_coinciden, _parsear_json, _reparar_json_truncado, _valor_visible, _valores_coinciden,
)


class GeminiReID(ReIDNube):
    """Encapsula el rate limiter y las llamadas a la API de Gemini.
    Si no esta activo (dependencias faltantes, sin API keys, o desactivado por
    config), todos los metodos son no-ops que devuelven None."""

    ETIQUETA = "Gemini"
    MSG_SIN_DEPENDENCIAS = "Dependencias no instaladas (google-genai/pillow). ReID en la nube desactivado."

    def __init__(
        self,
        usar_gemini_reid: bool,
        has_gemini: bool,
        api_keys: list,
        model: str,
        min_intervalo_seg: float,
        rafaga_umbral: int,
        pausa_rafaga_seg: float,
        ventana_rafaga_seg: float,
        coincidencias_minimas: int = 3,
        umbral_mismo_momento_seg: float = 90.0,
    ) -> None:
        super().__init__(usar_gemini_reid, has_gemini, api_keys, model, min_intervalo_seg, rafaga_umbral,
                         pausa_rafaga_seg, ventana_rafaga_seg, coincidencias_minimas, umbral_mismo_momento_seg)

    # ── Llamadas a la API ───────────────────────────────────────────────────────
    def _crop_a_imagen(self, crop_bgr: np.ndarray) -> Optional["Image.Image"]:
        try:
            return Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
        except Exception as error:
            print(f"[Gemini] No se pudo preparar el crop: {error}")
            return None

    def _generar_contenido(self, imagen: "Image.Image", prompt: str, json_response: bool = False) -> Optional[str]:
        """Prueba cada API key en orden; si una se queda sin cupo (429) o Google
        tiene un problema transitorio (5xx, ej. sobrecarga), pasa a la siguiente
        en silencio (sin loggear cada fallo individual). Devuelve el texto crudo
        de la respuesta, o None si fallan todas las keys o hay un error de
        cliente no recuperable."""
        config = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json" if json_response else None,
        )
        ultimo_error: Optional[Exception] = None
        for api_key in self.api_keys:
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=self.model, contents=[imagen, prompt], config=config,
                )
                return response.text
            except ClientError as error:
                if getattr(error, "code", None) == 429:
                    ultimo_error = error
                    continue
                print(f"[Gemini] Error de cliente en la llamada: {error}")
                return None
            except ServerError as error:
                # Error transitorio del lado de Google (ej. 503 sobrecarga) --
                # se prueba con la siguiente key tras una pausa breve, en vez
                # de abandonar la llamada de una.
                ultimo_error = error
                time.sleep(2)
                continue
            except Exception as error:
                print(f"[Gemini] Error inesperado en la llamada: {error}")
                return None

        print(f"[Gemini] Todas las API keys fallaron (cupo agotado o error del servidor), "
              f"se omite la llamada. Ultimo error: {ultimo_error}")
        return None

    def _preparar_imagen(self, crop_bgr: np.ndarray):
        return self._crop_a_imagen(crop_bgr)

    def _pedir_descripcion(self, imagen, prompt: str) -> Optional[str]:
        return self._generar_contenido(imagen, prompt, json_response=True)

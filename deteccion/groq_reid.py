"""Cliente de Groq para el Re-ID en la nube: misma funcion que gemini_reid.py
(describe personas una unica vez y clasifica IDs nuevos contra candidatos
perdidos, con rate limiting local), pero contra modelos de vision alojados en
Groq en vez de Gemini. Pensado como alternativa intercambiable -- PersonTracker
solo necesita un objeto con '.activo', '.generar_descripcion()' y
'.clasificar()', asi que GeminiReID y GroqReID son compatibles entre si."""
import time
import json
import base64
from typing import Optional

import cv2
import numpy as np

try:
    from groq import Groq
    from groq import APIStatusError, APIConnectionError
except ImportError:
    Groq = APIStatusError = APIConnectionError = None

CAMPOS_DESCRIPTOR   = ["color_ropa_superior", "color_ropa_inferior", "complexion", "cabello", "accesorios"]
CAMPOS_OBLIGATORIOS = ["color_ropa_superior", "color_ropa_inferior"]


def _parsear_json(texto: str) -> dict:
    """Parsea el primer objeto JSON valido de la respuesta, ignorando
    cualquier texto extra que el modelo agregue despues -- json.loads() comun
    falla con 'Extra data' en esos casos, raw_decode() no."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    obj, _ = json.JSONDecoder().raw_decode(texto)
    return obj


def _comparar_descriptores(a: dict, b: dict) -> int:
    """Cuenta cuantos de los campos del descriptor coinciden (texto exacto,
    sin mayusculas/espacios) entre dos descripciones estructuradas."""
    coincidencias = 0
    for campo in CAMPOS_DESCRIPTOR:
        v1 = str(a.get(campo, "")).strip().lower()
        v2 = str(b.get(campo, "")).strip().lower()
        if v1 and v2 and v1 == v2:
            coincidencias += 1
    return coincidencias


def _obligatorios_coinciden(a: dict, b: dict) -> bool:
    """Los colores de ropa superior/inferior son eliminatorios: si alguno no
    coincide EXACTO (o no esta visible en alguna de las dos), el candidato
    se descarta sin importar cuantos otros campos coincidan."""
    for campo in CAMPOS_OBLIGATORIOS:
        v1 = str(a.get(campo, "")).strip().lower()
        v2 = str(b.get(campo, "")).strip().lower()
        if not v1 or not v2 or v1 != v2:
            return False
    return True


class GroqReID:
    """Encapsula el rate limiter y las llamadas a la API de Groq (modelo de
    vision con salida JSON). Si no esta activo (dependencias faltantes, sin
    API keys, o desactivado por config), todos los metodos son no-ops que
    devuelven None -- misma semantica que GeminiReID."""

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
    ) -> None:
        self.api_keys              = api_keys
        self.model                 = model
        self.min_intervalo_seg     = min_intervalo_seg
        self.rafaga_umbral         = rafaga_umbral
        self.pausa_rafaga_seg      = pausa_rafaga_seg
        self.ventana_rafaga_seg    = ventana_rafaga_seg
        self.coincidencias_minimas = coincidencias_minimas

        self.activo = bool(usar_groq_reid and has_groq and api_keys)
        if usar_groq_reid and not has_groq:
            print("[Groq] Dependencias no instaladas (paquete 'groq'). ReID en la nube desactivado.")
        elif usar_groq_reid and not api_keys:
            print("[Groq] No hay API keys configuradas (revisa .env). ReID en la nube desactivado.")

        self._ultima_llamada: float = 0.0
        self._eventos_recientes: list = []

    # ── Rate limiter local (gestion de rafagas) ────────────────────────────────
    def _registrar_evento_y_medir_rafaga(self) -> int:
        """Registra la ocurrencia de un evento 'ID nuevo sospechoso' y devuelve
        cuantos eventos hubo dentro de la ventana de rafaga (ej. un grupo entrando junto)."""
        ahora = time.monotonic()
        self._eventos_recientes.append(ahora)
        corte = ahora - self.ventana_rafaga_seg
        while self._eventos_recientes and self._eventos_recientes[0] < corte:
            self._eventos_recientes.pop(0)
        return len(self._eventos_recientes)

    def esperar_turno(self) -> None:
        """Aplica un intervalo minimo entre llamadas a Groq y, si se detecta
        una rafaga de eventos (varios IDs nuevos casi juntos), agrega una pausa
        extra para no exceder el rate limit del free tier sin colgar el procesamiento."""
        eventos_en_rafaga = self._registrar_evento_y_medir_rafaga()

        intervalo_min = self.min_intervalo_seg
        if eventos_en_rafaga >= self.rafaga_umbral:
            intervalo_min += self.pausa_rafaga_seg
            print(f"[Groq] Rafaga detectada ({eventos_en_rafaga} eventos en "
                  f"{self.ventana_rafaga_seg:.0f}s) -> pausa extra de {self.pausa_rafaga_seg:.0f}s")

        transcurrido = time.monotonic() - self._ultima_llamada
        if transcurrido < intervalo_min:
            time.sleep(intervalo_min - transcurrido)
        self._ultima_llamada = time.monotonic()

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

    def generar_descripcion(self, crop_bgr: np.ndarray) -> Optional[dict]:
        """Genera UNA UNICA VEZ por cliente un descriptor visual ESTRUCTURADO
        (no texto libre) pensado para Re-Identificacion: un puñado de rasgos
        estables (ropa, complexion, cabello, accesorios) que se puedan comparar
        despues, no una descripcion de moda. Se usa cuando la persona sale de
        cuadro, queda oculta, o reaparece en otra camara -- nunca reconocimiento
        facial."""
        if not self.activo:
            return None

        imagen_b64 = self._crop_a_base64(crop_bgr)
        if imagen_b64 is None:
            return None

        self.esperar_turno()
        prompt = (
            "Actuas como un sistema de Re-Identificacion de personas (Person Re-ID) para "
            "tracking multi-camara en un local comercial, SIN reconocimiento facial (esta "
            "prohibido por privacidad). El objetivo NO es describir la moda de la persona, "
            "sino extraer caracteristicas visuales ESTABLES que permitan reconocerla mas "
            "adelante si sale de cuadro, queda oculta detras de otra persona o gondola, o "
            "reaparece en otra camara minutos despues. Otra parte del sistema va a comparar "
            "este JSON contra descripciones generadas en otros momentos de la MISMA persona, "
            "asi que los valores tienen que ser SIMPLES y GENERALES, no un detalle exacto que "
            "probablemente cambie entre una descripcion y otra.\n"
            "Analiza la imagen y devolve UNICAMENTE un JSON (sin texto adicional) con estos "
            "campos:\n"
            '{"color_ropa_superior": "...", "color_ropa_inferior": "...", '
            '"complexion": "...", "cabello": "...", "accesorios": "..."}\n'
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
            "No inventes datos ni agregues explicaciones fuera del JSON."
        )
        texto = self._generar_contenido(imagen_b64, prompt, json_response=True)
        if texto is None:
            return None
        try:
            return _parsear_json(texto)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            print(f"[Groq] Respuesta no parseable al generar descripcion: {error}")
            return None

    def clasificar(self, crop_bgr: np.ndarray, candidatos: list) -> Optional[int]:
        """Genera un descriptor NUEVO e independiente para esta aparicion (con
        generar_descripcion) y lo compara campo a campo contra el descriptor ya
        guardado de cada candidato (clientes recientemente perdidos). El modelo
        no siempre va a describir a la misma persona con las mismas palabras
        exactas cada vez -- por eso no se pide una probabilidad, se cuenta
        cuantos de los 5 campos coinciden. color_ropa_superior y
        color_ropa_inferior son ELIMINATORIOS (tienen que coincidir exacto si o
        si); entre los candidatos que pasan ese filtro, se acepta el de mas
        coincidencias totales, siempre que llegue al minimo configurado
        (coincidencias_minimas). Devuelve el id del candidato aceptado, o None
        si no hay ninguno lo bastante parecido, si la generacion falla, o si
        Groq esta desactivado.
        NO valida el id contra la lista de tracks perdidos vigentes -- eso es
        responsabilidad de quien llama (PersonTracker), que es quien conoce el
        estado real de lost_tracks."""
        if not self.activo or not candidatos:
            return None

        nueva_descripcion = self.generar_descripcion(crop_bgr)
        if not nueva_descripcion:
            return None

        mejor_sid = None
        mejor_coincidencias = 0
        for c in candidatos:
            descripcion_c = c.get("descripcion") or {}
            if not _obligatorios_coinciden(nueva_descripcion, descripcion_c):
                continue
            coincidencias = _comparar_descriptores(nueva_descripcion, descripcion_c)
            if coincidencias > mejor_coincidencias:
                mejor_coincidencias = coincidencias
                mejor_sid = c["sid"]

        if mejor_sid is None:
            print("[Groq] Ningun candidato con color de ropa superior/inferior "
                  "exactamente igual -> descartado")
            return None
        if mejor_coincidencias < self.coincidencias_minimas:
            print(f"[Groq] Mejor candidato {mejor_sid} con solo {mejor_coincidencias}/"
                  f"{len(CAMPOS_DESCRIPTOR)} caracteristicas coincidentes "
                  f"(< {self.coincidencias_minimas} minimo) -> descartado")
            return None

        print(f"[Groq] Candidato {mejor_sid} con {mejor_coincidencias}/{len(CAMPOS_DESCRIPTOR)} "
              f"caracteristicas coincidentes -> aceptado")
        return mejor_sid

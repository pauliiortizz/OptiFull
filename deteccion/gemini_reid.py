"""Cliente de Gemini para el Re-ID en la nube: describe personas una unica vez
y clasifica IDs nuevos contra candidatos perdidos, con rate limiting local."""
import time
import json
import re
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

CAMPOS_DESCRIPTOR = ["color_ropa_superior", "color_ropa_inferior", "complexion", "cabello", "accesorios"]


_COMILLAS_TIPOGRAFICAS = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "′": "'",
})


def _reparar_json_truncado(texto: str) -> str:
    """Intenta cerrar un JSON que quedo TRUNCADO -- ej. la respuesta de
    Gemini se corta antes de la '}' final (pasa mas de lo que uno esperaria,
    incluso con response_mime_type='application/json'). Cuenta comillas
    dobles sin escapar para saber si el corte quedo a mitad de un string (en
    ese caso la cierra primero) y despues agrega tantas '}' como '{' hayan
    quedado sin su cierre correspondiente."""
    t = texto.rstrip()
    if len(re.findall(r'(?<!\\)"', t)) % 2 == 1:
        t += '"'
    faltantes = t.count("{") - t.count("}")
    t += "}" * max(0, faltantes)
    return t


def _parsear_json(texto: str) -> dict:
    """Parsea el primer objeto JSON valido de la respuesta, ignorando
    cualquier texto extra que Gemini agregue despues (a veces pasa incluso
    pidiendo response_mime_type='application/json') -- json.loads() comun
    falla con 'Extra data' en esos casos, raw_decode() no. Tambien normaliza
    comillas tipograficas ("curly quotes") a rectas -- Gemini a veces las usa
    dentro del VALOR de un campo (ej. describiendo un logo o texto en la
    ropa) y, si son dobles, cortan el string JSON antes de tiempo. Si aun asi
    falla el parseo, es probable que la respuesta haya quedado TRUNCADA (se
    corto antes de la llave de cierre) -- como Gemini corre con temperature=0,
    reintentar la MISMA llamada devuelve casi siempre el mismo corte, asi que
    reparar localmente (en vez de reintentar contra la API) es lo que
    realmente rescata la descripcion."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    texto = texto.translate(_COMILLAS_TIPOGRAFICAS)
    try:
        obj, _ = json.JSONDecoder().raw_decode(texto)
        return obj
    except json.JSONDecodeError:
        obj, _ = json.JSONDecoder().raw_decode(_reparar_json_truncado(texto))
        return obj


CAMPOS_OBLIGATORIOS = ["color_ropa_superior", "color_ropa_inferior"]


def _valor_visible(d: dict, campo: str) -> Optional[str]:
    """Valor normalizado de un campo, o None si esta vacio o si Gemini lo
    marco como 'no visible' -- ej. el mostrador de caja tapa la ropa inferior
    desde el angulo de una camara pero no de otra. Un campo 'no visible' no
    es evidencia de nada (ni a favor ni en contra de que sea la misma
    persona), asi que se excluye de la comparacion en vez de tratarlo como un
    valor mas."""
    v = str(d.get(campo, "")).strip().lower()
    return v if v and v != "no visible" else None


def _comparar_descriptores(a: dict, b: dict) -> tuple:
    """Cuenta cuantos de los campos COMPARABLES (visibles en ambos lados)
    coinciden. Devuelve (coincidencias, comparables) -- 'comparables' importa
    tanto como 'coincidencias': una persona con la mitad del cuerpo tapado en
    una camara va a tener menos campos comparables que una vista de cuerpo
    entero, y no hay que penalizarla por eso."""
    coincidencias = comparables = 0
    for campo in CAMPOS_DESCRIPTOR:
        v1, v2 = _valor_visible(a, campo), _valor_visible(b, campo)
        if v1 is None or v2 is None:
            continue
        comparables += 1
        if v1 == v2:
            coincidencias += 1
    return coincidencias, comparables


def _obligatorios_coinciden(a: dict, b: dict) -> bool:
    """Los colores de ropa superior/inferior son el criterio mas fuerte para
    descartar un candidato, PERO solo cuando son visibles en ambos lados: si
    uno de los dos tiene ese campo oculto (ej. la caja tapa la ropa inferior
    de un empleado en una camara pero no en otra), no se puede exigir que
    coincida -- no descarta al candidato por eso, la decision se apoya en el
    resto de los campos visibles."""
    for campo in CAMPOS_OBLIGATORIOS:
        v1, v2 = _valor_visible(a, campo), _valor_visible(b, campo)
        if v1 is None or v2 is None:
            continue
        if v1 != v2:
            return False
    return True


class GeminiReID:
    """Encapsula el rate limiter y las llamadas a la API de Gemini.
    Si no esta activo (dependencias faltantes, sin API keys, o desactivado por
    config), todos los metodos son no-ops que devuelven None."""

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
    ) -> None:
        self.api_keys              = api_keys
        self.model                 = model
        self.min_intervalo_seg     = min_intervalo_seg
        self.rafaga_umbral         = rafaga_umbral
        self.pausa_rafaga_seg      = pausa_rafaga_seg
        self.ventana_rafaga_seg    = ventana_rafaga_seg
        self.coincidencias_minimas = coincidencias_minimas

        self.activo = bool(usar_gemini_reid and has_gemini and api_keys)
        if usar_gemini_reid and not has_gemini:
            print("[Gemini] Dependencias no instaladas (google-genai/pillow). ReID en la nube desactivado.")
        elif usar_gemini_reid and not api_keys:
            print("[Gemini] No hay API keys configuradas (revisa .env). ReID en la nube desactivado.")

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
        """Aplica un intervalo minimo entre llamadas a Gemini y, si se detecta
        una rafaga de eventos (varios IDs nuevos casi juntos), agrega una pausa
        extra para no exceder el rate limit del free tier sin colgar el procesamiento."""
        eventos_en_rafaga = self._registrar_evento_y_medir_rafaga()

        intervalo_min = self.min_intervalo_seg
        if eventos_en_rafaga >= self.rafaga_umbral:
            intervalo_min += self.pausa_rafaga_seg
            print(f"[Gemini] Rafaga detectada ({eventos_en_rafaga} eventos en "
                  f"{self.ventana_rafaga_seg:.0f}s) -> pausa extra de {self.pausa_rafaga_seg:.0f}s")

        transcurrido = time.monotonic() - self._ultima_llamada
        if transcurrido < intervalo_min:
            time.sleep(intervalo_min - transcurrido)
        self._ultima_llamada = time.monotonic()

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

    def generar_descripcion(self, crop_bgr: np.ndarray) -> Optional[dict]:
        """Genera UNA UNICA VEZ por cliente un descriptor visual ESTRUCTURADO
        (no texto libre) pensado para Re-Identificacion: un puñado de rasgos
        estables (ropa, complexion, cabello, accesorios) que se puedan comparar
        despues, no una descripcion de moda. Se usa cuando la persona sale de
        cuadro, queda oculta, o reaparece en otra camara -- nunca reconocimiento
        facial. Si Gemini devuelve una respuesta no parseable como JSON (falla
        ocasional del modelo, no del codigo), reintenta UNA vez -- perder la
        descripcion para siempre por un glitch de formato deja a esa persona
        sin candidatos para el Re-ID entre camaras."""
        if not self.activo:
            return None

        imagen = self._crop_a_imagen(crop_bgr)
        if imagen is None:
            return None

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
        for intento in (1, 2):
            self.esperar_turno()
            texto = self._generar_contenido(imagen, prompt, json_response=True)
            if texto is None:
                return None  # fallo de la llamada en si (cupo agotado, etc.) -- reintentar no ayuda
            try:
                return _parsear_json(texto)
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                print(f"[Gemini] Respuesta no parseable al generar descripcion "
                      f"(intento {intento}/2): {error}")
                print(f"[Gemini] Texto crudo recibido: {texto!r}")
        return None

    def clasificar(self, crop_bgr: np.ndarray, candidatos: list) -> Optional[int]:
        """Genera un descriptor NUEVO e independiente para esta aparicion (con
        generar_descripcion) y lo compara campo a campo contra el descriptor ya
        guardado de cada candidato (clientes recientemente perdidos). Gemini no
        siempre va a describir a la misma persona con las mismas palabras exactas
        cada vez -- por eso no se pide una probabilidad, se cuenta cuantos de los
        campos VISIBLES EN AMBOS LADOS coinciden (ver _comparar_descriptores: un
        campo 'no visible' -- ej. la ropa inferior tapada por el mostrador de
        caja desde el angulo de una camara -- no cuenta ni a favor ni en contra).
        color_ropa_superior y color_ropa_inferior son ELIMINATORIOS solo cuando
        son visibles en ambos lados; entre los candidatos que pasan ese filtro,
        se acepta el de mas coincidencias totales, siempre que llegue al minimo
        configurado (coincidencias_minimas), escalado hacia abajo si hay menos
        campos comparables que ese minimo -- una persona vista de la cintura
        para arriba no puede alcanzar el mismo piso que una vista de cuerpo
        entero, y no hay que descartarla solo por eso. Devuelve el id del
        candidato aceptado, o None si no hay ninguno lo bastante parecido, si
        la generacion falla, o si Gemini esta desactivado.
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
        mejor_comparables = 0
        for c in candidatos:
            descripcion_c = c.get("descripcion") or {}
            if not _obligatorios_coinciden(nueva_descripcion, descripcion_c):
                continue
            coincidencias, comparables = _comparar_descriptores(nueva_descripcion, descripcion_c)
            if comparables == 0:
                continue  # sin ningun campo visible en comun, no hay evidencia para comparar
            if coincidencias > mejor_coincidencias:
                mejor_coincidencias = coincidencias
                mejor_comparables   = comparables
                mejor_sid = c["sid"]

        if mejor_sid is None:
            print("[Gemini] Ningun candidato con color de ropa superior/inferior "
                  "coincidente (donde visible) y evidencia comparable -> descartado")
            return None

        minimo_efectivo = min(self.coincidencias_minimas, mejor_comparables)
        if mejor_coincidencias < minimo_efectivo:
            print(f"[Gemini] Mejor candidato {mejor_sid} con solo {mejor_coincidencias}/"
                  f"{mejor_comparables} caracteristicas comparables coincidentes "
                  f"(< {minimo_efectivo} minimo) -> descartado")
            return None

        print(f"[Gemini] Candidato {mejor_sid} con {mejor_coincidencias}/{mejor_comparables} "
              f"caracteristicas comparables coincidentes -> aceptado")
        return mejor_sid

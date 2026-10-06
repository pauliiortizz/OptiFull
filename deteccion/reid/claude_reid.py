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
max_tokens, no como el camino principal."""
import time
import json
import re
import base64
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

try:
    import anthropic
except ImportError:
    anthropic = None

CAMPOS_DESCRIPTOR   = ["color_ropa_superior", "color_ropa_inferior", "complexion", "cabello", "accesorios"]
CAMPOS_OBLIGATORIOS          = ["color_ropa_superior"]
CAMPOS_OBLIGATORIOS_EMPLEADO = ["color_ropa_superior", "color_ropa_inferior"]

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


_COMILLAS_TIPOGRAFICAS = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "′": "'",
})


def _reparar_json_truncado(texto: str) -> str:
    """Intenta cerrar un JSON que quedo TRUNCADO -- ej. la respuesta de Claude
    se corta antes de la '}' final por haber llegado a max_tokens. Cuenta
    comillas dobles sin escapar para saber si el corte quedo a mitad de un
    string (en ese caso la cierra primero) y despues agrega tantas '}' como
    '{' hayan quedado sin su cierre correspondiente."""
    t = texto.rstrip()
    if len(re.findall(r'(?<!\\)"', t)) % 2 == 1:
        t += '"'
    faltantes = t.count("{") - t.count("}")
    t += "}" * max(0, faltantes)
    return t


def _parsear_json(texto: str) -> dict:
    """Parsea el primer objeto JSON valido de la respuesta. Con
    output_config.format esto casi siempre es un parseo directo, pero se
    mantiene el mismo repertorio de reparaciones que gemini_reid.py/
    groq_reid.py (comillas tipograficas, JSON truncado) como red de
    seguridad ante una respuesta cortada por max_tokens."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    texto = texto.translate(_COMILLAS_TIPOGRAFICAS)
    try:
        obj, _ = json.JSONDecoder().raw_decode(texto)
    except json.JSONDecodeError:
        obj, _ = json.JSONDecoder().raw_decode(_reparar_json_truncado(texto))
    if not isinstance(obj, dict):
        raise ValueError(f"Se esperaba un objeto JSON, se recibio {type(obj).__name__}")
    return obj


def _valor_visible(d: dict, campo: str) -> Optional[str]:
    """Valor normalizado de un campo, o None si esta vacio o si Claude lo
    marco como 'no visible' -- ej. el mostrador de caja tapa la ropa inferior
    desde el angulo de una camara pero no de otra. Un campo 'no visible' no
    es evidencia de nada (ni a favor ni en contra de que sea la misma
    persona), asi que se excluye de la comparacion en vez de tratarlo como un
    valor mas."""
    if not isinstance(d, dict):
        return None
    v = str(d.get(campo, "")).strip().lower()
    return v if v and v != "no visible" else None


def _valores_coinciden(v1: str, v2: str, campo: str) -> bool:
    """Igualdad exacta para la mayoria de los campos, PERO por color
    individual (no por string completo) para color_ropa_superior/inferior:
    Claude describe la MISMA prenda combinada de forma inconsistente entre
    angulos de camara distintos -- 'negro/azul' en una toma y 'azul/negro' en
    otra (mismo orden invertido), o 'gris' vs 'gris/azul' cuando un angulo
    deja ver un segundo color que el otro no. Comparar el string completo
    rechazaba estos casos como si fueran personas distintas; alcanza con que
    compartan AL MENOS un color."""
    if campo in ("color_ropa_superior", "color_ropa_inferior"):
        c1 = {c.strip() for c in v1.split("/") if c.strip()}
        c2 = {c.strip() for c in v2.split("/") if c.strip()}
        return bool(c1 & c2)
    return v1 == v2


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
        if _valores_coinciden(v1, v2, campo):
            coincidencias += 1
    return coincidencias, comparables


def _obligatorios_coinciden(a: dict, b: dict, estricto: bool = False) -> bool:
    """El color de ropa SUPERIOR es el criterio mas fuerte para descartar un
    candidato, PERO solo cuando es visible en ambos lados: si uno de los dos
    lo tiene oculto, no se puede exigir que coincida -- no descarta al
    candidato por eso, la decision se apoya en el resto de los campos
    visibles. El color de ropa inferior NO es obligatorio para comparar
    CLIENTES entre si (ahora cuenta como un campo mas dentro del minimo de
    coincidencias_minimas, igual que complexion/cabello/accesorios) --
    'estricto=True' lo vuelve a exigir junto al superior, uso reservado para
    matchear una aparicion contra un EMPLEADO ya conocido (el uniforme hace
    que ambos colores sean una señal mucho mas confiable ahi que para un
    cliente cualquiera)."""
    campos = CAMPOS_OBLIGATORIOS_EMPLEADO if estricto else CAMPOS_OBLIGATORIOS
    for campo in campos:
        v1, v2 = _valor_visible(a, campo), _valor_visible(b, campo)
        if v1 is None or v2 is None:
            continue
        if not _valores_coinciden(v1, v2, campo):
            return False
    return True


class ClaudeReID:
    """Encapsula el rate limiter y las llamadas a la API de Claude (Anthropic
    Messages API, entrada de imagen + salida JSON forzada por esquema). Si no
    esta activo (dependencias faltantes, sin API keys, o desactivado por
    config), todos los metodos son no-ops que devuelven None -- misma
    semantica que GeminiReID/GroqReID."""

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
        self.api_keys              = api_keys
        self.model                 = model
        self.min_intervalo_seg     = min_intervalo_seg
        self.rafaga_umbral         = rafaga_umbral
        self.pausa_rafaga_seg      = pausa_rafaga_seg
        self.ventana_rafaga_seg    = ventana_rafaga_seg
        self.coincidencias_minimas = coincidencias_minimas
        # Camaras del mismo grupo fisico miran el MISMO lugar desde angulos
        # distintos -- si dos personas aparecen casi en el mismo instante en
        # camaras distintas del grupo, es una senial fuerte de que son la
        # misma persona, incluso si el angulo le tapo a Claude alguna prenda
        # que el otro angulo si ve (ver clasificar()).
        self.umbral_mismo_momento_seg = umbral_mismo_momento_seg

        self.activo = bool(usar_claude_reid and has_claude and api_keys)
        if usar_claude_reid and not has_claude:
            print("[Claude] Paquete 'anthropic' no instalado. ReID en la nube desactivado.")
        elif usar_claude_reid and not api_keys:
            print("[Claude] No hay API keys configuradas (revisa .env). ReID en la nube desactivado.")

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
        """Aplica un intervalo minimo entre llamadas a Claude y, si se detecta
        una rafaga de eventos (varios IDs nuevos casi juntos), agrega una pausa
        extra para no exceder el rate limit sin colgar el procesamiento."""
        eventos_en_rafaga = self._registrar_evento_y_medir_rafaga()

        intervalo_min = self.min_intervalo_seg
        if eventos_en_rafaga >= self.rafaga_umbral:
            intervalo_min += self.pausa_rafaga_seg
            print(f"[Claude] Rafaga detectada ({eventos_en_rafaga} eventos en "
                  f"{self.ventana_rafaga_seg:.0f}s) -> pausa extra de {self.pausa_rafaga_seg:.0f}s")

        transcurrido = time.monotonic() - self._ultima_llamada
        if transcurrido < intervalo_min:
            time.sleep(intervalo_min - transcurrido)
        self._ultima_llamada = time.monotonic()

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

    def generar_descripcion(self, crop_bgr: np.ndarray) -> Optional[dict]:
        """Genera UNA UNICA VEZ por cliente un descriptor visual ESTRUCTURADO
        (no texto libre) pensado para Re-Identificacion: un puñado de rasgos
        estables (ropa, complexion, cabello, accesorios) que se puedan comparar
        despues, no una descripcion de moda. Se usa cuando la persona sale de
        cuadro, queda oculta, o reaparece en otra camara -- nunca reconocimiento
        facial. Si la respuesta no es parseable como JSON (rarisimo con
        output_config.format, salvo corte por max_tokens), reintenta UNA vez --
        perder la descripcion para siempre por un glitch de formato deja a esa
        persona sin candidatos para el Re-ID entre camaras."""
        if not self.activo:
            return None

        imagen_b64 = self._crop_a_base64(crop_bgr)
        if imagen_b64 is None:
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
        for intento in (1, 2):
            self.esperar_turno()
            print("[Claude] Enviando crop de persona para describirla...")
            texto = self._generar_contenido(imagen_b64, prompt)
            if texto is None:
                return None  # fallo de la llamada en si (cupo agotado, etc.) -- reintentar no ayuda
            try:
                descripcion = _parsear_json(texto)
                print(f"[Claude] Descripcion: {json.dumps(descripcion, ensure_ascii=False)}")
                return descripcion
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                print(f"[Claude] Respuesta no parseable al generar descripcion "
                      f"(intento {intento}/2): {error}")
                print(f"[Claude] Texto crudo recibido: {texto!r}")
        return None

    def clasificar(self, crop_bgr: np.ndarray, candidatos: list, momento: Optional[datetime] = None) -> Optional[int]:
        """Genera un descriptor NUEVO e independiente para esta aparicion (con
        generar_descripcion) y lo compara campo a campo contra el descriptor ya
        guardado de cada candidato (clientes recientemente perdidos). Claude no
        siempre va a describir a la misma persona con las mismas palabras
        exactas cada vez -- por eso no se pide una probabilidad, se cuenta
        cuantos de los campos VISIBLES EN AMBOS LADOS coinciden (ver
        _comparar_descriptores: un campo 'no visible' -- ej. la ropa inferior
        tapada por el mostrador de caja desde el angulo de una camara -- no
        cuenta ni a favor ni en contra). color_ropa_superior y
        color_ropa_inferior son ELIMINATORIOS solo cuando son visibles en ambos
        lados; entre los candidatos que pasan ese filtro, se acepta el de mas
        puntaje total, siempre que llegue al minimo configurado
        (coincidencias_minimas), escalado hacia abajo si hay menos campos
        comparables que ese minimo -- una persona vista de la cintura para
        arriba no puede alcanzar el mismo piso que una vista de cuerpo entero,
        y no hay que descartarla solo por eso.
        Si 'momento' viene y el candidato tiene 'primera_deteccion' a menos de
        self.umbral_mismo_momento_seg de diferencia, suma un punto extra al
        puntaje -- las camaras del mismo grupo miran el mismo lugar, asi que
        aparecer casi al mismo instante en dos angulos distintos es evidencia
        fuerte de que es la misma persona, aun cuando un angulo describa menos
        prendas que otro. Devuelve el id del candidato aceptado, o None si no
        hay ninguno lo bastante parecido, si la generacion falla, o si Claude
        esta desactivado.
        NO valida el id contra la lista de tracks perdidos vigentes -- eso es
        responsabilidad de quien llama (PersonTracker), que es quien conoce el
        estado real de lost_tracks."""
        if not self.activo or not candidatos:
            return None

        nueva_descripcion = self.generar_descripcion(crop_bgr)
        if not nueva_descripcion:
            return None

        mejor_sid = None
        mejor_puntaje = -1
        mejor_coincidencias = 0
        mejor_comparables = 0
        mejor_mismo_momento = False
        for c in candidatos:
            descripcion_c = c.get("descripcion") or {}
            if not _obligatorios_coinciden(nueva_descripcion, descripcion_c):
                continue
            coincidencias, comparables = _comparar_descriptores(nueva_descripcion, descripcion_c)
            if comparables == 0:
                continue  # sin ningun campo visible en comun, no hay evidencia para comparar

            mismo_momento = False
            if momento and c.get("primera_deteccion"):
                delta_seg = abs((momento - c["primera_deteccion"]).total_seconds())
                mismo_momento = delta_seg <= self.umbral_mismo_momento_seg

            puntaje = coincidencias + (1 if mismo_momento else 0)
            if puntaje > mejor_puntaje:
                mejor_puntaje        = puntaje
                mejor_coincidencias  = coincidencias
                mejor_comparables    = comparables
                mejor_mismo_momento  = mismo_momento
                mejor_sid = c["sid"]

        if mejor_sid is None:
            print("[Claude] Ningun candidato con color de ropa superior/inferior "
                  "coincidente (donde visible) y evidencia comparable -> descartado")
            return None

        minimo_efectivo = min(self.coincidencias_minimas, mejor_comparables)
        if mejor_puntaje < minimo_efectivo:
            print(f"[Claude] Mejor candidato {mejor_sid} con solo {mejor_coincidencias}/"
                  f"{mejor_comparables} caracteristicas comparables coincidentes "
                  f"{'(+1 mismo momento) ' if mejor_mismo_momento else ''}"
                  f"(< {minimo_efectivo} minimo) -> descartado")
            return None

        print(f"[Claude] Candidato {mejor_sid} con {mejor_coincidencias}/{mejor_comparables} "
              f"caracteristicas comparables coincidentes"
              f"{' + mismo momento en otra camara' if mejor_mismo_momento else ''} -> aceptado")
        return mejor_sid

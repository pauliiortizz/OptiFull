"""Logica comun del Re-ID en la nube (Gemini, Groq y Claude).

Los tres proveedores hacen lo mismo -- describir a una persona UNA vez con un descriptor visual estructurado y,
cuando aparece un id nuevo, compararlo contra candidatos para reconocerla -- y solo cambian en COMO llaman a su
API. Antes cada uno tenia su copia de todo este codigo (gemini_reid.py, groq_reid.py y claude_reid.py, con las
funciones de abajo identicas y el resto igual salvo la etiqueta de los mensajes); ahora vive aca una sola vez y
cada proveedor solo implementa lo suyo (ver ReIDNube).
"""
import json
import re
import time
from datetime import datetime
from typing import Optional

import numpy as np
CAMPOS_DESCRIPTOR = ["color_ropa_superior", "color_ropa_inferior", "complexion", "cabello", "accesorios"]
CAMPOS_OBLIGATORIOS          = ["color_ropa_superior"]
CAMPOS_OBLIGATORIOS_EMPLEADO = ["color_ropa_superior", "color_ropa_inferior"]

_COMILLAS_TIPOGRAFICAS = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "′": "'",
})


def _reparar_json_truncado(texto: str) -> str:
    """Intenta cerrar un JSON que quedo TRUNCADO -- ej. la respuesta del
    modelo se corta antes de la '}' final (pasa mas de lo que uno esperaria,
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
    cualquier texto extra que el modelo agregue despues (a veces pasa incluso
    pidiendo response_mime_type='application/json') -- json.loads() comun
    falla con 'Extra data' en esos casos, raw_decode() no. Si el texto no
    parsea tal cual, prueba normalizando comillas tipograficas ("curly quotes")
    a rectas -- el modelo a veces las usa como delimitadores del JSON; dentro
    del VALOR de un campo (ej. un logo en la ropa) se respetan. Si aun asi
    falla el parseo, es probable que la respuesta haya quedado TRUNCADA (se
    corto antes de la llave de cierre) -- como el modelo corre con temperature=0,
    reintentar la MISMA llamada devuelve casi siempre el mismo corte, asi que
    reparar localmente (en vez de reintentar contra la API) es lo que
    realmente rescata la descripcion."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    # Primero el texto tal cual: comillas tipograficas DENTRO de un valor ('remera “Nike”') son JSON valido, y
    # pasarlas a rectas cortaba el string y se perdia la descripcion entera (DEF-009). Solo si no parsea se
    # prueba con las comillas normalizadas (el modelo a veces las usa como delimitadores) y, por ultimo,
    # reparando un JSON truncado.
    normalizado = texto.translate(_COMILLAS_TIPOGRAFICAS)
    primer_error = None
    for candidato in (texto, normalizado, _reparar_json_truncado(texto), _reparar_json_truncado(normalizado)):
        try:
            obj, _ = json.JSONDecoder().raw_decode(candidato)
            break
        except json.JSONDecodeError as error:
            primer_error = primer_error or error
    else:
        raise primer_error
    if not isinstance(obj, dict):
        # El modelo a veces envuelve el objeto en una lista (ej. '[{...}]') --
        # sin esta validacion, ese descriptor "lista" se guarda tal cual en
        # la BD y revienta mas tarde en _valor_visible() (dict.get() no
        # existe en una lista) cuando otra persona lo trae como candidato.
        raise ValueError(f"Se esperaba un objeto JSON, se recibio {type(obj).__name__}")
    return obj


def _valor_visible(d: dict, campo: str) -> Optional[str]:
    """Valor normalizado de un campo, o None si esta vacio o si el modelo lo
    marco como 'no visible' -- ej. el mostrador de caja tapa la ropa inferior
    desde el angulo de una camara pero no de otra. Un campo 'no visible' no
    es evidencia de nada (ni a favor ni en contra de que sea la misma
    persona), asi que se excluye de la comparacion en vez de tratarlo como un
    valor mas."""
    if not isinstance(d, dict):
        # Defensa ante descripciones corruptas ya guardadas en la BD antes de
        # que _parsear_json validara el tipo (ver historial) -- tratarlo como
        # "no visible" en vez de reventar con AttributeError.
        return None
    v = str(d.get(campo, "")).strip().lower()
    return v if v and v != "no visible" else None


def _valores_coinciden(v1: str, v2: str, campo: str) -> bool:
    """Igualdad exacta para la mayoria de los campos, PERO por color
    individual (no por string completo) para color_ropa_superior/inferior:
    El modelo describe la MISMA prenda combinada de forma inconsistente entre
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


# Prompt de descripcion de Gemini y Groq (Claude usa el suyo: el formato JSON lo fuerza la API).
PROMPT_DESCRIPCION = (
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


class ReIDNube:
    """Base de los clientes de Re-ID en la nube: rate limiting local, descripcion de una persona y clasificacion
    contra candidatos. Cada proveedor (GeminiReID, GroqReID, ClaudeReID) define ETIQUETA, MSG_SIN_DEPENDENCIAS,
    PROMPT, _preparar_imagen() (recorte BGR -> lo que acepta su API) y _pedir_descripcion() (la llamada a su API,
    devuelve el texto crudo o None). Si no esta activo (dependencias faltantes, sin API keys, o desactivado por
    config), todos los metodos son no-ops que devuelven None. PersonTracker solo usa '.activo',
    '.generar_descripcion()' y '.clasificar()', asi que los proveedores son intercambiables."""

    ETIQUETA = "ReID"
    MSG_SIN_DEPENDENCIAS = "Dependencias no instaladas. ReID en la nube desactivado."
    PROMPT = PROMPT_DESCRIPCION

    def __init__(
        self,
        usar_reid: bool,
        has_dependencias: bool,
        api_keys: list,
        model: str,
        min_intervalo_seg: float,
        rafaga_umbral: int,
        pausa_rafaga_seg: float,
        ventana_rafaga_seg: float,
        coincidencias_minimas: int,
        umbral_mismo_momento_seg: float,
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
        # misma persona, incluso si el angulo le tapo al modelo alguna prenda
        # que el otro angulo si ve (ver clasificar()).
        self.umbral_mismo_momento_seg = umbral_mismo_momento_seg

        self.activo = bool(usar_reid and has_dependencias and api_keys)
        if usar_reid and not has_dependencias:
            print(f"[{self.ETIQUETA}] {self.MSG_SIN_DEPENDENCIAS}")
        elif usar_reid and not api_keys:
            print(f"[{self.ETIQUETA}] No hay API keys configuradas (revisa .env). ReID en la nube desactivado.")

        self._ultima_llamada: float = 0.0
        self._eventos_recientes: list = []

    # ── Lo que implementa cada proveedor ────────────────────────────────────────
    def _preparar_imagen(self, crop_bgr: np.ndarray):
        raise NotImplementedError

    def _pedir_descripcion(self, imagen, prompt: str) -> Optional[str]:
        raise NotImplementedError

    def _antes_de_pedir(self) -> None:
        """Gancho opcional antes de cada llamada (Claude lo usa para loggear)."""

    def _descripcion_obtenida(self, descripcion: dict) -> None:
        """Gancho opcional al obtener una descripcion valida (Claude lo usa para loggear)."""

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
        """Aplica un intervalo minimo entre llamadas a la API y, si se detecta
        una rafaga de eventos (varios IDs nuevos casi juntos), agrega una pausa
        extra para no exceder el rate limit del free tier sin colgar el procesamiento."""
        eventos_en_rafaga = self._registrar_evento_y_medir_rafaga()

        intervalo_min = self.min_intervalo_seg
        if eventos_en_rafaga >= self.rafaga_umbral:
            intervalo_min += self.pausa_rafaga_seg
            print(f"[{self.ETIQUETA}] Rafaga detectada ({eventos_en_rafaga} eventos en "
                  f"{self.ventana_rafaga_seg:.0f}s) -> pausa extra de {self.pausa_rafaga_seg:.0f}s")

        transcurrido = time.monotonic() - self._ultima_llamada
        if transcurrido < intervalo_min:
            time.sleep(intervalo_min - transcurrido)
        self._ultima_llamada = time.monotonic()

    def generar_descripcion(self, crop_bgr: np.ndarray) -> Optional[dict]:
        """Genera UNA UNICA VEZ por cliente un descriptor visual ESTRUCTURADO
        (no texto libre) pensado para Re-Identificacion: un puñado de rasgos
        estables (ropa, complexion, cabello, accesorios) que se puedan comparar
        despues, no una descripcion de moda. Se usa cuando la persona sale de
        cuadro, queda oculta, o reaparece en otra camara -- nunca reconocimiento
        facial. Si el modelo devuelve una respuesta no parseable como JSON (falla
        ocasional del modelo, no del codigo), reintenta UNA vez -- perder la
        descripcion para siempre por un glitch de formato deja a esa persona
        sin candidatos para el Re-ID entre camaras."""
        if not self.activo:
            return None

        imagen = self._preparar_imagen(crop_bgr)
        if imagen is None:
            return None

        prompt = self.PROMPT
        for intento in (1, 2):
            self.esperar_turno()
            self._antes_de_pedir()
            texto = self._pedir_descripcion(imagen, prompt)
            if texto is None:
                return None  # fallo de la llamada en si (cupo agotado, etc.) -- reintentar no ayuda
            try:
                descripcion = _parsear_json(texto)
                self._descripcion_obtenida(descripcion)
                return descripcion
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                print(f"[{self.ETIQUETA}] Respuesta no parseable al generar descripcion "
                      f"(intento {intento}/2): {error}")
                print(f"[{self.ETIQUETA}] Texto crudo recibido: {texto!r}")
        return None

    def clasificar(self, crop_bgr: np.ndarray, candidatos: list, momento: Optional[datetime] = None) -> Optional[int]:
        """Genera un descriptor NUEVO e independiente para esta aparicion (con
        generar_descripcion) y lo compara campo a campo contra el descriptor ya
        guardado de cada candidato (clientes recientemente perdidos). El modelo no
        siempre va a describir a la misma persona con las mismas palabras exactas
        cada vez -- por eso no se pide una probabilidad, se cuenta cuantos de los
        campos VISIBLES EN AMBOS LADOS coinciden (ver _comparar_descriptores: un
        campo 'no visible' -- ej. la ropa inferior tapada por el mostrador de
        caja desde el angulo de una camara -- no cuenta ni a favor ni en contra).
        color_ropa_superior y color_ropa_inferior son ELIMINATORIOS solo cuando
        son visibles en ambos lados; entre los candidatos que pasan ese filtro,
        se acepta el de mas puntaje total, siempre que llegue al minimo
        configurado (coincidencias_minimas), escalado hacia abajo si hay menos
        campos comparables que ese minimo -- una persona vista de la cintura
        para arriba no puede alcanzar el mismo piso que una vista de cuerpo
        entero, y no hay que descartarla solo por eso.
        Si 'momento' viene y el candidato tiene 'primera_deteccion' a menos de
        self.umbral_mismo_momento_seg de diferencia, suma un punto extra al
        puntaje (no cuenta como 'coincidencia' real para el minimo escalado,
        pero puede ser el desempate entre varios candidatos parecidos, o
        completar el minimo cuando solo hay 1 campo visible en comun) -- las
        camaras del mismo grupo miran el mismo lugar, asi que aparecer casi al
        mismo instante en dos angulos distintos es evidencia fuerte de que es
        la misma persona, aun cuando un angulo describa menos prendas que otro.
        Devuelve el id del candidato aceptado, o None si no hay ninguno lo
        bastante parecido, si la generacion falla, o si el Re-ID esta desactivado.
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
            print(f"[{self.ETIQUETA}] Ningun candidato con color de ropa superior/inferior "
                  "coincidente (donde visible) y evidencia comparable -> descartado")
            return None

        minimo_efectivo = min(self.coincidencias_minimas, mejor_comparables)
        if mejor_puntaje < minimo_efectivo:
            print(f"[{self.ETIQUETA}] Mejor candidato {mejor_sid} con solo {mejor_coincidencias}/"
                  f"{mejor_comparables} caracteristicas comparables coincidentes "
                  f"{'(+1 mismo momento) ' if mejor_mismo_momento else ''}"
                  f"(< {minimo_efectivo} minimo) -> descartado")
            return None

        print(f"[{self.ETIQUETA}] Candidato {mejor_sid} con {mejor_coincidencias}/{mejor_comparables} "
              f"caracteristicas comparables coincidentes"
              f"{' + mismo momento en otra camara' if mejor_mismo_momento else ''} -> aceptado")
        return mejor_sid

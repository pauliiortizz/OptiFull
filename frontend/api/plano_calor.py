"""Calor DENTRO de cada zona, para pintar el croquis de la tienda.

Cada camara tiene su mapa de calor acumulado (grilla NxN normalizada 0-1 por el
maximo de ESA camara, ver mapas_calor_camara) y sus propias zonas dibujadas
(tabla 'zonas', en espacio 1920x1080). Para cada TIPO de zona (caja / gondola /
otro) se usa UNA sola camara como fuente (FUENTES_POR_DEFECTO) y se devuelve el
recorte de su grilla que cae dentro del poligono de esa zona (celdas fuera = 0),
mas el 'pico' (valor maximo dentro de la zona, 0-1 respecto del maximo de la
camara). El frontend traslada ese recorte al poligono de la zona en el croquis
(ver FloorPlan.jsx), asi se ve que parte de la zona esta mas caliente.

Una sola camara por zona a proposito: combinar camaras que miran la misma zona
desde angulos distintos exigiria saber que punto de una imagen es cual punto de la otra."""
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw

# Resolucion del video sobre el que se dibujaron las zonas (ver ZONAS_REF_RESOLUCION
# en deteccion/config.py). Las grillas son fracciones del cuadro, asi que sirven
# para cualquier resolucion de camara.
ZONAS_REF = (1920, 1080)

# Camara que alimenta cada tipo de zona del croquis: Góndolas = Full cajas (4),
# Salón = Full esquina (2). Caja no se especifico: se usa la 4 (la que mejor ve
# el mostrador) -- cambiar aca o con ?fuentes=caja:3 en /api/heatmap/plano.
FUENTES_POR_DEFECTO = {"gondola": 4, "otro": 2, "caja": 4}


def mascara_zona(poligono, grid_size: int) -> np.ndarray:
    """Mascara booleana grid_size x grid_size de las celdas que cubre el poligono."""
    sx, sy = grid_size / ZONAS_REF[0], grid_size / ZONAS_REF[1]
    img = Image.new("L", (grid_size, grid_size), 0)
    ImageDraw.Draw(img).polygon([(x * sx, y * sy) for x, y in poligono], fill=1, outline=1)
    return np.array(img, dtype=bool)


def calor_en_zona(matriz, valor_maximo: float, poligono) -> Optional[dict]:
    """Recorte de la grilla dentro de 'poligono' (None si no cubre ninguna celda).
    'grid' es el recorte (celdas fuera del poligono = 0), 'origen' la celda (col, fila)
    de su esquina superior izquierda en la grilla completa, 'bbox' el rectangulo del
    poligono en espacio 1920x1080, 'pico' el maximo dentro de la zona (0-1)."""
    grid = np.array(matriz, dtype=np.float64)
    n = grid.shape[0]
    mask = mascara_zona(poligono, n)
    if not mask.any():
        return None
    filas, cols = np.where(mask)
    f0, f1, c0, c1 = filas.min(), filas.max() + 1, cols.min(), cols.max() + 1
    recorte = np.where(mask, grid, 0.0)[f0:f1, c0:c1]
    crudo = grid * float(valor_maximo or 0)
    total = crudo.sum()
    xs = [p[0] for p in poligono]
    ys = [p[1] for p in poligono]
    return {
        "pico":      round(float(grid[mask].max()), 4),
        "share_pct": round(float(crudo[mask].sum() / total * 100), 2) if total > 0 else 0.0,
        "bbox":      {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)},
        "origen":    [int(c0), int(f0)],
        "grid":      [[round(float(v), 3) for v in fila] for fila in recorte],
    }


def calor_por_zona(camaras: dict, fuentes: Optional[dict] = None) -> dict:
    """'camaras': {camara_id: {matriz, valor_maximo, zonas: [{tipo, poligono}]}} ->
    {tipo: {camara_id, pico, share_pct, bbox, origen, grid}} usando solo la camara fuente de
    cada tipo. Un tipo cuya camara fuente no tiene datos o no tiene esa zona no aparece."""
    fuentes = fuentes or FUENTES_POR_DEFECTO
    resultado = {}
    for tipo, camara_id in fuentes.items():
        c = camaras.get(camara_id)
        if not c:
            continue
        for z in c["zonas"]:
            if z["tipo"] != tipo:
                continue
            medida = calor_en_zona(c["matriz"], c["valor_maximo"], z["poligono"])
            if medida:
                resultado[tipo] = {"camara_id": camara_id, **medida}
                break
    return resultado


# ── Calor por hora del dia, PROMEDIO de todos los dias (reproduccion del mapa de calor) ──
# El mapa de calor acumulado no tiene hora, asi que para reproducirlo se usan las posiciones de
# trayectoria (cada ~10 s por persona, con su timestamp). Se juntan TODOS los dias en un solo dia
# "tipico": el backend reparte las posiciones por zona de la camara fuente y las agrupa por celda de
# la grilla y por bloque horario; el frontend arma el calor de cada hora sumando los bloques de la
# ventana elegida y dividiendo por la cantidad de dias con datos de esa camara (promedio por dia).

BLOQUE_SEG = 300                      # los bloques horarios son de 5 minutos


def bbox_poligono(poligono) -> dict:
    xs = [p[0] for p in poligono]
    ys = [p[1] for p in poligono]
    return {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}


def zona_fuente(zonas_por_camara: dict, tipo: str, camara_id: int) -> Optional[dict]:
    """La zona de 'tipo' de la camara fuente (la primera, si hay varias); None si no tiene."""
    return next((z for z in zonas_por_camara.get(camara_id, []) if z["tipo"] == tipo), None)


def dias_activos(por_dia: dict) -> int:
    """Dias con actividad real a partir de {dia: posiciones}: al menos 10% de las posiciones del dia mas
    activo. Un dia con unas pocas posiciones (grabacion cortada) no cuenta, porque dividir por el
    achicaria el promedio de todos los demas."""
    return sum(1 for n in por_dia.values() if n >= 0.1 * max(por_dia.values())) if por_dia else 0


def armar_celdas(por_dia: dict, cuentas: dict, zonas_por_camara: dict, fuentes: Optional[dict] = None) -> dict:
    """Respuesta de celdas_por_zona a partir de los conteos ya agrupados (asi el endpoint los pide agrupados
    a la base): 'por_dia' = {camara_id: {dia: posiciones}} con TODAS las posiciones de la camara, 'cuentas' =
    {tipo: {(bloque, col, fila): n}} con las que caen dentro de la zona de ese tipo."""
    fuentes = fuentes or FUENTES_POR_DEFECTO
    resultado = {}
    for tipo, camara_id in fuentes.items():
        zona = zona_fuente(zonas_por_camara, tipo, camara_id)
        cuenta = cuentas.get(tipo)
        if zona is None or not por_dia.get(camara_id) or not cuenta:
            continue
        resultado[tipo] = {
            "camara_id": camara_id,
            "bbox":      bbox_poligono(zona["poligono"]),
            "dias":      dias_activos(por_dia[camara_id]),
            "celdas":    sorted([b, c, r, n] for (b, c, r), n in cuenta.items()),
        }
    return resultado


def dentro_de_zona(poligono, xy) -> np.ndarray:
    """Que puntos de 'xy' (n x 2, en pixeles de ZONAS_REF) caen dentro del poligono, CONTANDO EL BORDE como
    adentro -- igual que 'polygon @> point' de Postgres, que es lo que usan /heatmap/plano/tiempo y /plano/flujo.
    matplotlib (contains_points) deja afuera los puntos justo sobre el borde, y una zona que ocupa todo el
    cuadro (0,0 a 1920,1080) perdia a quien se veia pegado al borde de la imagen."""
    from matplotlib.path import Path

    pol = np.array(poligono, dtype=float)
    xy = np.asarray(xy, dtype=float).reshape(-1, 2)
    dentro = Path(pol).contains_points(xy)
    for a, b in zip(pol, np.roll(pol, -1, axis=0)):          # cada lado del poligono
        ab = b - a
        largo2 = float(ab @ ab) or 1.0
        t = np.clip(((xy - a) @ ab) / largo2, 0.0, 1.0)
        dentro |= np.hypot(*(xy - (a + t[:, None] * ab)).T) < 1e-6
    return dentro


def celdas_por_zona(filas: list, zonas_por_camara: dict, fuentes: Optional[dict] = None, grid_size: int = 64) -> dict:
    """'filas': [{camara_id, dia, seg, xn, yn}] -- dia = fecha (cualquier valor comparable), seg =
    segundos desde las 00:00, (xn, yn) = posicion como fraccion 0-1 del cuadro de la camara.
    Devuelve {tipo: {camara_id, bbox, dias, celdas}} usando solo las posiciones de la camara fuente
    de ese tipo que caen DENTRO del poligono de su zona, de TODOS los dias juntos.
    'dias' = cuantos dias con actividad real tiene esa camara (ver dias_activos); 'celdas' = [[bloque, col, fila, n]]:
    n posiciones en la celda (col, fila) de la grilla durante el bloque de 5 min (bloque * 300 s).
    /heatmap/plano/tiempo hace este mismo agrupado en SQL (ver heatmap.py) y arma la respuesta con armar_celdas."""
    from collections import Counter

    fuentes = fuentes or FUENTES_POR_DEFECTO
    por_dia: dict = {}
    for f in filas:
        por_dia.setdefault(f["camara_id"], Counter())[f["dia"]] += 1
    cuentas = {}
    for tipo, camara_id in fuentes.items():
        zona = zona_fuente(zonas_por_camara, tipo, camara_id)
        propias = [f for f in filas if f["camara_id"] == camara_id]
        if zona is None or not propias:
            continue
        xy = np.array([[f["xn"] * ZONAS_REF[0], f["yn"] * ZONAS_REF[1]] for f in propias])
        dentro = dentro_de_zona(zona["poligono"], xy)
        cuenta: Counter = Counter()
        for f, d in zip(propias, dentro):
            if not d:
                continue
            col = min(grid_size - 1, max(0, int(f["xn"] * grid_size)))
            fila = min(grid_size - 1, max(0, int(f["yn"] * grid_size)))
            cuenta[(int(f["seg"]) // BLOQUE_SEG, col, fila)] += 1
        cuentas[tipo] = cuenta
    return armar_celdas(por_dia, cuentas, zonas_por_camara, fuentes)


def rango_horario(zonas: dict, minimo: int = 60) -> dict:
    """Rango (en minutos desde las 00:00, redondeado a la hora) que cubren los datos de todas las zonas."""
    bloques = [c[0] for z in zonas.values() for c in z["celdas"]]
    if not bloques:
        return {"desde": 8 * 60, "hasta": 22 * 60}
    desde = (min(bloques) * BLOQUE_SEG // 3600) * 60
    hasta = -(-((max(bloques) + 1) * BLOQUE_SEG) // 3600) * 60
    return {"desde": desde, "hasta": max(hasta, desde + minimo)}


# ── Recorridos de clientes (flechas de trayectoria promedio) ─────────────────
# Cada persona deja una serie de posiciones con hora. Para pintar "por donde se mueven los clientes
# normalmente" el backend parte cada recorrido en tramos DENTRO de cada zona de la camara fuente (los
# recorridos entre zonas de camaras distintas no existen: cada camara rastrea por su cuenta), descarta
# a quien casi no se mueve (parado en el mostrador o en una mesa) y simplifica cada tramo a pocos
# puntos equiespaciados. El frontend agrupa los tramos parecidos de la ventana de tiempo elegida y
# dibuja unas pocas flechas, una por ruta frecuente.

def _resamplear(puntos: list, n: int) -> list:
    """n puntos equiespaciados a lo largo de la poligonal 'puntos' [(x, y), ...]."""
    acum = [0.0]
    for (x0, y0), (x1, y1) in zip(puntos, puntos[1:]):
        acum.append(acum[-1] + ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    total = acum[-1]
    if total == 0:
        return [puntos[0]] * n
    salida, j = [], 0
    for k in range(n):
        objetivo = total * k / (n - 1)
        while j < len(acum) - 2 and acum[j + 1] < objetivo:
            j += 1
        tramo = acum[j + 1] - acum[j]
        f = 0.0 if tramo == 0 else (objetivo - acum[j]) / tramo
        salida.append((puntos[j][0] + f * (puntos[j + 1][0] - puntos[j][0]),
                       puntos[j][1] + f * (puntos[j + 1][1] - puntos[j][1])))
    return salida


def diagonal_zona(poligono) -> float:
    """Diagonal del rectangulo de la zona, como fraccion del cuadro (la escala de 'desplazamiento_min')."""
    bb = bbox_poligono(poligono)
    return (((bb["x1"] - bb["x0"]) / ZONAS_REF[0]) ** 2 + ((bb["y1"] - bb["y0"]) / ZONAS_REF[1]) ** 2) ** 0.5


def armar_tramos(corridas: list, por_dia: dict, zonas_por_camara: dict, fuentes: Optional[dict] = None,
                 n_puntos: int = 6, desplazamiento_min: float = 0.15, min_puntos: int = 3) -> dict:
    """Respuesta de tramos_por_zona a partir de los recorridos ya partidos por zona (asi el endpoint los pide
    partidos a la base): 'corridas' = [(tipo, [(seg, xn, yn), ...])] en orden de hora, 'por_dia' =
    {camara_id: {dia: posiciones}} con TODAS las posiciones de clientes de la camara. Descarta las corridas
    cortas o de gente parada y simplifica el resto a 'n_puntos'."""
    fuentes = fuentes or FUENTES_POR_DEFECTO
    tramos = {tipo: [] for tipo in fuentes}
    for tipo, puntos in corridas:
        zona = zona_fuente(zonas_por_camara, tipo, fuentes[tipo])
        if zona is None or len(puntos) < min_puntos:
            continue
        diag = diagonal_zona(zona["poligono"])
        pts = [(xn, yn) for _, xn, yn in puntos]
        neto = ((pts[-1][0] - pts[0][0]) ** 2 + (pts[-1][1] - pts[0][1]) ** 2) ** 0.5
        if diag == 0 or neto < desplazamiento_min * diag:
            continue
        plano = [v for p in _resamplear(pts, n_puntos) for v in p]
        tramos[tipo].append([int(puntos[0][0]) // 60, [int(round(min(1.0, max(0.0, v)) * 1000)) for v in plano]])

    resultado = {}
    for tipo, lista in tramos.items():
        if not lista:
            continue
        cam = fuentes[tipo]
        resultado[tipo] = {
            "camara_id": cam,
            "bbox":      bbox_poligono(zona_fuente(zonas_por_camara, tipo, cam)["poligono"]),
            "dias":      dias_activos(por_dia.get(cam, {})),
            "tramos":    sorted(lista),
        }
    return resultado


def tramos_por_zona(filas: list, zonas_por_camara: dict, fuentes: Optional[dict] = None,
                    n_puntos: int = 6, desplazamiento_min: float = 0.15,
                    hueco_max_seg: int = 60, min_puntos: int = 3) -> dict:
    """'filas': posiciones de CLIENTES [{camara_id, persona_id, dia, seg, xn, yn}] (xn, yn = fraccion 0-1
    del cuadro), ordenadas por persona y hora. Devuelve {tipo: {camara_id, bbox, dias, tramos}} con los
    tramos de recorrido que ocurren dentro de la zona de ese tipo de su camara fuente, de TODOS los dias.
    Un tramo = posiciones consecutivas (sin huecos de mas de 'hueco_max_seg') de una misma persona dentro
    de la zona; se descartan los de menos de 'min_puntos' posiciones o con un desplazamiento neto
    (inicio -> fin) menor a 'desplazamiento_min' de la diagonal de la zona (gente parada).
    'tramos' = [[minuto_de_inicio, [x1, y1, ..., xn, yn]]] con x, y en milesimas del cuadro.
    /heatmap/plano/flujo parte los recorridos en SQL (ver heatmap.py) y arma la respuesta con armar_tramos."""
    from collections import Counter

    fuentes = fuentes or FUENTES_POR_DEFECTO
    # tipos que alimenta cada camara, en el orden de 'fuentes' (si dos zonas se pisan gana la primera)
    por_camara: dict = {}
    for tipo, cam in fuentes.items():
        zona = zona_fuente(zonas_por_camara, tipo, cam)
        if zona is not None:
            por_camara.setdefault(cam, []).append((tipo, zona["poligono"]))

    por_dia: dict = {}
    por_persona: dict = {}
    for f in filas:
        por_dia.setdefault(f["camara_id"], Counter())[f["dia"]] += 1
        if f["camara_id"] in por_camara:
            por_persona.setdefault((f["camara_id"], f["persona_id"]), []).append(f)

    corridas: list = []
    for (cam, _), puntos in por_persona.items():
        puntos.sort(key=lambda f: f["seg"])
        xy = np.array([[f["xn"] * ZONAS_REF[0], f["yn"] * ZONAS_REF[1]] for f in puntos])
        asignado = [None] * len(puntos)
        for tipo, poligono in por_camara[cam]:
            dentro = dentro_de_zona(poligono, xy)
            for i, d in enumerate(dentro):
                if d and asignado[i] is None:
                    asignado[i] = tipo
        corrida: list = []
        for i, f in enumerate(puntos):
            tipo = asignado[i]
            if tipo is None or (corrida and (tipo != corrida[-1][0] or f["seg"] - corrida[-1][1][0] > hueco_max_seg)):
                if corrida:
                    corridas.append((corrida[0][0], [p for _, p in corrida]))
                corrida = []
            if tipo is not None:
                corrida.append((tipo, (f["seg"], f["xn"], f["yn"])))
        if corrida:
            corridas.append((corrida[0][0], [p for _, p in corrida]))
    return armar_tramos(corridas, por_dia, zonas_por_camara, fuentes, n_puntos, desplazamiento_min, min_puntos)

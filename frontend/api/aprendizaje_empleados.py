"""Aprende de las decisiones del usuario en las alertas "Persona posiblemente empleada".

Cada vez que alguien resuelve una de esas alertas ("Es empleado" / "No es empleado", POST /personas/<id>/empleado
con revisado=true) la persona queda en 'personas' con empleado_revisado = TRUE y su respuesta en es_empleado. Esas
personas son los ejemplos: con lo que se vio de ellas ese dia (cuanto tiempo, en que zonas, a que hora llego, cuanto
duro su jornada, la ropa) se entrena una regresion logistica chica y con ella se puntua cada candidato nuevo:

  - prob_empleado: que tan parecido es a los empleados que ya confirmaste (0 a 1);
  - motivos: lo que mas pesa en esa estimacion, en palabras ("paso el 62% del tiempo en la caja", ...).

Cuantas mas alertas se resuelven, mas ejemplos tiene y mejor separa empleados de clientes. No guarda nada aparte:
el modelo se vuelve a entrenar en cada consulta a partir de las decisiones que estan en la base (son pocas filas).
"""
import json

import numpy as np

# Con menos ejemplos de cada clase no hay con que comparar: no se estima nada.
MIN_EJEMPLOS_POR_CLASE = 3
# Con al menos estos ejemplos de cada clase, un candidato que se parece claramente a los clientes confirmados ya no
# se levanta como alerta (es lo que se aprendio de las respuestas "No es empleado").
MIN_EJEMPLOS_PARA_DESCARTAR = 5
# 5%: medido con las 62 personas revisadas (oct-2026, dejando cada una afuera del entrenamiento) no oculto a ningun
# empleado; con 15% ya ocultaba uno.
PROB_DESCARTE_CLIENTE = 0.05

_NUMERICAS = ['horas', 'jornada', 'llegada', 'frac_caja', 'frac_gondola', 'frac_salon', 'frac_sin_zona']
_ZONAS = {'caja': 'la caja', 'gondola': 'góndolas', 'salon': 'el salón', 'sin_zona': 'fuera de las zonas'}


def _ropa(descripcion):
    if not descripcion:
        return {}
    if isinstance(descripcion, str):
        try:
            descripcion = json.loads(descripcion)
        except ValueError:
            return {}
    ropa = {}
    for clave, nombre in (('color_ropa_superior', 'sup'), ('color_ropa_inferior', 'inf')):
        color = (descripcion.get(clave) or '').strip().lower()
        if color and color != 'no visible':
            ropa[nombre] = color
    return ropa


def caracteristicas(fila):
    """Lo que se vio de una persona en un dia (una fila de la consulta de posibles empleados) -> dict de numeros
    y la ropa. 'fila' trae: segundos, seg_caja, seg_gondola, seg_otro, primera_hora, ultima_hora, descripcion_visual."""
    total = float(fila.get('segundos') or 0) or 1.0
    caja, gondola, salon = (float(fila.get(k) or 0) for k in ('seg_caja', 'seg_gondola', 'seg_otro'))
    primera, ultima = fila.get('primera_hora'), fila.get('ultima_hora')
    return {
        'horas':         total / 3600,
        'jornada':       (ultima - primera).total_seconds() / 3600 if primera and ultima else 0.0,
        'llegada':       primera.hour + primera.minute / 60 if primera else 0.0,
        'frac_caja':     caja / total,
        'frac_gondola':  gondola / total,
        'frac_salon':    salon / total,
        'frac_sin_zona': max(0.0, 1 - (caja + gondola + salon) / total),
        'ropa':          _ropa(fila.get('descripcion_visual')),
    }


class Modelo:
    """Regresion logistica (L2) sobre las caracteristicas numericas estandarizadas + los colores de ropa vistos en
    los ejemplos (one-hot). Determinista: mismo resultado para las mismas decisiones."""

    def __init__(self, ejemplos):
        """ejemplos: lista de (caracteristicas, es_empleado)."""
        self.n_empleados = sum(1 for _, y in ejemplos if y)
        self.n_clientes = len(ejemplos) - self.n_empleados
        self.listo = min(self.n_empleados, self.n_clientes) >= MIN_EJEMPLOS_POR_CLASE
        if not self.listo:
            return
        colores = sorted({f"{k}:{v}" for c, _ in ejemplos for k, v in c['ropa'].items()})
        self.columnas = _NUMERICAS + colores
        X = np.array([self._crudo(c) for c, _ in ejemplos])
        y = np.array([1.0 if e else 0.0 for _, e in ejemplos])
        self.media = X.mean(axis=0)
        self.desvio = X.std(axis=0)
        self.desvio[self.desvio == 0] = 1.0
        Z = (X - self.media) / self.desvio
        self.pesos = np.zeros(Z.shape[1])
        self.sesgo = 0.0
        lam, paso = 1.0, 0.5
        for _ in range(800):
            p = 1 / (1 + np.exp(-(Z @ self.pesos + self.sesgo)))
            error = p - y
            self.pesos -= paso * (Z.T @ error / len(y) + lam * self.pesos / len(y))
            self.sesgo -= paso * error.mean()

    def _crudo(self, c):
        """Vector de la persona: las numericas y un 1/0 por cada color de ropa visto en los ejemplos."""
        colores = [col.split(':') for col in self.columnas[len(_NUMERICAS):]]
        return [c[k] for k in _NUMERICAS] + [float(c['ropa'].get(parte) == color) for parte, color in colores]

    def predecir(self, c):
        """(probabilidad de que sea empleado, motivos en palabras) o (None, []) si todavia no hay modelo."""
        if not self.listo:
            return None, []
        z = (np.array(self._crudo(c)) - self.media) / self.desvio
        aportes = z * self.pesos
        prob = float(1 / (1 + np.exp(-(aportes.sum() + self.sesgo))))
        # lo que mas empuja hacia la respuesta que da el modelo
        signo = 1 if prob >= 0.5 else -1
        orden = sorted(range(len(aportes)), key=lambda i: -signo * aportes[i])
        motivos = []
        for i in orden:
            if signo * aportes[i] <= 0 or len(motivos) == 2:
                break
            texto = self._motivo(self.columnas[i], c, bajo=z[i] < 0)
            if texto:
                motivos.append(texto)
        return prob, motivos

    @staticmethod
    def _motivo(columna, c, bajo=False):
        """'bajo': el valor de esta persona esta por debajo del promedio de los ejemplos (eso es lo que pesa)."""
        if columna.startswith('frac_'):
            pct, zona = round(c[columna] * 100), _ZONAS[columna[5:]]
            if pct == 0:
                return f"no pasó por {zona}" if columna != 'frac_sin_zona' else None
            return f"{'solo ' if bajo else ''}pasó el {pct}% del tiempo en {zona}"
        if columna == 'horas':
            return f"estuvo {c['horas']:.1f} h a la vista".replace('.', ',')
        if columna == 'jornada':
            return f"su jornada duró {c['jornada']:.1f} h".replace('.', ',')
        if columna == 'llegada':
            return f"llegó a las {int(c['llegada']):02d}:{round(c['llegada'] % 1 * 60):02d}"
        parte, color = columna.split(':')
        if c['ropa'].get(parte) != color:
            return None
        return f"ropa {'superior' if parte == 'sup' else 'inferior'} {color}"


def puntuar(filas):
    """Entrena con las filas ya revisadas y puntua las que no. Agrega a cada fila 'prob_empleado' (o None) y
    'motivos', y devuelve el modelo (para saber con cuantos ejemplos aprendio)."""
    feats = [caracteristicas(f) for f in filas]
    modelo = Modelo([(c, bool(f['es_empleado'])) for f, c in zip(filas, feats) if f['revisado']])
    for f, c in zip(filas, feats):
        f['prob_empleado'], f['motivos'] = (None, []) if f['revisado'] else modelo.predecir(c)
    return modelo


def descartar_por_cliente(modelo, fila):
    """True si el candidato se parece claramente a los clientes ya confirmados y hay ejemplos suficientes para
    confiar en eso: no hace falta preguntarle de nuevo al usuario."""
    return (fila['prob_empleado'] is not None and fila['prob_empleado'] < PROB_DESCARTE_CLIENTE
            and min(modelo.n_empleados, modelo.n_clientes) >= MIN_EJEMPLOS_PARA_DESCARTAR)

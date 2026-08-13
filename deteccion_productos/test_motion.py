"""
test_motion.py
---------------
Prueba el MotionAgent con frames SINTÉTICOS (arrays de numpy), sin
cámara ni video real.

Verifica las dos señales que tienen que darse juntas para disparar un
análisis: estabilidad (frames parecidos entre sí) y escena nueva
(distinta al último frame analizado).

Correr: python test_motion.py
"""

import numpy as np

from agents.motion_agent import MotionAgent


ALTO, ANCHO = 240, 320

# Los timestamps se simulan a este ritmo. Como la estabilidad ahora se
# mide en TIEMPO (ESTABLE_MS), los frames tienen que abarcar esa
# ventana: a 10 fps (dt=0.1s), 3 frames cubren 0.2s > 150ms.
DT = 0.1


def frame_solido(valor, ruido=0):
    """Frame de un color sólido (simula un producto quieto bajo la cámara).
    'ruido' agrega variación aleatoria leve para simular vibración del
    sensor sin romper la estabilidad."""
    base = np.full((ALTO, ANCHO, 3), valor, dtype=np.int16)
    if ruido:
        base += np.random.randint(-ruido, ruido + 1, base.shape)
    return np.clip(base, 0, 255).astype(np.uint8)


def correr_caso(nombre, frames, esperado):
    motion = MotionAgent()
    resultados = [motion.deberia_analizar(f, i * DT) for i, f in enumerate(frames)]
    obtenido = resultados[-1]
    ok = obtenido == esperado
    marca = "✔" if ok else "✘"
    print(f"{marca} {nombre}: resultados={resultados} -> {obtenido} (esperado {esperado})")
    return ok


def main():
    aciertos = 0
    total = 0

    # Caso 1: frames idénticos (quieto) -> tras N frames, estable + nueva
    # escena (primer análisis) -> debería disparar en el último frame.
    frames = [frame_solido(100)] * 5
    total += 1
    aciertos += correr_caso("Quieto desde el arranque", frames, True)

    # Caso 2: sigue en movimiento (cada frame muy distinto) -> nunca
    # debería considerarse estable.
    frames = [frame_solido(v) for v in (20, 200, 40, 180, 60)]
    total += 1
    aciertos += correr_caso("En movimiento constante", frames, False)

    # Caso 3: estable, pero misma escena que la última analizada
    # (no debería re-disparar sobre el mismo producto).
    motion = MotionAgent()
    t = 0.0
    frames_quieto = [frame_solido(100)] * 4
    for f in frames_quieto:
        motion.deberia_analizar(f, t)
        t += DT
    motion.marcar_analizado(frames_quieto[-1])
    # Mismo valor, sigue estable -> no debería ser "escena nueva"
    resultado = motion.deberia_analizar(frame_solido(100), t)
    t += DT
    total += 1
    ok = resultado is False
    aciertos += ok
    print(f"{'✔' if ok else '✘'} Estable pero misma escena: -> {resultado} (esperado False)")

    # Caso 4: estable, después cambia a un producto distinto (escena
    # nueva) -> debería volver a disparar.
    resultado = None
    for f in [frame_solido(220)] * 4:
        resultado = motion.deberia_analizar(f, t)
        t += DT
    total += 1
    ok = resultado is True
    aciertos += ok
    print(f"{'✔' if ok else '✘'} Estable y escena nueva tras cambio: -> {resultado} (esperado True)")

    # Caso 5: micro-ruido (vibración/luz) no debería romper la estabilidad.
    frames = [frame_solido(100, ruido=3) for _ in range(5)]
    total += 1
    aciertos += correr_caso("Micro-ruido, no rompe estabilidad", frames, True)

    print("-" * 60)
    print(f"Aciertos: {aciertos}/{total}")


if __name__ == "__main__":
    main()

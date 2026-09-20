"""Graficos estadisticos (PNG) de Reportes 2.0: barras, lineas y matriz dia x hora.

Usa matplotlib.figure.Figure directamente (sin pyplot): pyplot mantiene estado
global y no es thread-safe, y Flask atiende cada pedido en su propio hilo.
"""
import io

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle


# Paleta de la app (--brand / --brand-deep en index.css) y rampa secuencial de
# un solo hue para magnitudes (mas gente = mas oscuro).
BRAND      = '#6a72cf'
BRAND_DEEP = '#4f57ae'
INK        = '#0f172a'
MUTED      = '#64748b'
GRID       = '#e3ddf0'
RAMP       = ['#eef0fc', '#cfd3f5', '#aeb4ec', '#8d95e0', '#6a72cf', '#4f57ae', '#363c85']
CMAP_SEQ   = LinearSegmentedColormap.from_list('optifull_seq', RAMP)
DPI        = 150


def _a_png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=DPI, bbox_inches='tight', facecolor='white')
    return buf.getvalue()


def _ejes(fig, titulo):
    ax = fig.add_subplot(111)
    ax.set_title(titulo, loc='left', fontsize=11, fontweight='bold', color=INK, pad=12)
    for lado in ('top', 'right'):
        ax.spines[lado].set_visible(False)
    for lado in ('left', 'bottom'):
        ax.spines[lado].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
    ax.set_axisbelow(True)
    return ax


def _barras(spec):
    labels, valores = spec['labels'], spec['valores']
    horizontal = spec.get('horizontal', False)
    alto = max(3.0, 0.32 * len(labels) + 1.2) if horizontal else 3.4
    fig = Figure(figsize=(7.5, alto))
    ax = _ejes(fig, spec['titulo'])
    pos = np.arange(len(labels))
    if horizontal:
        barras = ax.barh(pos, valores, color=BRAND, height=0.62)
        ax.set_yticks(pos, labels)
        ax.invert_yaxis()
        ax.xaxis.grid(True, color=GRID, linewidth=0.6)
        if spec.get('ylabel'):
            ax.set_xlabel(spec['ylabel'], color=MUTED, fontsize=8.5)
    else:
        barras = ax.bar(pos, valores, color=BRAND, width=0.6)
        ax.set_xticks(pos, labels, rotation=0 if len(labels) <= 8 else 45,
                      ha='center' if len(labels) <= 8 else 'right')
        ax.yaxis.grid(True, color=GRID, linewidth=0.6)
        if spec.get('ylabel'):
            ax.set_ylabel(spec['ylabel'], color=MUTED, fontsize=8.5)
    if len(labels) <= 14:
        ax.bar_label(barras, fmt='%g', padding=3, fontsize=8, color=INK)
    return _a_png(fig)


def _linea(spec):
    fig = Figure(figsize=(7.5, 3.4))
    ax = _ejes(fig, spec['titulo'])
    x = np.arange(len(spec['labels']))
    ax.plot(x, spec['valores'], color=BRAND_DEEP, linewidth=1.8, marker='o', markersize=3.5)
    ax.fill_between(x, spec['valores'], color=BRAND, alpha=0.12)
    paso = max(1, len(x) // 10)
    ax.set_xticks(x[::paso], [spec['labels'][i] for i in range(0, len(x), paso)], rotation=45, ha='right')
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_ylim(bottom=0)
    if spec.get('ylabel'):
        ax.set_ylabel(spec['ylabel'], color=MUTED, fontsize=8.5)
    return _a_png(fig)


def _matriz(spec):
    """Matriz dia x hora (congestion). Celdas sin datos en gris claro; los
    rangos pico se remarcan con un borde oscuro."""
    fig = Figure(figsize=(8.5, 3.4))
    ax = _ejes(fig, spec['titulo'])
    datos = np.ma.masked_where(~np.array(spec['con_datos'], dtype=bool), np.array(spec['matriz'], dtype=float))
    cmap = CMAP_SEQ.copy()
    cmap.set_bad('#f1f2f8')
    img = ax.imshow(datos, cmap=cmap, aspect='auto', vmin=0)
    ax.set_xticks(range(24), [str(h) for h in range(24)])
    ax.set_yticks(range(len(spec['filas'])), spec['filas'])
    ax.set_xlabel('Hora del día', color=MUTED, fontsize=8.5)
    for lado in ax.spines.values():
        lado.set_visible(False)
    for fila, h0, h1 in spec.get('picos', []):
        ax.add_patch(Rectangle((h0 - 0.5, fila - 0.5), h1 - h0 + 1, 1, fill=False, edgecolor=INK, linewidth=1.4))
    cb = fig.colorbar(img, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label('personas (promedio)', color=MUTED, fontsize=8)
    cb.ax.tick_params(labelsize=8, colors=MUTED, length=0)
    cb.outline.set_visible(False)
    return _a_png(fig)


def grafico_png(spec):
    return {'bar': _barras, 'line': _linea, 'heat': _matriz}[spec['tipo']](spec)

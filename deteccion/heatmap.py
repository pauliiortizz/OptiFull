"""Construccion, render y estadisticas del mapa de calor acumulativo."""
import json

import cv2
import numpy as np


def _make_gaussian(radius: int) -> np.ndarray:
    size = radius * 2 + 1
    x = np.arange(size) - radius
    g = np.exp(-(x ** 2) / (2 * (radius / 3) ** 2))
    kernel = np.outer(g, g)
    return (kernel / kernel.max()).astype(np.float32)


class HeatmapBuilder:
    """Acumula calor por centroide detectado, y calcula/exporta las
    estadisticas y las imagenes derivadas al final de la corrida."""

    def __init__(self, frame_w: int, frame_h: int, gaussian_radius: int) -> None:
        self.frame_w    = frame_w
        self.frame_h    = frame_h
        self.radius     = gaussian_radius
        self.accumulator = np.zeros((frame_h, frame_w), dtype=np.float32)
        self.kernel      = _make_gaussian(gaussian_radius)
        self.total_detecciones = 0

    def agregar_punto(self, cx: int, cy: int) -> None:
        cx, cy, kr = int(cx), int(cy), self.radius
        h, w = self.accumulator.shape
        ky1, ky2 = max(0, cy - kr), min(h, cy + kr + 1)
        kx1, kx2 = max(0, cx - kr), min(w, cx + kr + 1)
        gy1 = ky1 - (cy - kr)
        gy2 = gy1 + (ky2 - ky1)
        gx1 = kx1 - (cx - kr)
        gx2 = gx1 + (kx2 - kx1)
        self.accumulator[ky1:ky2, kx1:kx2] += self.kernel[gy1:gy2, gx1:gx2]
        self.total_detecciones += 1

    def esta_vacio(self) -> bool:
        return self.accumulator.max() == 0

    def render(self, background=None, alpha_bg: float = 0.5) -> np.ndarray:
        hm = self.accumulator.copy()
        if hm.max() > 0:
            hm /= hm.max()
        hm_color = cv2.applyColorMap((hm * 255).astype(np.uint8), cv2.COLORMAP_JET)
        if background is not None:
            return cv2.addWeighted(background, alpha_bg, hm_color, 1 - alpha_bg, 0)
        return hm_color

    def calcular_stats(self, zonas: list, umbral_pct: float, grid_size: int) -> dict:
        """Estadisticas del acumulador: valor maximo, punto mas caliente,
        porcentaje de area activa, concentracion, y zona con mas calor."""
        accumulator = self.accumulator
        valor_maximo = float(accumulator.max())
        hm_norm      = accumulator / valor_maximo

        flat_idx = accumulator.argmax()
        punto_max_y, punto_max_x = np.unravel_index(flat_idx, accumulator.shape)

        umbral          = valor_maximo * umbral_pct
        area_activa_pct = float((accumulator > umbral).sum() / accumulator.size * 100)

        flat    = accumulator.flatten()
        activos = flat[flat > 0]
        if len(activos) > 0:
            top_umbral    = np.percentile(activos, 90)
            concentracion = float(flat[flat >= top_umbral].sum() / flat.sum())
        else:
            concentracion = 0.0

        zona_id_mas_caliente = None
        if zonas:
            max_calor, mejor_zona = -1, None
            for z in zonas:
                mask = np.zeros((self.frame_h, self.frame_w), dtype=np.uint8)
                pts  = np.array(z["poligono"], dtype=np.int32)
                cv2.fillPoly(mask, [pts], 1)
                calor = float((accumulator * mask).sum())
                if calor > max_calor:
                    max_calor, mejor_zona = calor, z["id"]
            zona_id_mas_caliente = mejor_zona

        matriz_small = cv2.resize(hm_norm, (grid_size, grid_size))
        matriz_json  = json.dumps([[round(float(v), 4) for v in row] for row in matriz_small])

        return {
            "valor_maximo":         round(valor_maximo, 4),
            "hm_norm":              hm_norm,
            "punto_max_x":          int(punto_max_x),
            "punto_max_y":          int(punto_max_y),
            "area_activa_pct":      round(area_activa_pct, 2),
            "concentracion":        round(concentracion, 4),
            "zona_id_mas_caliente": zona_id_mas_caliente,
            "matriz_json":          matriz_json,
            "resolucion":           grid_size,
        }

    def guardar_imagenes(self, camara_id, inicio_dt, last_frame, hm_norm: np.ndarray) -> tuple:
        """Escribe los PNG puro/overlay a disco y devuelve sus rutas."""
        hm_uint8    = (hm_norm * 255).astype(np.uint8)
        hm_color    = cv2.applyColorMap(hm_uint8, cv2.COLORMAP_JET)
        ts_str      = inicio_dt.strftime("%Y%m%d_%H%M%S")
        img_puro    = f"heatmap_puro_{camara_id}_{ts_str}.png"
        img_overlay = f"heatmap_overlay_{camara_id}_{ts_str}.png"

        cv2.imwrite(img_puro, hm_color)
        if last_frame is not None:
            overlay = cv2.addWeighted(last_frame, 0.4, hm_color, 0.6, 0)
            cv2.imwrite(img_overlay, overlay)
            print(f"[Heatmap] Guardado: {img_overlay}")
        print(f"[Heatmap] Guardado: {img_puro}")

        return img_puro, img_overlay

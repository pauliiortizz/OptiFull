// ── Plano esquemático de tienda — heatmap / trayectorias / zonas ───────────
// Dibuja un layout arquitectónico simplificado (wireframe) y superpone,
// según el modo activo, el mapa de calor, los vectores de trayectoria o el
// resaltado de ROIs. Todo en SVG para mantenerlo nítido a cualquier escala.

import { useEffect, useMemo, useRef, useState } from "react";

const VB_W = 760, VB_H = 460;

// Layout dibujado a mano sobre el plano real del local (tienda Full): el
// rectangulo grande es toda la tienda, abajo a la izquierda la zona de caja,
// arriba a la izquierda las 3 góndolas, a la derecha las mesas de clientes y
// el ingreso en el muro superior. Coordenadas en el sistema del viewBox.
const STORE = { x1: 30, y1: 28, x2: 730, y2: 432 };
const DOOR  = { x: 349, w: 107, h: 32 }; // hueco/alcoba de ingreso sobre el muro superior

// Zonas ROI del plano — coordenadas del polígono en el sistema del viewBox.
// 'tipoReal' mapea cada ROI del esquema visual al 'tipo' real de la tabla
// 'zonas' en Postgres (ver /reportes/permanencia-por-zona) -- el schema solo
// agrupa permanencia real en 3 categorías (caja / gondola / otro), así que
// Mesas usa el valor real de 'otro' (Salón/piso general). El ingreso se dibuja como puerta en el muro, sin zona.
// El numero mostrado sobre cada ROI en modo "zones" viene SIEMPRE de datos
// reales via la prop 'zonasReales' (ver DashboardPage) -- nunca hardcodeado.
export const STORE_ZONES = [
  {
    id: "gondolas", roi: "ROI-01", label: "Góndolas", filterKey: "aisles",
    tipoReal: "gondola", tint: "106,114,207", // periwinkle pastel
    poly: [[32, 30], [290, 30], [290, 228], [32, 228]],
    labelAt: [46, 218],
  },
  {
    id: "cajas", roi: "ROI-02", label: "Caja", filterKey: "checkout",
    tipoReal: "caja", tint: "198,138,62", // apricot pastel
    poly: [[32, 238], [390, 238], [390, 430], [32, 430]],
    labelAt: [46, 256],
  },
  {
    id: "mesas", roi: "ROI-03", label: "Sector Mesas", filterKey: "all",
    tipoReal: "otro", tint: "53,144,112", // sage pastel
    orient: "giro90", // como se ve la zona desde la camara fuente (ver ORIENTACIONES)
    poly: [[475, 30], [728, 30], [728, 430], [425, 430], [425, 100], [475, 100]],
    labelAt: [598, 396],
  },
];

// Góndolas (rosa en el dibujo) — solo mobiliario para el plano. Sin métricas
// propias: el schema real no distingue góndolas individuales, solo el tipo de
// zona agregado (ver STORE_ZONES.tipoReal).
export const GONDOLA_AISLES = [
  { id: "g1", x: 32,  y: 39, w: 50, h: 158 },
  { id: "g2", x: 130, y: 65, w: 50, h: 132 },
  { id: "g3", x: 219, y: 65, w: 46, h: 120 },
];

// Mesas de clientes (azul en el dibujo): [x, y, ancho, alto].
const MESAS = [
  [482, 56, 81, 66], [607, 49, 84, 63],
  [495, 160, 94, 69], [623, 151, 87, 73],
  [516, 279, 68, 53], [659, 265, 48, 74],
  [433, 352, 147, 60],
];


// ── Calor dentro de cada zona ──────────────────────────────────────────────
// El backend (/api/heatmap/plano) entrega, por tipo de zona, el recorte del mapa de calor de
// UNA camara fuente (grilla 64x64 sobre un cuadro de 1920x1080, celdas fuera de la zona = 0).
// Aca se traslada ese recorte al poligono de la zona en el croquis: cada punto del croquis se
// lleva a su posicion equivalente en la imagen de la camara y se lee el calor de ahi.
//
// ORIENTACIONES: como queda la zona de la camara respecto del croquis. Cada funcion lleva una
// posicion normalizada de la zona en el CROQUIS (pu, pv: 0-1, desde arriba-izquierda) a la
// posicion normalizada equivalente en la IMAGEN de la camara (cu, cv). Si el calor sale en
// el lugar equivocado de una zona, se cambia 'orient' de esa zona en STORE_ZONES.
//   id          la camara ve la zona con los mismos ejes que el croquis
//   giro90      arriba de la imagen = izquierda del croquis (camara mirando hacia la izquierda)
//   giro180 / giro270 / espejoH / espejoV: el resto de las combinaciones
const ORIENTACIONES = {
  id:       (pu, pv) => [pu, pv],
  giro90:   (pu, pv) => [1 - pv, pu],
  giro180:  (pu, pv) => [1 - pu, 1 - pv],
  giro270:  (pu, pv) => [pv, 1 - pu],
  espejoH:  (pu, pv) => [1 - pu, pv],
  espejoV:  (pu, pv) => [pu, 1 - pv],
};
const GRID_N = 64, CUADRO_W = 1920, CUADRO_H = 1080;
const PX_CALOR = 4;                       // unidades del viewBox por pixel de la imagen de calor
const COLD = [130, 175, 214], MID = [222, 169, 104], HOT = [217, 122, 97]; // = --heat-cold/mid/hot

function enPoligono(x, y, poly) {
  let dentro = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}
function mezclar(a, b, k) { return a.map((v, i) => v + (b[i] - v) * k); }
function colorCalor(t) { return t < 0.5 ? mezclar(COLD, MID, t / 0.5) : mezclar(MID, HOT, (t - 0.5) / 0.5); }

// Lee el calor del recorte 'c' en la posicion (X, Y) del cuadro de 1920x1080 (interpolacion bilineal).
function leerCalor(c, X, Y) {
  const gx = (X / CUADRO_W) * GRID_N - 0.5 - c.origen[0];
  const gy = (Y / CUADRO_H) * GRID_N - 0.5 - c.origen[1];
  const x0 = Math.floor(gx), y0 = Math.floor(gy), fx = gx - x0, fy = gy - y0;
  const v = (x, y) => (c.grid[y]?.[x] ?? 0);
  return v(x0, y0) * (1 - fx) * (1 - fy) + v(x0 + 1, y0) * fx * (1 - fy)
       + v(x0, y0 + 1) * (1 - fx) * fy + v(x0 + 1, y0 + 1) * fx * fy;
}

// Imagen (data URL) del calor de una zona, del tamano del rectangulo que la contiene en el croquis.
// El color es RELATIVO a la zona (lo mas caliente de la zona = rojo) para que se vea que parte esta
// mas caliente; la opacidad escala con el pico absoluto de la zona (c.pico) para que una zona fria
// no parezca tan intensa como una caliente.
function imagenCalorZona(zona, c, norm = c?.pico, factorIntensidad = c?.pico) {
  if (typeof document === "undefined" || !c?.grid?.length || !(norm > 0)) return null;
  const xs = zona.poly.map((p) => p[0]), ys = zona.poly.map((p) => p[1]);
  const x0 = Math.min(...xs), y0 = Math.min(...ys), x1 = Math.max(...xs), y1 = Math.max(...ys);
  const W = Math.ceil((x1 - x0) / PX_CALOR), H = Math.ceil((y1 - y0) / PX_CALOR);
  const canvas = document.createElement("canvas");
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(W, H);
  const orient = ORIENTACIONES[zona.orient || "id"] || ORIENTACIONES.id;
  const factor = 0.4 + 0.6 * Math.min(1, factorIntensidad);
  for (let py = 0; py < H; py++) {
    for (let px = 0; px < W; px++) {
      const x = x0 + (px + 0.5) * PX_CALOR, y = y0 + (py + 0.5) * PX_CALOR;
      if (!enPoligono(x, y, zona.poly)) continue;
      const [cu, cv] = orient((x - x0) / (x1 - x0), (y - y0) / (y1 - y0));
      const X = c.bbox.x0 + cu * (c.bbox.x1 - c.bbox.x0), Y = c.bbox.y0 + cv * (c.bbox.y1 - c.bbox.y0);
      // Raiz cuadrada: los mapas de calor son muy puntiagudos (un maximo fuerte y casi todo el
      // resto cerca de 0); sin comprimir, solo se veria el punto mas caliente.
      const rel = Math.sqrt(Math.min(1, Math.max(0, leerCalor(c, X, Y) / norm)));
      if (rel < 0.22) continue;
      const [r, g, b] = colorCalor(rel);
      const o = (py * W + px) * 4;
      img.data[o] = r; img.data[o + 1] = g; img.data[o + 2] = b;
      img.data[o + 3] = Math.round(255 * Math.min(0.95, (0.3 + 0.65 * rel) * factor));
    }
  }
  ctx.putImageData(img, 0, 0);
  return { href: canvas.toDataURL("image/png"), x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

// ── Calor por hora del dia, promedio de todos los dias (reproduccion) ──────────
// /api/heatmap/plano/tiempo entrega, por zona, las posiciones de TODOS los dias juntos agrupadas en
// celdas de la grilla de 64x64 y bloques horarios de 5 min: [bloque, columna, fila, cantidad].
// El calor de una hora es la suma de los bloques de la ventana elegida dividida por la cantidad de
// dias con datos de esa camara (= promedio por dia), repartida con un suavizado gaussiano. Despues
// se traslada al croquis con el mismo codigo que el calor acumulado (imagenCalorZona).
const BLOQUE_SEG = 300;   // = BLOQUE_SEG de api/plano_calor.py
const VENTANA_MIN = 30;   // ventana movil: los 30 minutos previos a la hora elegida
const PASO_MIN = 10;      // cada cuantos minutos se mide el pico para fijar la escala
const SIGMA = 1.3, RADIO = 3;

function gridDeCeldas(celdas, dias, segIni, segFin) {
  const g = new Float32Array(GRID_N * GRID_N);
  let n = 0;
  for (const [bloque, col, fila, cant] of celdas) {
    const seg = bloque * BLOQUE_SEG;
    if (seg < segIni || seg >= segFin) continue;
    const peso = cant / Math.max(1, dias);
    n += peso;
    for (let j = fila - RADIO; j <= fila + RADIO; j++) {
      if (j < 0 || j >= GRID_N) continue;
      for (let i = col - RADIO; i <= col + RADIO; i++) {
        if (i < 0 || i >= GRID_N) continue;
        g[j * GRID_N + i] += peso * Math.exp(-((i - col) ** 2 + (j - fila) ** 2) / (2 * SIGMA * SIGMA));
      }
    }
  }
  return { g, n };
}
function maxGrid(g) { let m = 0; for (let i = 0; i < g.length; i++) if (g[i] > m) m = g[i]; return m; }
function filasDeGrid(g) { return Array.from({ length: GRID_N }, (_, j) => g.subarray(j * GRID_N, (j + 1) * GRID_N)); }

// Ventana [segIni, segFin) para el minuto 'minuto' del dia: los ultimos VENTANA_MIN o todo lo anterior.
function ventanaSeg(minuto, acumulado) {
  return [acumulado ? 0 : (minuto - VENTANA_MIN) * 60, minuto * 60 + 1];
}

// Escala de una zona: el pico mas alto que alcanza la ventana a lo largo del dia tipico, asi el color
// de cada hora se compara contra el dia entero (y se nota cuando hay mas o menos actividad).
function escalaDelDia(zt, rango, acumulado) {
  if (acumulado) return maxGrid(gridDeCeldas(zt.celdas, zt.dias, 0, 24 * 3600 + 1).g);
  let k = 0;
  for (let m = rango.desde; m <= rango.hasta; m += PASO_MIN) {
    const [a, b] = ventanaSeg(m, false);
    k = Math.max(k, maxGrid(gridDeCeldas(zt.celdas, zt.dias, a, b).g));
  }
  return k;
}

// ── Recorridos promedio de los clientes (flechas) ─────────────────────────────
// /api/heatmap/plano/flujo entrega, por zona, los recorridos de clientes de TODOS los dias juntos,
// partidos en tramos dentro de esa zona y simplificados a 6 puntos. Aca se trasladan al croquis (con
// la misma orientacion que el calor), se toman los de la ventana de tiempo elegida, se agrupan los
// que siguen una ruta parecida y se dibuja una flecha por cada ruta frecuente: el recorrido promedio
// del grupo. Nunca se dibujan los recorridos sueltos.
const ORIENTACIONES_INV = {   // de la posicion en la IMAGEN de la camara (cu, cv) a la zona del CROQUIS (pu, pv)
  id:       (cu, cv) => [cu, cv],
  giro90:   (cu, cv) => [cv, 1 - cu],
  giro180:  (cu, cv) => [1 - cu, 1 - cv],
  giro270:  (cu, cv) => [1 - cv, cu],
  espejoH:  (cu, cv) => [1 - cu, cv],
  espejoV:  (cu, cv) => [cu, 1 - cv],
};
const RUTAS_POR_ZONA = 2;        // como maximo 2 flechas por zona
const RUTA_MIN_REL = 0.35;       // una ruta secundaria debe tener al menos el 35% de las personas de la principal
const RUTA_MIN_PERSONAS = 2;     // y nunca menos de 2 recorridos
const RUTA_AGRUPAR = 0.16;       // dos tramos son "la misma ruta" si distan menos del 16% de la diagonal de la zona
const RUTA_LARGO_MIN = 28;       // una flecha mas corta que esto (unidades del croquis) no se dibuja

// Pasa los tramos de una zona de coordenadas de la camara a coordenadas del croquis.
function tramosEnCroquis(zona, zt) {
  const xs = zona.poly.map((q) => q[0]), ys = zona.poly.map((q) => q[1]);
  const x0 = Math.min(...xs), y0 = Math.min(...ys), x1 = Math.max(...xs), y1 = Math.max(...ys);
  const inv = ORIENTACIONES_INV[zona.orient || "id"] || ORIENTACIONES_INV.id;
  const clamp = (v) => Math.min(1, Math.max(0, v));
  const bb = zt.bbox;
  return {
    diag: Math.hypot(x1 - x0, y1 - y0),
    tramos: zt.tramos.map(([minuto, plano]) => {
      const pts = [];
      for (let i = 0; i < plano.length; i += 2) {
        const cu = ((plano[i] / 1000) * CUADRO_W - bb.x0) / (bb.x1 - bb.x0);
        const cv = ((plano[i + 1] / 1000) * CUADRO_H - bb.y0) / (bb.y1 - bb.y0);
        const [pu, pv] = inv(clamp(cu), clamp(cv));
        pts.push([x0 + pu * (x1 - x0), y0 + pv * (y1 - y0)]);
      }
      return { minuto, pts };
    }),
  };
}

function distRutas(a, b) {
  let d = 0;
  for (let i = 0; i < a.length; i++) d += Math.hypot(a[i][0] - b[i][0], a[i][1] - b[i][1]);
  return d / a.length;
}

// Agrupa los tramos en rutas: cada tramo se une a la ruta mas cercana si se parece (distancia media
// punto a punto menor al umbral); si no, abre una ruta nueva. La ruta es el PROMEDIO de sus tramos.
function agruparRutas(tramos, diag) {
  const grupos = [];
  for (const t of tramos) {
    let mejor = null, mejorD = RUTA_AGRUPAR * diag;
    for (const g of grupos) {
      const d = distRutas(t.pts, g.media);
      if (d < mejorD) { mejor = g; mejorD = d; }
    }
    if (!mejor) {
      mejor = { suma: t.pts.map(() => [0, 0]), media: t.pts.map((q) => [...q]), n: 0 };
      grupos.push(mejor);
    }
    t.pts.forEach((q, i) => { mejor.suma[i][0] += q[0]; mejor.suma[i][1] += q[1]; });
    mejor.n += 1;
    mejor.media = mejor.suma.map(([sx, sy]) => [sx / mejor.n, sy / mejor.n]);
  }
  return grupos;
}

// Las rutas que se dibujan para un instante: solo las mas frecuentes de cada zona.
function flechasDelInstante(flujoCroquis, minuto, acumulado) {
  const desde = acumulado ? -Infinity : minuto - VENTANA_MIN;
  const flechas = [];
  for (const [tipo, z] of Object.entries(flujoCroquis)) {
    const enVentana = z.tramos.filter((t) => t.minuto >= desde && t.minuto <= minuto);
    const grupos = agruparRutas(enVentana, z.diag).sort((a, b) => b.n - a.n);
    const mejor = grupos[0]?.n || 0;
    for (const g of grupos.slice(0, RUTAS_POR_ZONA)) {
      if (g.n < Math.max(RUTA_MIN_PERSONAS, RUTA_MIN_REL * mejor)) continue;
      const largo = g.media.slice(1).reduce((s, q, i) => s + Math.hypot(q[0] - g.media[i][0], q[1] - g.media[i][1]), 0);
      if (largo < RUTA_LARGO_MIN) continue;
      flechas.push({ tipo, camara: z.camara, pts: g.media, n: g.n, porDia: g.n / Math.max(1, z.dias) });
    }
  }
  const max = Math.max(1, ...flechas.map((f) => f.n));
  return flechas.map((f) => ({ ...f, rel: f.n / max, principal: f.n === max }));
}

// Curva suave (Catmull-Rom) que pasa por los puntos de la ruta.
function curvaSuave(p) {
  let d = `M${p[0][0].toFixed(1)},${p[0][1].toFixed(1)}`;
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[Math.max(0, i - 1)], p1 = p[i], p2 = p[i + 1], p3 = p[Math.min(p.length - 1, i + 2)];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

// Devuelve 'valor' pero actualizandolo como maximo una vez cada 'ms' (el primer cambio pasa enseguida y
// el ultimo siempre llega). Las flechas se dibujan de a poco (~1,4 s): si se rehicieran en cada paso del
// reproductor (cada paso) no llegarian a completarse nunca; se espera mas que el dibujo (~1,4 s) para que se vean completas.
function useEspaciado(valor, ms) {
  const [v, setV] = useState(valor);
  const ultimo = useRef(0), timer = useRef(null), pendiente = useRef(valor);
  useEffect(() => {
    pendiente.current = valor;
    const espera = ms - (Date.now() - ultimo.current);
    if (espera <= 0) {
      ultimo.current = Date.now();
      setV(valor);
    } else if (!timer.current) {
      timer.current = setTimeout(() => { timer.current = null; ultimo.current = Date.now(); setV(pendiente.current); }, espera);
    }
  }, [valor, ms]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return v;
}

// Punta de flecha propia (en vez de un <marker>): asi aparece recien cuando la linea termino de dibujarse.
function puntaDeFlecha(pts) {
  const [x, y] = pts[pts.length - 1], [xa, ya] = pts[pts.length - 2];
  return { x, y, grados: (Math.atan2(y - ya, x - xa) * 180) / Math.PI };
}

function polyToPoints(poly) {
  return poly.map((p) => p.join(",")).join(" ");
}
function polyCenter(poly) {
  const x = poly.reduce((s, p) => s + p[0], 0) / poly.length;
  const y = poly.reduce((s, p) => s + p[1], 0) / poly.length;
  return [x, y];
}

// 'zonasReales': mapa tipo -> {pct, promedio_min, visitantes}, tal cual lo
// entrega /reportes/permanencia-por-zona (ver useZonasPermanencia en App.jsx).
// null/undefined mientras carga -- el ROI muestra "—" en vez de inventar un
// numero, y nunca cae de nuevo a un valor hardcodeado.
// 'calorReal': respuesta de /api/heatmap/plano ({zonas: {tipo: {intensidad, share_pct, camaras}}}),
// el calor de cada camara medido por zona y combinado entre camaras (ver api/plano_calor.py).
// null mientras carga o si falla -- en ese caso no se dibuja calor (nunca uno de relleno).
// 'calorTiempo' ({zonas, rango}, de /api/heatmap/plano/tiempo), 'minuto' (minuto del dia que se esta
// mirando) y 'acumulado' reproducen como cambia el calor durante un dia; si 'calorTiempo' no esta, se
// usa el calor acumulado de 'calorReal'. 'flujo' ({zonas}, de /api/heatmap/plano/flujo) alimenta las
// flechas del modo Trayectorias con el recorrido promedio de los clientes en la misma ventana de tiempo.
export function FloorPlan({ mode = "heat", opacity = 80, roiFilter = "all", zonasReales = null, calorReal = null,
  calorTiempo = null, minuto = 0, acumulado = false, flujo = null }) {
  const heatOpacity = mode === "heat" ? opacity / 100 : 0;
  const vecOpacity  = mode === "vectors" ? Math.max(0.25, opacity / 100) : 0;
  const zoneEmph    = mode === "zones";

  // Tramos de recorrido ya trasladados al croquis (una vez por carga de datos).
  const flujoCroquis = useMemo(() => {
    if (!flujo?.zonas) return null;
    const r = {};
    for (const z of STORE_ZONES) {
      const zt = flujo.zonas[z.tipoReal];
      if (z.sinCalor || !zt?.tramos?.length) continue;
      r[z.id] = { ...tramosEnCroquis(z, zt), camara: zt.camara_id, dias: zt.dias };
    }
    return r;
  }, [flujo]);

  // Las pocas flechas del instante elegido (rutas frecuentes, no recorridos sueltos).
  // Se actualizan de forma espaciada y, si una ruta sigue siendo la misma que en el instante anterior (se
  // parece a una de las que ya estaban), conserva su 'id': el elemento SVG no se recrea y no se vuelve a
  // dibujar. Solo se dibujan de nuevo las rutas que aparecen.
  const minutoFlechas = useEspaciado(minuto, 3000);
  const idsRef = useRef({ previas: [], n: 0 });
  const flechas = useMemo(() => {
    if (!flujoCroquis) return [];
    const usadas = new Set();
    const nuevas = flechasDelInstante(flujoCroquis, minutoFlechas, acumulado).map((f) => {
      let mejor = null, mejorD = 0.25 * flujoCroquis[f.tipo].diag;
      for (const q of idsRef.current.previas) {
        if (q.tipo !== f.tipo || usadas.has(q.id)) continue;
        const d = distRutas(f.pts, q.pts);
        if (d < mejorD) { mejor = q; mejorD = d; }
      }
      const id = mejor ? mejor.id : `${f.tipo}-${++idsRef.current.n}`;
      usadas.add(id);
      return { ...f, id };
    });
    idsRef.current.previas = nuevas;
    return nuevas;
  }, [flujoCroquis, minutoFlechas, acumulado]);

  // Escala del dia por zona (costosa: se calcula una vez por dia/modo, no en cada instante).
  const escalas = useMemo(() => {
    if (!calorTiempo?.zonas) return null;
    const r = {};
    for (const [tipo, zt] of Object.entries(calorTiempo.zonas)) {
      r[tipo] = escalaDelDia(zt, calorTiempo.rango || { desde: 0, hasta: 1440 }, acumulado);
    }
    return r;
  }, [calorTiempo, acumulado]);

  // Una imagen de calor por zona para el instante actual (o el acumulado, si no hay datos con hora).
  // 'info' guarda lo que muestra la etiqueta: cuanto calor hay ahora respecto del pico del dia.
  const { calorPorZona, infoZona } = useMemo(() => {
    const imgs = {}, info = {};
    for (const z of STORE_ZONES) {
      if (z.sinCalor) continue;
      if (calorTiempo?.zonas) {
        const zt = calorTiempo.zonas[z.tipoReal];
        if (!zt) { info[z.id] = { sinDatos: true }; continue; }
        const [a, b] = ventanaSeg(minuto, acumulado);
        const { g, n } = gridDeCeldas(zt.celdas, zt.dias, a, b);
        const k = escalas?.[z.tipoReal] || 0;
        const pico = maxGrid(g);
        info[z.id] = { camara: zt.camara_id, dias: zt.dias, muestras: Math.round(n), pct: k > 0 ? Math.round((pico / k) * 100) : 0 };
        // La escala satura al 40% del pico del dia: una persona parada en la caja dispara el pico
        // y, sin esto, el resto de la actividad quedaria casi invisible al lado.
        const im = imagenCalorZona(z, { grid: filasDeGrid(g), origen: [0, 0], bbox: zt.bbox }, k * 0.4, 1);
        if (im) imgs[z.id] = im;
      } else {
        const c = calorReal?.zonas?.[z.tipoReal];
        const im = imagenCalorZona(z, c);
        if (im) imgs[z.id] = im;
        if (c) info[z.id] = { camara: c.camara_id, pct: Math.round(c.pico * 100), estatico: true, share: c.share_pct };
      }
    }
    return { calorPorZona: imgs, infoZona: info };
  }, [calorReal, calorTiempo, escalas, minuto, acumulado]);

  return (
    <svg viewBox={`0 0 ${VB_W} ${VB_H}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet"
      style={{ display: "block" }}>
      <defs>
        <pattern id="fp-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0H0V20" fill="none" stroke="var(--line)" strokeOpacity="0.5" />
        </pattern>
        {/* Calor por zona: recortado al poligono de la zona, con un leve suavizado. */}
        {STORE_ZONES.map((z) => calorPorZona[z.id] && (
          <clipPath key={z.id} id={`fp-clip-${z.id}`}><polygon points={polyToPoints(z.poly)} /></clipPath>
        ))}
        <filter id="fp-suave" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="6" /></filter>
      </defs>

      {/* Hoja de plano — fondo técnico con grilla */}
      <rect x="0" y="0" width={VB_W} height={VB_H} fill="var(--bg-3)" />
      <rect x="0" y="0" width={VB_W} height={VB_H} fill="url(#fp-grid)" />

      {/* Muro exterior — con hueco para el ingreso (alcoba en el muro superior) */}
      <g stroke="var(--plan-wall)" strokeWidth="1.8" fill="none">
        <path d={`M${DOOR.x},${STORE.y1} L${STORE.x1},${STORE.y1} L${STORE.x1},${STORE.y2} L${STORE.x2},${STORE.y2} L${STORE.x2},${STORE.y1} L${DOOR.x + DOOR.w},${STORE.y1}`} />
        <path d={`M${DOOR.x},${STORE.y1} L${DOOR.x},${STORE.y1 + DOOR.h} L${DOOR.x + DOOR.w},${STORE.y1 + DOOR.h} L${DOOR.x + DOOR.w},${STORE.y1}`} strokeWidth="1.4" />
      </g>
      {/* Puerta — indicador de ingreso */}
      <g stroke="var(--fg-3)" strokeWidth="1.1" fill="none">
        <path d={`M${DOOR.x + DOOR.w / 2},${STORE.y1 + 7} L${DOOR.x + DOOR.w / 2 - 7},${STORE.y1 + 19} M${DOOR.x + DOOR.w / 2},${STORE.y1 + 7} L${DOOR.x + DOOR.w / 2 + 7},${STORE.y1 + 19}`}
          strokeLinecap="round" opacity="0.7" />
      </g>

      {/* Mobiliario — góndolas. Borde nitido (slate-600) + relleno suave
          (slate-100) para que el mobiliario se lea como objeto solido, no
          como un bloque gris difuso. */}
      {GONDOLA_AISLES.map((g) => (
        <rect key={g.id} x={g.x} y={g.y} width={g.w} height={g.h} rx="1"
          fill="var(--plan-fill)" stroke="var(--plan-line)" strokeWidth="1.4" />
      ))}
      {GONDOLA_AISLES.map((g) => (
        <line key={g.id + "-ln"} x1={g.x + g.w / 2} y1={g.y + 8} x2={g.x + g.w / 2} y2={g.y + g.h - 8}
          stroke="var(--plan-line)" strokeWidth="1" strokeDasharray="3 4" opacity="0.5" />
      ))}

      {/* Mobiliario — mesas de clientes */}
      {MESAS.map(([x, y, w, h], i) => (
        <g key={i}>
          <rect x={x} y={y} width={w} height={h} rx="3"
            fill="var(--plan-fill)" stroke="var(--plan-line)" strokeWidth="1.4" />
          <rect x={x + 6} y={y + 6} width={w - 12} height={h - 12} rx="2"
            fill="none" stroke="var(--plan-line)" strokeWidth="1" opacity="0.4" />
        </g>
      ))}

      {/* ── Capa: mapa de calor REAL dentro de cada zona (de la camara fuente de cada zona) ── */}
      {heatOpacity > 0 && (
        <g opacity={heatOpacity}>
          {STORE_ZONES.map((z) => {
            const im = calorPorZona[z.id];
            if (!im) return null;
            return (
              <image key={z.id} href={im.href} x={im.x} y={im.y} width={im.w} height={im.h}
                preserveAspectRatio="none" clipPath={`url(#fp-clip-${z.id})`} filter="url(#fp-suave)" />
            );
          })}
        </g>
      )}

      {/* ── Capa: trayectorias — recorrido PROMEDIO de los clientes (pocas rutas frecuentes) ── */}
      {vecOpacity > 0 && (
        <g opacity={vecOpacity}>
          {flechas.map((f) => {
            const punta = puntaDeFlecha(f.pts);
            const color = f.principal ? "var(--brand)" : "var(--traffic)";
            const op = f.principal ? 0.85 : 0.55;
            return (
              // key = id de la ruta: si sigue siendo la misma, el elemento se conserva y la animacion no se repite
              <g key={f.id} opacity={op}>
                <title>{`Ruta frecuente (cámara ${f.camara}): ${f.n} recorrido${f.n === 1 ? "" : "s"} en la ventana · ≈ ${f.porDia.toFixed(1)} por día`}</title>
                <path className="fp-ruta" d={curvaSuave(f.pts)} pathLength="1" fill="none" stroke={color}
                  strokeWidth={1.8 + 1.8 * Math.sqrt(f.rel)} strokeLinecap="round" />
                <polygon className="fp-punta" points="0,0 -10,-5 -10,5" fill={color}
                  transform={`translate(${punta.x.toFixed(1)},${punta.y.toFixed(1)}) rotate(${punta.grados.toFixed(1)})`} />
              </g>
            );
          })}
          {flechas.length === 0 && (
            <text x={VB_W / 2} y={VB_H / 2} textAnchor="middle" fontFamily="var(--font-metric)" fontSize="11"
              fill="var(--fg-3)">{flujoCroquis ? "Sin rutas frecuentes en esta ventana de tiempo" : "Cargando recorridos…"}</text>
          )}
        </g>
      )}

      {/* ── Capa: ROIs — solo el contorno punteado de cada zona (el detalle va en el panel Analítica de zonas) ── */}
      {STORE_ZONES.map((z) => {
        const dim = roiFilter !== "all" && z.filterKey !== roiFilter;
        const baseOp = zoneEmph ? 0.85 : dim ? 0.12 : 0.4;
        const fillOp = zoneEmph ? 0.1 : dim ? 0.02 : 0.045;
        return (
          <g key={z.id} opacity={dim && !zoneEmph ? 0.35 : 1}>
            <polygon points={polyToPoints(z.poly)}
              fill={`rgba(${z.tint},${fillOp})`}
              stroke={`rgba(${z.tint},${baseOp})`}
              strokeWidth={zoneEmph ? 1.6 : 1.1}
              strokeDasharray="5 4" />
            {zoneEmph && !z.sinCalor && (() => {   // el Ingreso no tiene zona propia en la BD: no se muestra un % (seria el del Salon)
              const real = zonasReales?.[z.tipoReal];
              return (
                <text x={polyCenter(z.poly)[0]} y={polyCenter(z.poly)[1]} textAnchor="middle"
                  fontFamily="var(--font-metric)" fontSize="23" fontWeight="600" fill={`rgb(${z.tint})`} opacity="0.85">
                  {real ? `${real.pct}%` : "—"}
                </text>
              );
            })()}
          </g>
        );
      })}
    </svg>
  );
}

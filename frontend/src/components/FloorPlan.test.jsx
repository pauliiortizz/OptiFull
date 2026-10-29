// Pruebas del croquis de la tienda (FloorPlan): calor por zona, reproduccion por hora, flechas de
// recorridos y numeros de las zonas. FloorPlan no pide datos por su cuenta: recibe por props las
// respuestas de /api/heatmap/plano, /plano/tiempo y /plano/flujo (las pide App.jsx), asi que aca se le
// pasan objetos con la misma forma que devuelve api/plano_calor.py.
import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'
import { FloorPlan, STORE_ZONES, GONDOLA_AISLES } from './FloorPlan.jsx'

// jsdom no tiene canvas: un contexto 2D falso que guarda cada imagen que se pinta.
let pintadas
beforeEach(() => {
  pintadas = []
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => ({
    createImageData: (w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
    putImageData: vi.fn((img) => pintadas.push(img)),
  }))
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockImplementation(() => 'data:image/png;base64,CALOR')
})

const CUADRO = { x0: 0, y0: 0, x1: 1920, y1: 1080 }
const grilla = (v) => Array.from({ length: 64 }, () => Array(64).fill(v))
const opacos = (img) => { let n = 0; for (let i = 3; i < img.data.length; i += 4) if (img.data[i] > 0) n++; return n }

// Respuesta de /api/heatmap/plano: {zonas: {tipo: {camara_id, pico, share_pct, bbox, origen, grid}}}
const CALOR = {
  zonas: {
    gondola: { camara_id: 4, pico: 0.8, share_pct: 40, bbox: CUADRO, origen: [0, 0], grid: grilla(0.8) },
    otro:    { camara_id: 2, pico: 0.5, share_pct: 60, bbox: CUADRO, origen: [0, 0], grid: grilla(0.5) },
  },
  camaras: {},
}

// Respuesta de /api/heatmap/plano/tiempo: celdas [bloque de 5 min, col, fila, n] de todos los dias.
const TIEMPO = {
  rango: { desde: 600, hasta: 720 },
  zonas: {
    caja: { camara_id: 4, bbox: CUADRO, dias: 2, celdas: [[122, 32, 32, 10], [140, 20, 20, 4]] },
  },
}

// Respuesta de /api/heatmap/plano/flujo: tramos [minuto, [x1, y1, ..., x6, y6]] en milesimas del cuadro.
const diagonal = [100, 100, 260, 260, 420, 420, 580, 580, 740, 740, 900, 900]
const inversa = [900, 100, 740, 260, 580, 420, 420, 580, 260, 740, 100, 900]
const FLUJO = {
  zonas: {
    gondola: {
      camara_id: 4, bbox: CUADRO, dias: 2,
      tramos: [[600, diagonal], [610, diagonal], [620, diagonal], [605, inversa], [615, inversa]],
    },
  },
}

const imagenes = (c) => [...c.querySelectorAll('image')]
const rutas = (c) => [...c.querySelectorAll('path.fp-ruta')]
const textos = (c) => [...c.querySelectorAll('text')].map((t) => t.textContent)

describe('FloorPlan: plano base', () => {
  test('dibuja el plano con las tres zonas, las góndolas y las mesas aunque no haya datos', () => {
    const { container } = render(<FloorPlan />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('viewBox', '23 14 714 432')   // recortado al local, misma proporcion que el recuadro
    // un poligono por zona (contorno punteado)
    expect(container.querySelectorAll('polygon[stroke-dasharray="5 4"]')).toHaveLength(STORE_ZONES.length)
    expect(GONDOLA_AISLES).toHaveLength(3)
    // sin datos no se inventa calor
    expect(imagenes(container)).toHaveLength(0)
    expect(HTMLCanvasElement.prototype.getContext).not.toHaveBeenCalled()
  })
})

describe('FloorPlan: calor acumulado (/api/heatmap/plano)', () => {
  test('pinta una imagen de calor por cada zona con datos, recortada a su polígono', () => {
    const { container } = render(<FloorPlan calorReal={CALOR} opacity={70} />)
    const imgs = imagenes(container)
    expect(imgs).toHaveLength(2)   // góndolas y mesas; la caja no tiene datos
    expect(imgs.map((i) => i.getAttribute('clip-path'))).toEqual(['url(#fp-clip-gondolas)', 'url(#fp-clip-mesas)'])
    expect(imgs[0]).toHaveAttribute('href', 'data:image/png;base64,CALOR')
    expect(container.querySelector('#fp-clip-gondolas')).not.toBeNull()
    expect(container.querySelector('#fp-clip-cajas')).toBeNull()
    expect(imgs[0].parentElement).toHaveAttribute('opacity', '0.7')
    // el calor se pinta de verdad (pixeles con alfa) dentro de cada zona
    expect(pintadas).toHaveLength(2)
    for (const p of pintadas) expect(opacos(p)).toBeGreaterThan(0)
  })

  test('una zona con pico 0 o sin grilla no pinta calor', () => {
    const calor = { zonas: {
      gondola: { ...CALOR.zonas.gondola, pico: 0, grid: grilla(0) },
      caja: { camara_id: 4, pico: 0.3, bbox: CUADRO, origen: [0, 0], grid: [] },
    } }
    const { container } = render(<FloorPlan calorReal={calor} />)
    expect(imagenes(container)).toHaveLength(0)
  })

  test('las zonas frías de la grilla quedan transparentes (no se pinta todo el polígono)', () => {
    // solo una celda caliente: el resto de la zona debe quedar sin color
    const grid = grilla(0)
    grid[32][32] = 1
    render(<FloorPlan calorReal={{ zonas: { gondola: { ...CALOR.zonas.gondola, pico: 1, grid } } }} />)
    const [img] = pintadas
    const total = img.width * img.height
    expect(opacos(img)).toBeGreaterThan(0)
    expect(opacos(img)).toBeLessThan(total / 4)
  })

  test('fuera del modo calor no se muestra la capa de calor', () => {
    for (const mode of ['vectors', 'zones']) {
      const { container, unmount } = render(<FloorPlan mode={mode} calorReal={CALOR} />)
      expect(imagenes(container), mode).toHaveLength(0)
      unmount()
    }
  })
})

describe('FloorPlan: calor por hora (/api/heatmap/plano/tiempo)', () => {
  test('con datos por hora usa la ventana de los 30 minutos previos en vez del acumulado', () => {
    // 10:30 -> ventana 10:00-10:30, donde cae el bloque 122 (10:10) de la caja
    const { container } = render(<FloorPlan calorReal={CALOR} calorTiempo={TIEMPO} minuto={630} />)
    const imgs = imagenes(container)
    // solo la caja tiene datos por hora: góndolas y mesas no se pintan con el calor acumulado
    expect(imgs).toHaveLength(1)
    expect(imgs[0]).toHaveAttribute('clip-path', 'url(#fp-clip-cajas)')
    expect(opacos(pintadas.at(-1))).toBeGreaterThan(0)
  })

  test('a una hora sin actividad la zona queda sin color', () => {
    // 9:00: ningun bloque cae en la ventana 8:30-9:00
    render(<FloorPlan calorTiempo={TIEMPO} minuto={540} />)
    expect(pintadas).toHaveLength(1)
    expect(opacos(pintadas[0])).toBe(0)
  })

  test('en modo acumulado suma todo lo anterior a la hora elegida', () => {
    // 13:00 sin acumulado: la ventana 12:30-13:00 no tiene bloques
    const { rerender } = render(<FloorPlan calorTiempo={TIEMPO} minuto={780} />)
    expect(opacos(pintadas.at(-1))).toBe(0)
    rerender(<FloorPlan calorTiempo={TIEMPO} minuto={780} acumulado />)
    expect(opacos(pintadas.at(-1))).toBeGreaterThan(0)
  })

  test('sin rango en la respuesta usa el día completo para la escala', () => {
    const { container } = render(<FloorPlan calorTiempo={{ zonas: TIEMPO.zonas }} minuto={630} />)
    expect(imagenes(container)).toHaveLength(1)
  })
})

describe('FloorPlan: trayectorias (/api/heatmap/plano/flujo)', () => {
  test('mientras no llegan los recorridos avisa que están cargando', () => {
    const { container } = render(<FloorPlan mode="vectors" />)
    expect(textos(container)).toContain('Cargando recorridos…')
  })

  test('dibuja una flecha por ruta frecuente, la principal destacada', () => {
    const { container } = render(<FloorPlan mode="vectors" flujo={FLUJO} minuto={625} />)
    const r = rutas(container)
    expect(r).toHaveLength(2)
    expect(r[0]).toHaveAttribute('stroke', 'var(--brand)')
    expect(r[1]).toHaveAttribute('stroke', 'var(--traffic)')
    const titulos = [...container.querySelectorAll('title')].map((t) => t.textContent)
    expect(titulos).toEqual([
      'Ruta frecuente (cámara 4): 3 recorridos en la ventana · ≈ 1.5 por día',
      'Ruta frecuente (cámara 4): 2 recorridos en la ventana · ≈ 1.0 por día',
    ])
    // cada flecha lleva su punta
    expect(container.querySelectorAll('polygon.fp-punta')).toHaveLength(2)
    expect(textos(container)).not.toContain('Cargando recorridos…')
  })

  test('un recorrido suelto o una ruta muy corta no se dibujan', () => {
    const corto = [500, 500, 501, 501, 502, 502, 503, 503, 504, 504, 505, 505]
    const flujo = { zonas: { gondola: { ...FLUJO.zonas.gondola, tramos: [[600, diagonal], [600, corto], [601, corto]] } } }
    const { container } = render(<FloorPlan mode="vectors" flujo={flujo} minuto={610} />)
    expect(rutas(container)).toHaveLength(0)
    expect(textos(container)).toContain('Sin rutas frecuentes en esta ventana de tiempo')
  })

  test('zonas sin tramos se ignoran y el modo acumulado toma todos los recorridos previos', () => {
    const flujo = { zonas: { ...FLUJO.zonas, caja: { camara_id: 4, bbox: CUADRO, dias: 1, tramos: [] } } }
    // a las 11:00 la ventana de 30 min no tiene recorridos, pero el acumulado si
    const { container, rerender } = render(<FloorPlan mode="vectors" flujo={flujo} minuto={660} />)
    expect(rutas(container)).toHaveLength(0)
    rerender(<FloorPlan mode="vectors" flujo={flujo} minuto={660} acumulado />)
    expect(rutas(container)).toHaveLength(2)
  })

  test('las rutas de las mesas se trasladan con la orientación de su cámara', () => {
    const flujo = { zonas: { otro: { camara_id: 2, bbox: CUADRO, dias: 1, tramos: [[600, diagonal], [601, diagonal]] } } }
    const { container } = render(<FloorPlan mode="vectors" flujo={flujo} minuto={610} />)
    const [ruta] = rutas(container)
    // giro90: la diagonal de la camara (arriba-izq -> abajo-der) cae en el croquis de abajo-izq a arriba-der
    const [, x0, y0] = ruta.getAttribute('d').match(/^M([\d.]+),([\d.]+)/).map(Number)
    const [, x1, y1] = ruta.getAttribute('d').match(/ ([\d.]+),([\d.]+)$/).map(Number)
    expect(x1).toBeGreaterThan(x0)
    expect(y1).toBeLessThan(y0)
  })

  test('las flechas se actualizan como máximo cada 3 s y conservan la ruta que no cambió', () => {
    vi.useFakeTimers()
    const { container, rerender } = render(<FloorPlan mode="vectors" flujo={FLUJO} minuto={625} />)
    const antes = rutas(container)[0]
    // el reproductor avanza a las 11:00 (sin recorridos), pero el cambio espera
    rerender(<FloorPlan mode="vectors" flujo={FLUJO} minuto={700} />)
    rerender(<FloorPlan mode="vectors" flujo={FLUJO} minuto={701} />)
    expect(rutas(container)).toHaveLength(2)
    act(() => { vi.advanceTimersByTime(3000) })
    expect(rutas(container)).toHaveLength(0)
    expect(textos(container)).toContain('Sin rutas frecuentes en esta ventana de tiempo')

    // vuelve a una hora con las mismas rutas: se dibujan de nuevo, y un paso chico conserva el elemento
    act(() => { vi.advanceTimersByTime(3000) })
    rerender(<FloorPlan mode="vectors" flujo={FLUJO} minuto={625} />)
    const nueva = rutas(container)[0]
    expect(nueva).not.toBe(antes)
    act(() => { vi.advanceTimersByTime(3000) })
    rerender(<FloorPlan mode="vectors" flujo={FLUJO} minuto={626} />)
    expect(rutas(container)[0]).toBe(nueva)
  })

  test('la opacidad de las trayectorias nunca baja del 25 %', () => {
    const { container } = render(<FloorPlan mode="vectors" opacity={5} flujo={FLUJO} minuto={625} />)
    expect(rutas(container)[0].closest('g[opacity="0.25"]')).not.toBeNull()
  })
})

describe('FloorPlan: zonas (permanencia real)', () => {
  test('muestra el porcentaje real de cada zona y "—" donde no hay dato', () => {
    const zonasReales = { gondola: { pct: 45, promedio_min: 3, visitantes: 10 }, caja: { pct: 30 } }
    const { container } = render(<FloorPlan mode="zones" zonasReales={zonasReales} />)
    expect(textos(container)).toEqual(['45%', '30%', '—'])
  })

  test('mientras carga no inventa números', () => {
    const { container } = render(<FloorPlan mode="zones" />)
    expect(textos(container)).toEqual(['—', '—', '—'])
  })

  test('fuera del modo zonas no se muestran los porcentajes', () => {
    const { container } = render(<FloorPlan mode="heat" zonasReales={{ gondola: { pct: 45 } }} />)
    expect(textos(container)).toEqual([])
  })

  test('el filtro de zona atenúa las demás, salvo en el modo zonas', () => {
    const atenuadas = (c) => [...c.querySelectorAll('g[opacity="0.35"] > polygon')].length
    const { container, rerender } = render(<FloorPlan roiFilter="checkout" />)
    expect(atenuadas(container)).toBe(2)
    rerender(<FloorPlan roiFilter="all" />)
    expect(atenuadas(container)).toBe(0)
    rerender(<FloorPlan mode="zones" roiFilter="checkout" />)
    expect(atenuadas(container)).toBe(0)
  })
})

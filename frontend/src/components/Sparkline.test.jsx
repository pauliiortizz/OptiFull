// Pruebas de Sparkline, RadialGauge, KpiCard y StatTileRow (los "stat tiles" y tarjetas KPI del Dashboard).
import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Sparkline, RadialGauge, KpiCard, StatTileRow, StatTile } from './Sparkline'

const Ico = (props) => <svg data-testid="ico" {...props} />

// Devuelve los puntos [x, y] por los que pasa el trazo (M x y C ... x y C ... x y).
function puntosDelTrazo(container) {
  const d = container.querySelectorAll('path')[container.querySelectorAll('path').length - 1].getAttribute('d')
  const nums = d.replace(/[MC]/g, ' ').trim().split(/\s+/).map(Number)
  const pts = [[nums[0], nums[1]]]
  for (let i = 2; i < nums.length; i += 6) pts.push([nums[i + 4], nums[i + 5]])
  return pts
}

describe('Sparkline', () => {
  test('sin datos, con array vacío o con un solo punto no dibuja nada', () => {
    for (const data of [undefined, null, [], [7]]) {
      const { container, unmount } = render(<Sparkline data={data} />)
      expect(container.querySelector('svg'), JSON.stringify(data)).toBeNull()
      unmount()
    }
  })

  test('con dos o más puntos dibuja área, línea y el punto final con el color pedido', () => {
    const { container } = render(<Sparkline data={[1, 3, 2]} color="red" width={100} height={32} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('viewBox', '0 0 100 32')
    expect(container.querySelectorAll('path')).toHaveLength(2)
    const circulo = container.querySelector('circle')
    expect(circulo).toHaveAttribute('fill', 'red')
    // El último punto queda en el borde derecho (ancho - padding)
    expect(Number(circulo.getAttribute('cx'))).toBe(98)
    // El área usa el degradado definido en el mismo svg
    const id = container.querySelector('linearGradient').getAttribute('id')
    expect(container.querySelectorAll('path')[0].getAttribute('fill')).toBe(`url(#${id})`)
  })

  test('fill=false omite el área y deja solo la línea', () => {
    const { container } = render(<Sparkline data={[1, 2]} fill={false} />)
    expect(container.querySelectorAll('path')).toHaveLength(1)
  })

  test('el máximo queda arriba y el mínimo abajo, respetando el padding', () => {
    const { container } = render(<Sparkline data={[0, 10, 5]} width={100} height={32} />)
    const pts = puntosDelTrazo(container)
    expect(pts).toEqual([[2, 30], [50, 2], [98, 16]])
  })

  test('todos ceros: línea plana en la base, sin NaN (evita dividir por cero)', () => {
    const { container } = render(<Sparkline data={[0, 0, 0, 0]} width={100} height={32} />)
    const d = container.querySelectorAll('path')[1].getAttribute('d')
    expect(d).not.toMatch(/NaN|Infinity/)
    for (const [, y] of puntosDelTrazo(container)) expect(y).toBe(30)
  })

  test('valores negativos se escalan entre el mínimo y el máximo', () => {
    const { container } = render(<Sparkline data={[-5, 5]} width={100} height={32} />)
    expect(puntosDelTrazo(container)).toEqual([[2, 30], [98, 2]])
  })

  test('cada sparkline tiene su propio id de degradado', () => {
    const { container } = render(<><Sparkline data={[1, 2]} /><Sparkline data={[2, 1]} /></>)
    const ids = [...container.querySelectorAll('linearGradient')].map((g) => g.id)
    expect(new Set(ids).size).toBe(2)
  })
})

describe('RadialGauge', () => {
  const offset = (container) => Number(container.querySelectorAll('circle')[1].getAttribute('stroke-dashoffset'))
  const largo = (container) => Number(container.querySelectorAll('circle')[1].getAttribute('stroke-dasharray'))

  test('el arco refleja el porcentaje y se recorta entre 0 y 100', () => {
    let r = render(<RadialGauge value={50} />)
    expect(offset(r.container)).toBeCloseTo(largo(r.container) / 2)
    r.unmount()
    r = render(<RadialGauge value={150} />)
    expect(offset(r.container)).toBeCloseTo(0)
    r.unmount()
    r = render(<RadialGauge value={-20} />)
    expect(offset(r.container)).toBeCloseTo(largo(r.container))
  })
})

describe('KpiCard', () => {
  test('muestra etiqueta, valor, unidad, ícono, detalle y sparkline', () => {
    const { container } = render(
      <KpiCard label="Promedio diario" value={42} unit="únicas" delta="5 días · todas las cámaras"
        trend="up" Ico={Ico} iconClass="extra" spark={[1, 2, 3]} />,
    )
    expect(screen.getByText('Promedio diario')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('únicas')).toBeInTheDocument()
    expect(screen.getByText('5 días · todas las cámaras')).toBeInTheDocument()
    expect(screen.getByText('↑')).toBeInTheDocument()
    expect(container.querySelector('.kpi-card-icon')).toHaveClass('extra')
    expect(screen.getByTestId('ico')).toBeInTheDocument()
    expect(container.querySelector('.kpi-card-body svg')).not.toBeNull()
  })

  test('tendencia a la baja y neutra muestran su flecha; sin unidad, ícono ni datos no se rompe', () => {
    const { container, rerender } = render(<KpiCard label="Espera" value="—" trend="down" delta="baja" spark={[]} />)
    expect(screen.getByText('↓')).toBeInTheDocument()
    expect(container.querySelector('.kpi-card-unit')).toBeNull()
    expect(container.querySelector('.kpi-card-icon')).toBeNull()
    expect(container.querySelector('.kpi-card-body svg')).toBeNull()
    rerender(<KpiCard label="Espera" value={0} delta="estable" />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
    // Sin delta no hay pie (ni la raya ni el texto)
    rerender(<KpiCard label="Espera" value={0} />)
    expect(container.querySelector('.kpi-card-foot')).toBeNull()
  })
})

describe('StatTileRow', () => {
  test('muestra una tarjeta por ítem con valor, unidad, tendencia y subtítulo', () => {
    const { container } = render(<StatTileRow items={[
      { label: 'Personas hoy', value: 128, unit: 'únicas', trend: 'up', delta: '+12%', sub: 'vs. ayer', Ico },
      { label: 'Espera en caja', value: '3:20', unit: 'min', trend: 'down', delta: '-8%' },
      { label: 'Hora pico', value: '18hs', delta: 'sin datos' },
      { label: 'Sin delta', value: 0 },
    ]} />)
    expect(container.querySelectorAll('.stat-tile')).toHaveLength(4)
    expect(screen.getByText('▲ +12%')).toHaveClass('stat-tile-trend', 'up')
    expect(screen.getByText('▼ -8%')).toHaveClass('down')
    expect(screen.getByText('— sin datos')).toHaveClass('flat')
    expect(screen.getByText('vs. ayer')).toBeInTheDocument()
    expect(screen.getByText('únicas')).toBeInTheDocument()
    expect(screen.getAllByTestId('ico')).toHaveLength(1)
    // El último no tiene delta ni subtítulo
    const ultima = container.querySelectorAll('.stat-tile')[3]
    expect(ultima.querySelector('.stat-tile-trend')).toBeNull()
    expect(ultima.querySelector('.stat-tile-sub')).toBeNull()
  })

  test('delta 0 se muestra (no se confunde con "sin delta")', () => {
    render(<StatTile label="Variación" value={10} delta={0} trend="flat" />)
    expect(screen.getByText('— 0')).toBeInTheDocument()
  })

  test('sin ítems no muestra tarjetas', () => {
    const { container } = render(<StatTileRow items={[]} />)
    expect(container.querySelectorAll('.stat-tile')).toHaveLength(0)
  })
})

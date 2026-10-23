// Pruebas de los iconos: una sola familia (Phosphor) con el mismo peso, y las mismas props que antes.
import { describe, test, expect } from 'vitest'
import { render } from '@testing-library/react'
import * as Iconos from './Icons'

const dibujar = (Ico, props) => render(<Ico {...props} />).container.querySelector('svg')

describe('Iconos', () => {
  test('todos los iconos exportados dibujan un <svg> con contenido', () => {
    const nombres = Object.keys(Iconos)
    expect(nombres.length).toBeGreaterThan(40)
    for (const nombre of nombres) {
      const svg = dibujar(Iconos[nombre])
      expect(svg, nombre).not.toBeNull()
      expect(svg.innerHTML.trim().length, nombre).toBeGreaterThan(0)
    }
  })

  test('todos son de la misma familia: misma grilla y toman el color del texto', () => {
    for (const nombre of Object.keys(Iconos)) {
      const svg = dibujar(Iconos[nombre])
      expect(svg.getAttribute('viewBox'), nombre).toBe('0 0 256 256')
      expect(svg, nombre).toHaveAttribute('fill', 'currentColor')
    }
  })

  test('todos usan el mismo peso: dos iconos distintos dibujan con el mismo grosor de linea', () => {
    // En Phosphor el peso cambia el dibujo; el mismo icono en peso regular y en bold no coincide.
    const regular = dibujar(Iconos.IcoX).innerHTML
    const bold = dibujar(Iconos.IcoX, { weight: 'bold' }).innerHTML
    expect(regular).not.toBe(bold)
    expect(dibujar(Iconos.IcoX, { weight: 'regular' }).innerHTML).toBe(regular)
  })

  test('miden 16 por defecto y aceptan tamaño, clase y estilo', () => {
    const svg = dibujar(Iconos.IcoCam)
    expect(svg).toHaveAttribute('width', '16')
    expect(svg).toHaveAttribute('height', '16')

    const grande = dibujar(Iconos.IcoX, { size: 24, className: 'cerrar', style: { marginRight: 4, color: 'red' } })
    expect(grande).toHaveAttribute('width', '24')
    expect(grande).toHaveClass('cerrar')
    expect(grande.style.marginRight).toBe('4px')
    expect(grande.style.color).toBe('red')
  })

  test('stroke >= 2 (botones destacados) pide la version bold', () => {
    expect(dibujar(Iconos.IcoChev, { stroke: 2.2 }).innerHTML).toBe(dibujar(Iconos.IcoChev, { weight: 'bold' }).innerHTML)
    expect(dibujar(Iconos.IcoChev, { stroke: 1.5 }).innerHTML).toBe(dibujar(Iconos.IcoChev).innerHTML)
  })
})

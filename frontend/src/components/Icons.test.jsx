// Pruebas de los iconos: los de trazo (dibujados en JSX) y los de relleno (importados de icons/*.svg).
import { describe, test, expect } from 'vitest'
import { render } from '@testing-library/react'
import * as Iconos from './Icons'

const DE_SVG = ['IcoHome', 'IcoHeat', 'IcoTrack', 'IcoStock', 'IcoReport', 'IcoAlert', 'IcoUsers', 'IcoBox',
  'IcoDocs', 'IcoCheck', 'IcoSpinner', 'IcoDownload', 'IcoCheck2']

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

  test('los de trazo miden 16 por defecto, heredan el color y aceptan tamaño y grosor', () => {
    const svg = dibujar(Iconos.IcoCam)
    expect(svg).toHaveAttribute('width', '16')
    expect(svg).toHaveAttribute('viewBox', '0 0 16 16')
    expect(svg).toHaveAttribute('stroke', 'currentColor')
    expect(svg).toHaveAttribute('stroke-width', '1.6')

    const grande = dibujar(Iconos.IcoX, { size: 24, stroke: 2, className: 'cerrar' })
    expect(grande).toHaveAttribute('width', '24')
    expect(grande).toHaveAttribute('stroke-width', '2')
    expect(grande).toHaveClass('cerrar')
  })

  test('los de relleno se agrandan 1.25x, usan la tinta del tema y no reciben trazo', () => {
    for (const nombre of DE_SVG) {
      const svg = dibujar(Iconos[nombre], { stroke: 3 })
      expect(svg, nombre).toHaveAttribute('width', '20')
      expect(svg, nombre).toHaveAttribute('height', '20')
      expect(svg.getAttribute('viewBox'), nombre).toMatch(/^[\d.\s-]+$/)
      expect(svg.style.fill, nombre).toBe('var(--icon-ink)')
      expect(svg, nombre).not.toHaveAttribute('stroke')
      expect(svg.innerHTML, nombre).not.toMatch(/<!--/)
    }
  })

  test('el tamaño numérico en style también se agranda; el resto del estilo se respeta', () => {
    const svg = dibujar(Iconos.IcoAlert, { size: 10, style: { width: 26, height: 26, color: 'red' } })
    expect(svg).toHaveAttribute('width', '12.5')
    expect(svg.style.width).toBe('32.5px')
    expect(svg.style.height).toBe('32.5px')
    expect(svg.style.color).toBe('red')
  })

  test('un style sin medidas no deja width/height vacíos y las medidas no numéricas pasan tal cual', () => {
    const sinMedidas = dibujar(Iconos.IcoCheck2, { style: { marginRight: 4 } })
    expect(sinMedidas.style.marginRight).toBe('4px')
    expect(sinMedidas.style.width).toBe('')

    const conTexto = dibujar(Iconos.IcoBox, { style: { width: '2em' } })
    expect(conTexto.style.width).toBe('2em')
    expect(conTexto.style.height).toBe('')
  })
})

// Logo con sus versiones dia y noche (ver Logo.jsx).
import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Logo } from './Logo.jsx'

describe('Logo', () => {
  test('muestra las dos versiones del logo completo con texto alternativo', () => {
    render(<Logo className="landing-logo" />)
    const [dia, noche] = screen.getAllByRole('img', { name: 'OptiFull' })
    expect(dia).toHaveClass('logo-dia', 'landing-logo')
    expect(noche).toHaveClass('logo-noche', 'landing-logo')
    expect(dia.getAttribute('src')).toMatch(/logo-dia/)
    expect(noche.getAttribute('src')).toMatch(/logo-noche/)
  })

  test('en modo icono usa solo el circulo', () => {
    render(<Logo icono />)
    const [dia, noche] = screen.getAllByRole('img', { name: 'OptiFull' })
    expect(dia.className).toBe('logo-dia')
    expect(dia.getAttribute('src')).toMatch(/icono-dia/)
    expect(noche.getAttribute('src')).toMatch(/icono-noche/)
  })
})

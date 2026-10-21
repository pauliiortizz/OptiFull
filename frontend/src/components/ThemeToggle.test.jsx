// Boton de modo dia / noche (ver ThemeToggle.jsx y useTheme.js).
import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

let ThemeToggle
beforeEach(async () => {
  // Sin animacion (reducir movimiento) y con el modulo del tema recien cargado.
  vi.spyOn(window, 'matchMedia').mockImplementation((q) => ({
    media: q, matches: q.includes('reduced-motion'), addEventListener() {}, removeEventListener() {},
  }))
  vi.resetModules()
  ;({ ThemeToggle } = await import('./ThemeToggle.jsx'))
})

describe('ThemeToggle', () => {
  test('de dia ofrece pasar a modo noche, y al tocarlo cambia y lo recuerda', async () => {
    render(<ThemeToggle className="extra" />)
    const boton = screen.getByRole('button', { name: 'Cambiar a modo noche' })
    expect(boton).toHaveClass('theme-toggle', 'extra')
    expect(boton).toHaveAttribute('title', 'Cambiar a modo noche')
    await userEvent.click(boton)
    expect(screen.getByRole('button', { name: 'Cambiar a modo día' })).toBeInTheDocument()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('optifull-theme')).toBe('dark')
    await userEvent.click(screen.getByRole('button', { name: 'Cambiar a modo día' }))
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('optifull-theme')).toBe('light')
  })

  test('sin className solo lleva la clase base', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button').className).toBe('theme-toggle')
  })
})

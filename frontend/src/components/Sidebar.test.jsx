// Menu lateral: secciones segun el rol, navegacion, plegado y pie con el usuario (ver Sidebar.jsx).
import { describe, test, expect, vi } from 'vitest'
import { render, screen, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Sidebar } from './Sidebar.jsx'

const ADMIN = { usuario: 'ana', nombre: 'Ana María Pérez', rol: 'administrador', cargo: 'dueno' }
const EMPLEADO = { usuario: 'juan', nombre: 'Juan', rol: 'usuario', cargo: 'empleado' }

// Pantalla simulada: ancho en px para las media queries (max-width: N px), con aviso de cambio.
function pantalla(ancho) {
  const oyentes = new Set()
  const estado = { ancho }
  vi.spyOn(window, 'matchMedia').mockImplementation((q) => {
    const max = Number(/max-width:\s*(\d+)px/.exec(q)?.[1] ?? Infinity)
    return {
      media: q,
      get matches() { return estado.ancho <= max },
      addEventListener: (_, f) => oyentes.add(f),
      removeEventListener: (_, f) => oyentes.delete(f),
    }
  })
  return { cambiar(a) { estado.ancho = a; oyentes.forEach((f) => f()) } }
}

const etiquetas = (cont) => [...cont.querySelectorAll('.side-nav-item')].map((a) => a.textContent.trim())

describe('Sidebar', () => {
  test('el administrador ve todas las secciones y su cargo', () => {
    pantalla(1400)
    const { container } = render(<Sidebar usuario={ADMIN} active="dashboard" />)
    expect(etiquetas(container)).toEqual(['Dashboard', 'Productos', 'Ventas', 'Reportes', 'Alertas', 'Configuración'])
    for (const s of ['Monitoreo', 'Análisis', 'Sistema']) expect(screen.getByText(s)).toBeInTheDocument()
    expect(screen.getByText('Ana')).toBeInTheDocument()
    expect(screen.getByText('Dueño')).toBeInTheDocument()
    expect(container.querySelector('.avatar')).toHaveTextContent('AP')
  })

  test('el empleado solo ve Productos, Ventas y Alertas (sin Dashboard ni Sistema)', () => {
    pantalla(1400)
    const { container } = render(<Sidebar usuario={EMPLEADO} active="productos" />)
    expect(etiquetas(container)).toEqual(['Productos', 'Ventas', 'Alertas'])
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
    expect(screen.queryByText('Sistema')).not.toBeInTheDocument()
    expect(screen.getByText('Empleado')).toBeInTheDocument()
    expect(container.querySelector('.avatar')).toHaveTextContent('J')
  })

  test('sin usuario no muestra ninguna seccion', () => {
    pantalla(1400)
    const { container } = render(<Sidebar />)
    expect(etiquetas(container)).toEqual([])
    expect(screen.getByText('Usuario')).toBeInTheDocument()
    expect(container.querySelector('.avatar')).toHaveTextContent('?')
  })

  test('sin cargo conocido muestra Administrador o Usuario segun el rol', () => {
    pantalla(1400)
    const { rerender } = render(<Sidebar usuario={{ nombre: 'Ana', rol: 'administrador' }} />)
    expect(screen.getByText('Administrador')).toBeInTheDocument()
    rerender(<Sidebar usuario={{ nombre: 'Ana', rol: 'usuario', cargo: 'gerente' }} />)
    expect(screen.getByText('Gerente')).toBeInTheDocument()
    rerender(<Sidebar usuario={{ nombre: 'Ana', rol: 'usuario' }} />)
    expect(screen.getByText('Usuario')).toBeInTheDocument()
  })

  test('marca la seccion activa y muestra el contador de alertas', () => {
    pantalla(1400)
    const { container } = render(<Sidebar usuario={ADMIN} active="reports" alertCount={3} />)
    const activa = container.querySelector('[aria-current="page"]')
    expect(activa).toHaveTextContent('Reportes')
    expect(activa).toHaveClass('active')
    expect(container.querySelector('.side-active-pill')).toBeInTheDocument()
    const alertas = [...container.querySelectorAll('.side-nav-item')].find((a) => a.textContent.includes('Alertas'))
    expect(within(alertas).getByText('3')).toHaveClass('badge')
  })

  test('al colapsar y expandir, el indicador solo se ubica en vertical: el ancho lo da el CSS', async () => {
    pantalla(1400)
    const { container } = render(<Sidebar usuario={ADMIN} active="dashboard" />)
    const pill = () => container.querySelector('.side-active-pill')
    // Si JS fijara el ancho, lo mediria a mitad de la animacion del sidebar (al colapsar quedaba fuera de la
    // columna y al expandir del tamaño del icono). El ancho y el left vienen de .side-active-pill /
    // .side.collapsed .side-active-pill en index.css.
    const sinAnchoFijo = () => {
      expect(pill().style.width).toBe('')
      expect(pill().style.left).toBe('')
      expect(pill().style.transform).toMatch(/^translateY\(/)
    }
    sinAnchoFijo()
    await userEvent.click(screen.getByTitle('Colapsar'))
    expect(container.querySelector('aside')).toHaveClass('collapsed')
    sinAnchoFijo()
    await userEvent.click(screen.getByTitle('Expandir'))
    expect(container.querySelector('aside')).not.toHaveClass('collapsed')
    sinAnchoFijo()
  })

  test('sin alertas no hay contador, y una seccion activa no visible no tiene indicador', () => {
    pantalla(1400)
    const { container } = render(<Sidebar usuario={EMPLEADO} active="dashboard" alertCount={0} />)
    expect(container.querySelector('.badge')).toBeNull()
    expect(container.querySelector('.side-active-pill')).toBeNull()
  })

  test('al tocar una seccion navega y cierra el cajon', async () => {
    pantalla(1400)
    const onNavigate = vi.fn(), onClose = vi.fn()
    render(<Sidebar usuario={ADMIN} onNavigate={onNavigate} onClose={onClose} />)
    await userEvent.click(screen.getByText('Reportes'))
    expect(onNavigate).toHaveBeenCalledWith('reports')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('el boton de salir pregunta antes de cerrar la sesion', async () => {
    pantalla(1400)
    const onLogout = vi.fn()
    render(<Sidebar usuario={ADMIN} onLogout={onLogout} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    const dialogo = screen.getByRole('alertdialog', { name: '¿Deseás cerrar sesión?' })
    expect(onLogout).not.toHaveBeenCalled()
    expect(within(dialogo).getByRole('button', { name: 'No' })).toHaveFocus()

    await userEvent.click(within(dialogo).getByRole('button', { name: 'No' }))
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(onLogout).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('alertdialog')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await userEvent.click(document.querySelector('.vm-overlay'))   // tocar afuera tambien cancela
    expect(screen.queryByRole('alertdialog')).toBeNull()
    expect(onLogout).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await userEvent.click(screen.getByRole('button', { name: 'Sí, cerrar sesión' }))
    expect(onLogout).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alertdialog')).toBeNull()
  })

  test('el pie muestra solo el primer nombre (el completo queda en el title)', () => {
    pantalla(1400)
    const { container } = render(<Sidebar usuario={{ ...ADMIN, nombre: '  Miguel Ángel Ortiz Morán ' }} />)
    const nombre = screen.getByText('Miguel')
    expect(nombre).toHaveAttribute('title', '  Miguel Ángel Ortiz Morán ')
    expect(container.querySelector('.avatar')).toHaveTextContent('MM')
  })

  test('en escritorio arranca expandido y se puede colapsar y expandir a mano', async () => {
    pantalla(1400)
    const { container } = render(<Sidebar usuario={ADMIN} />)
    const aside = container.querySelector('aside')
    expect(aside).not.toHaveClass('collapsed')
    await userEvent.click(screen.getByTitle('Colapsar'))
    expect(aside).toHaveClass('collapsed')
    // Plegado: solo iconos (con title), sin etiquetas de seccion ni boton de salir.
    expect(screen.queryByText('Monitoreo')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).not.toBeInTheDocument()
    expect(screen.getByTitle('Reportes')).toBeInTheDocument()
    expect(screen.getAllByRole('img', { name: 'OptiFull' })[0].getAttribute('src')).toMatch(/icono/)
    await userEvent.click(screen.getByTitle('Expandir'))
    expect(aside).not.toHaveClass('collapsed')
  })

  test('en tablet arranca compacto y se adapta si cambia el ancho', () => {
    const p = pantalla(900)
    const { container } = render(<Sidebar usuario={ADMIN} />)
    const aside = container.querySelector('aside')
    expect(aside).toHaveClass('collapsed')
    act(() => p.cambiar(1400))
    expect(aside).not.toHaveClass('collapsed')
  })

  test('en celular siempre se muestra expandido y abre como cajon', () => {
    pantalla(500)
    const { container } = render(<Sidebar usuario={ADMIN} mobileOpen />)
    const aside = container.querySelector('aside')
    expect(aside).not.toHaveClass('collapsed')
    expect(aside).toHaveClass('mobile-open')
  })

  // DEF-018: las secciones eran <a> sin href (no recibian foco con Tab ni se activaban con Enter).
  test('se puede ir a una seccion solo con el teclado', async () => {
    pantalla(1400)
    const onNavigate = vi.fn()
    render(<Sidebar usuario={ADMIN} onNavigate={onNavigate} />)
    const user = userEvent.setup()
    const enDashboard = () => document.activeElement?.matches('.side-nav-item') && document.activeElement.textContent.includes('Dashboard')
    for (let i = 0; i < 6 && !enDashboard(); i++) await user.tab()
    expect(enDashboard()).toBe(true)
    await user.keyboard('{Enter}')
    expect(onNavigate).toHaveBeenCalledWith('dashboard')
  })
})

// Pruebas de los avisos flotantes (toasts), la barra de sección (PageHeader) y el cartel "EN PROGRESO".
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider, useToast, PageHeader, WipBanner } from './Toast'

// Componente mínimo que dispara un toast con el texto y las opciones que se le pasen.
function Disparador({ msg, opts }) {
  const toast = useToast()
  return <button type="button" onClick={() => toast(msg, opts)}>avisar</button>
}

describe('ToastProvider', () => {
  beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }) })

  test('muestra el mensaje con el estilo "info" por defecto y lo saca a los 3 segundos', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<ToastProvider><Disparador msg="Cámara apagada" /></ToastProvider>)

    await user.click(screen.getByRole('button', { name: 'avisar' }))
    const texto = screen.getByText('Cámara apagada')
    expect(texto.closest('.toast')).toHaveClass('toast-info')

    await act(() => vi.advanceTimersByTimeAsync(2900))
    expect(screen.getByText('Cámara apagada')).toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(200))
    expect(screen.queryByText('Cámara apagada')).not.toBeInTheDocument()
  })

  test('respeta el tipo (success / warn) y la duración pedida', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(
      <ToastProvider>
        <Disparador msg="Venta confirmada" opts={{ kind: 'success', ttl: 1000 }} />
      </ToastProvider>,
    )
    await user.click(screen.getByRole('button', { name: 'avisar' }))
    const toast = screen.getByText('Venta confirmada').closest('.toast')
    expect(toast).toHaveClass('toast-success')
    expect(toast.querySelector('.toast-ico svg')).not.toBeNull()

    await act(() => vi.advanceTimersByTimeAsync(1001))
    expect(screen.queryByText('Venta confirmada')).not.toBeInTheDocument()
  })

  test('los avisos se apilan y cada uno se va a su tiempo', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    function Dos() {
      const toast = useToast()
      return (
        <>
          <button type="button" onClick={() => toast('corto', { kind: 'warn', ttl: 500 })}>a</button>
          <button type="button" onClick={() => toast('largo', { ttl: 5000 })}>b</button>
        </>
      )
    }
    render(<ToastProvider><Dos /></ToastProvider>)
    await user.click(screen.getByRole('button', { name: 'a' }))
    await user.click(screen.getByRole('button', { name: 'b' }))
    expect(screen.getByText('corto').closest('.toast')).toHaveClass('toast-warn')
    expect(document.querySelectorAll('.toast-stack .toast')).toHaveLength(2)

    await act(() => vi.advanceTimersByTimeAsync(600))
    expect(screen.queryByText('corto')).not.toBeInTheDocument()
    expect(screen.getByText('largo')).toBeInTheDocument()
  })

  test('fuera del proveedor, useToast no rompe (no hace nada)', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<Disparador msg="nadie lo ve" />)
    await user.click(screen.getByRole('button', { name: 'avisar' }))
    expect(screen.queryByText('nadie lo ve')).not.toBeInTheDocument()
  })
})

describe('PageHeader', () => {
  test('muestra el título como encabezado, el subtítulo, la etiqueta y los controles de la derecha', () => {
    render(<PageHeader title="Alertas" subtitle="Eventos críticos" tag="beta" right={<button type="button">Exportar</button>} />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Alertasbeta')
    expect(screen.getByText('beta')).toHaveClass('section-tag')
    expect(screen.getByText('Eventos críticos')).toHaveClass('section-intro')
    expect(screen.getByRole('button', { name: 'Exportar' })).toBeInTheDocument()
    // En jsdom no hay medidas: no se apila.
    expect(screen.getByRole('banner')).not.toHaveClass('is-stacked')
  })

  test('sin subtítulo ni controles no dibuja esos bloques', () => {
    const { container } = render(<PageHeader title="Stock" />)
    expect(container.querySelector('.section-intro')).toBeNull()
    expect(container.querySelector('.section-tag')).toBeNull()
  })

  test('con stacked queda siempre en dos filas', () => {
    render(<PageHeader title="Dashboard" stacked right={<span>Hoy</span>} />)
    expect(screen.getByRole('banner')).toHaveClass('is-stacked')
  })

  describe('con medidas reales', () => {
    let anchoControles
    beforeEach(() => {
      anchoControles = 100
      // jsdom no calcula layout: se simula una barra de 600px y un título de 200px.
      vi.spyOn(window.HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function () {
        if (this.tagName === 'HEADER') return { width: 600 }
        return { width: anchoControles }
      })
      window.Range.prototype.getBoundingClientRect = () => ({ width: 200 })
    })
    afterEach(() => { delete window.Range.prototype.getBoundingClientRect })

    test('si los controles entran al lado del título, queda en una fila', () => {
      render(<PageHeader title="Reportes" right={<button type="button">uno</button>} />)
      expect(screen.getByRole('banner')).not.toHaveClass('is-stacked')
    })

    test('si los controles se pisan con el título, pasa a dos filas', () => {
      anchoControles = 150
      render(<PageHeader title="Reportes" right={<><button type="button">uno</button><button type="button">dos</button></>} />)
      expect(screen.getByRole('banner')).toHaveClass('is-stacked')
    })
  })
})

describe('WipBanner', () => {
  test('muestra la etiqueta EN PROGRESO y el texto', () => {
    render(<WipBanner>Falta la cámara en vivo</WipBanner>)
    expect(screen.getByText('EN PROGRESO')).toBeInTheDocument()
    expect(screen.getByText('Falta la cámara en vivo')).toBeInTheDocument()
  })
})

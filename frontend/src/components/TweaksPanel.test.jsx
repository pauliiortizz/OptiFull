// Pruebas del panel de ajustes (Tweaks): se abre/cierra por mensajes del editor que contiene la app,
// se puede arrastrar, y cada control avisa el nuevo valor. useTweaks guarda los valores en memoria
// (no persiste en localStorage) y avisa cada cambio con el evento 'tweakchange'.
import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, fireEvent, renderHook } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  useTweaks, TweaksPanel, TweakSection, TweakSlider, TweakToggle, TweakColor, TweakRadio,
} from './TweaksPanel.jsx'

const mensaje = (type) => act(() => { window.dispatchEvent(new MessageEvent('message', { data: { type } })) })

describe('useTweaks', () => {
  test('arranca con los valores por defecto y cambia una clave por vez', () => {
    const { result } = renderHook(() => useTweaks({ density: 'normal', heatIntensity: 80 }))
    expect(result.current[0]).toEqual({ density: 'normal', heatIntensity: 80 })
    act(() => result.current[1]('heatIntensity', 55))
    expect(result.current[0]).toEqual({ density: 'normal', heatIntensity: 55 })
  })

  test('acepta varios cambios juntos y avisa cada cambio con el evento tweakchange', () => {
    const oyente = vi.fn()
    window.addEventListener('tweakchange', oyente)
    const { result } = renderHook(() => useTweaks({ a: 1, b: 2, c: 3 }))
    act(() => result.current[1]({ a: 10, b: 20 }))
    expect(result.current[0]).toEqual({ a: 10, b: 20, c: 3 })
    act(() => result.current[1]('c', 30))
    expect(oyente.mock.calls.map(([e]) => e.detail)).toEqual([{ a: 10, b: 20 }, { c: 30 }])
    window.removeEventListener('tweakchange', oyente)
  })

  test('no guarda nada en el almacenamiento del navegador', () => {
    const { result } = renderHook(() => useTweaks({ a: 1 }))
    act(() => result.current[1]('a', 2))
    expect(window.localStorage.length).toBe(0)
  })
})

describe('TweaksPanel', () => {
  let postMessage
  beforeEach(() => { postMessage = vi.spyOn(window.parent, 'postMessage').mockImplementation(() => {}) })

  test('al montarse avisa al editor que hay modo edición y queda oculto', () => {
    render(<TweaksPanel><p>contenido</p></TweaksPanel>)
    expect(postMessage).toHaveBeenCalledWith({ type: '__edit_mode_available' }, '*')
    expect(screen.queryByText('contenido')).not.toBeInTheDocument()
  })

  test('se abre y se cierra con los mensajes del editor', () => {
    render(<TweaksPanel title="Ajustes"><p>contenido</p></TweaksPanel>)
    mensaje('__activate_edit_mode')
    expect(screen.getByText('Ajustes')).toBeInTheDocument()
    expect(screen.getByText('contenido')).toBeInTheDocument()
    mensaje('otro_mensaje')
    expect(screen.getByText('contenido')).toBeInTheDocument()
    mensaje('__deactivate_edit_mode')
    expect(screen.queryByText('contenido')).not.toBeInTheDocument()
  })

  test('un mensaje sin datos no rompe nada', () => {
    render(<TweaksPanel><p>contenido</p></TweaksPanel>)
    act(() => { window.dispatchEvent(new MessageEvent('message', { data: null })) })
    expect(screen.queryByText('contenido')).not.toBeInTheDocument()
  })

  test('la cruz cierra el panel', async () => {
    const user = userEvent.setup()
    render(<TweaksPanel><p>contenido</p></TweaksPanel>)
    mensaje('__activate_edit_mode')
    expect(screen.getByText('Tweaks')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '✕' }))
    expect(screen.queryByText('contenido')).not.toBeInTheDocument()
  })

  test('se arrastra desde el encabezado sin salirse de la ventana', () => {
    render(<TweaksPanel><p>contenido</p></TweaksPanel>)
    mensaje('__activate_edit_mode')
    const panel = document.querySelector('.twk-panel')
    expect(panel.style.right).toBe('16px')
    expect(panel.style.bottom).toBe('16px')
    // el panel esta a 16 px del borde derecho e inferior de una ventana de 1024x768
    vi.spyOn(panel, 'getBoundingClientRect').mockReturnValue({ right: window.innerWidth - 16, bottom: window.innerHeight - 16 })
    fireEvent.mouseDown(screen.getByText('Tweaks'), { clientX: 500, clientY: 400 })
    fireEvent.mouseMove(window, { clientX: 400, clientY: 350 })
    expect(panel.style.right).toBe('116px')
    expect(panel.style.bottom).toBe('66px')
    // arrastrarlo fuera de la ventana lo deja pegado al margen
    fireEvent.mouseMove(window, { clientX: 5000, clientY: 5000 })
    expect(panel.style.right).toBe('16px')
    expect(panel.style.bottom).toBe('16px')
    fireEvent.mouseMove(window, { clientX: -5000, clientY: -5000 })
    expect(panel.style.right).toBe(`${window.innerWidth - 16}px`)
    // al soltar deja de seguir al mouse
    fireEvent.mouseUp(window)
    fireEvent.mouseMove(window, { clientX: 400, clientY: 350 })
    expect(panel.style.right).toBe(`${window.innerWidth - 16}px`)
  })

  test('las secciones muestran su título y su contenido', () => {
    render(<TweaksPanel><TweakSection label="Apariencia"><span>hijo</span></TweakSection></TweaksPanel>)
    mensaje('__activate_edit_mode')
    expect(screen.getByText('Apariencia')).toBeInTheDocument()
    expect(screen.getByText('hijo')).toBeInTheDocument()
  })
})

describe('TweakSlider', () => {
  test('muestra el valor con su unidad y avisa el nuevo valor como número', () => {
    const onChange = vi.fn()
    render(<TweakSlider label="Intensidad heatmap" value={80} min={10} max={100} step={5} unit="%" onChange={onChange} />)
    expect(screen.getByText('80%')).toBeInTheDocument()
    const slider = screen.getByRole('slider')
    expect(slider).toHaveAttribute('min', '10')
    fireEvent.change(slider, { target: { value: '45' } })
    expect(onChange).toHaveBeenCalledWith(45)
  })
})

describe('TweakToggle', () => {
  test('refleja el estado y avisa el contrario al tocarlo', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const { rerender } = render(<TweakToggle label="Actualizaciones en vivo" value={false} onChange={onChange} />)
    const sw = screen.getByRole('switch')
    expect(sw).toHaveAttribute('aria-checked', 'false')
    await user.click(sw)
    expect(onChange).toHaveBeenLastCalledWith(true)
    rerender(<TweakToggle label="Actualizaciones en vivo" value onChange={onChange} />)
    expect(sw).toHaveAttribute('aria-checked', 'true')
    await user.click(sw)
    expect(onChange).toHaveBeenLastCalledWith(false)
  })
})

describe('TweakRadio', () => {
  // la pista de segmentos mide 204 px (2 px de borde a cada lado)
  const medirPista = () => vi.spyOn(screen.getByRole('radiogroup'), 'getBoundingClientRect')
    .mockReturnValue({ left: 0, width: 204, right: 204, top: 0, bottom: 20 })
  const puntero = (el, tipo, clientX) => act(() => { el.dispatchEvent(new PointerEvent(tipo, { bubbles: true, clientX })) })

  test('con pocas opciones cortas muestra segmentos y marca la elegida', () => {
    render(<TweakRadio label="Densidad" value="normal" options={['compacta', 'normal']} onChange={() => {}} />)
    expect(screen.getByRole('radio', { name: 'normal' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: 'compacta' })).toHaveAttribute('aria-checked', 'false')
  })

  test('tocar o arrastrar sobre los segmentos elige la opción bajo el puntero', () => {
    const onChange = vi.fn()
    render(<TweakRadio label="Densidad" value="compacta" options={['compacta', 'normal', 'amplia']} onChange={onChange} />)
    medirPista()
    const pista = screen.getByRole('radiogroup')
    puntero(pista, 'pointerdown', 10)        // sobre la opcion actual: no avisa
    expect(onChange).not.toHaveBeenCalled()
    expect(pista).toHaveClass('dragging')
    puntero(window, 'pointermove', 100)      // segmento del medio
    expect(onChange).toHaveBeenLastCalledWith('normal')
    puntero(window, 'pointermove', 9999)     // fuera de la pista: la ultima opcion
    expect(onChange).toHaveBeenLastCalledWith('amplia')
    puntero(window, 'pointerup', 9999)
    expect(pista).not.toHaveClass('dragging')
    onChange.mockClear()
    puntero(window, 'pointermove', 100)
    expect(onChange).not.toHaveBeenCalled()
  })

  test('acepta opciones con valor y etiqueta', () => {
    const onChange = vi.fn()
    render(<TweakRadio label="Modo" value="b" options={[{ value: 'a', label: 'Uno' }, { value: 'b', label: 'Dos' }]} onChange={onChange} />)
    medirPista()
    expect(screen.getByRole('radio', { name: 'Dos' })).toHaveAttribute('aria-checked', 'true')
    puntero(screen.getByRole('radiogroup'), 'pointerdown', 5)
    expect(onChange).toHaveBeenCalledWith('a')
    puntero(window, 'pointerup', 5)
  })

  test('con etiquetas largas o muchas opciones usa una lista desplegable y conserva el tipo del valor', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const opciones = [{ value: 1, label: 'Una cámara por fila' }, { value: 2, label: 'Dos cámaras por fila' }]
    render(<TweakRadio label="Columnas" value={1} options={opciones} onChange={onChange} />)
    const lista = screen.getByRole('combobox')
    await user.selectOptions(lista, 'Dos cámaras por fila')
    expect(onChange).toHaveBeenCalledWith(2)
  })

  test('con cuatro opciones simples también usa la lista y devuelve el texto', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<TweakRadio label="Hora" value="a" options={['a', 'b', 'c', 'd']} onChange={onChange} />)
    await user.selectOptions(screen.getByRole('combobox'), 'c')
    expect(onChange).toHaveBeenCalledWith('c')
  })
})

describe('TweakColor', () => {
  test('sin opciones muestra un selector de color libre', () => {
    const onChange = vi.fn()
    const { container } = render(<TweakColor label="Acento" value="#336699" onChange={onChange} />)
    const input = container.querySelector('input[type="color"]')
    expect(input).toHaveValue('#336699')
    fireEvent.change(input, { target: { value: '#ff0000' } })
    expect(onChange).toHaveBeenCalledWith('#ff0000')
  })

  test('con opciones muestra muestras, marca la elegida y avisa la que se toca', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const opciones = ['#1F4FD8', '#ffffff', ['#000000', '#111111', '#222222']]
    render(<TweakColor label="Acento" value="#1f4fd8" options={opciones} onChange={onChange} />)
    const chips = screen.getAllByRole('radio')
    expect(chips).toHaveLength(3)
    // la comparacion no distingue mayusculas
    expect(chips[0]).toHaveAttribute('aria-checked', 'true')
    expect(chips[1]).toHaveAttribute('aria-checked', 'false')
    // una paleta muestra sus colores secundarios al costado
    expect(chips[2].querySelectorAll('span > i')).toHaveLength(2)
    await user.click(chips[2])
    expect(onChange).toHaveBeenCalledWith(['#000000', '#111111', '#222222'])
  })

  test('la tilde se ve oscura sobre colores claros y blanca sobre oscuros', () => {
    const tilde = (c) => c.querySelector('svg path').getAttribute('stroke')
    const casos = [['#fff', 'rgba(0,0,0,.78)'], ['#000', '#fff'], ['#1f4fd8', '#fff'], ['no-es-color', 'rgba(0,0,0,.78)']]
    for (const [color, esperado] of casos) {
      const { container, unmount } = render(<TweakColor label="A" value={color} options={[color]} onChange={() => {}} />)
      expect(tilde(container), color).toBe(esperado)
      unmount()
    }
  })
})

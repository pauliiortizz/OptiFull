// Pruebas de la página de Ventas (VentasPage.jsx): tickets con productos, total y fecha, resumen y filtro por
// período. La API es falsa (ver src/test/apiFalsa.js) y respeta el contrato de frontend/api/ventas.py (GET /api/ventas).
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { apiFalsa } from '../test/apiFalsa'
import { VentasPage } from './VentasPage'

const TICKET = {
  id: 12, fecha: '2026-10-21T18:30:00+00:00', total: 1250,
  items: [
    { sku: 'A', nombre: 'Agua Bonaqua 500ml', cantidad: 2, precio_unitario: 500, subtotal: 1000 },
    { sku: 'B', nombre: 'Cereal Mix Frutilla', cantidad: 1, precio_unitario: 250, subtotal: 250 },
  ],
}
const SIN_TICKET = {
  id: null, fecha: '2026-10-20T15:00:00+00:00', total: 300,
  items: [{ sku: 'C', nombre: 'Chicle', cantidad: 3, precio_unitario: 100, subtotal: 300 }],
}
const RESPUESTA = { ventas: [TICKET, SIN_TICKET], resumen: { tickets: 2, total: 1550, unidades: 6, ticket_promedio: 775 } }

function montar(regla = RESPUESTA) {
  const api = apiFalsa({ 'GET /api/ventas': regla })
  render(<VentasPage />)
  return api
}

const tarjeta = (titulo) => screen.getByText(titulo).closest('.vt-ticket')
const tile = (etiqueta) => screen.getByText(etiqueta).closest('.stat-tile')
// Testing Library normaliza los espacios del texto renderizado (el formato de moneda usa uno no separable) pero no
// los del texto buscado: se normalizan aca también.
const pesos = (n) => n.toLocaleString('es-AR', { style: 'currency', currency: 'ARS' }).replace(/\s/g, ' ')

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.setSystemTime(new Date(2026, 9, 21, 12, 0))   // 21/10/2026, 12:00 hora local
})
afterEach(() => vi.useRealTimers())

describe('ventas', () => {
  test('muestra cada ticket con sus productos, el total y la fecha', async () => {
    montar()
    await screen.findByText('Ticket #12')
    const t = within(tarjeta('Ticket #12'))
    expect(t.getByText('Agua Bonaqua 500ml')).toBeInTheDocument()
    expect(t.getByText('×2')).toBeInTheDocument()
    expect(t.getByText(`${pesos(500)} c/u`)).toBeInTheDocument()
    expect(t.getByText('Cereal Mix Frutilla')).toBeInTheDocument()
    expect(t.getByText(pesos(1250))).toBeInTheDocument()
    expect(t.getByRole('time')).toHaveAttribute('dateTime', TICKET.fecha)
  })

  test('una venta vieja sin ticket se muestra sin número', async () => {
    montar()
    expect(await screen.findByText('Venta sin ticket')).toBeInTheDocument()
    expect(within(tarjeta('Venta sin ticket')).getByText('Chicle')).toBeInTheDocument()
  })

  test('el resumen muestra tickets, facturado, ticket promedio y unidades', async () => {
    montar()
    await screen.findByText('Ticket #12')
    expect(tile('Tickets')).toHaveTextContent('2')
    expect(tile('Facturado')).toHaveTextContent(pesos(1550))
    expect(tile('Ticket promedio')).toHaveTextContent(pesos(775))
    expect(tile('Unidades')).toHaveTextContent('6')
  })

  test('arranca con los últimos 7 días y el filtro cambia el período pedido', async () => {
    const api = montar()
    await screen.findByText('Ticket #12')
    expect(api.hechos('/api/ventas')[0].query).toEqual({ desde: '2026-10-15' })
    await userEvent.click(screen.getByRole('button', { name: 'Hoy' }))
    await waitFor(() => expect(api.hechos('/api/ventas').at(-1).query).toEqual({ desde: '2026-10-21' }))
    await userEvent.click(screen.getByRole('button', { name: 'Todo' }))
    await waitFor(() => expect(api.hechos('/api/ventas').at(-1).query).toEqual({}))
  })

  test('sin ventas en el período lo dice', async () => {
    montar({ ventas: [], resumen: { tickets: 0, total: 0, unidades: 0, ticket_promedio: 0 } })
    expect(await screen.findByText('No hay ventas en este período.')).toBeInTheDocument()
  })

  test('si la API falla muestra el error', async () => {
    montar({ status: 503, json: { error: 'sin conexion a la base de datos' } })
    expect(await screen.findByText(/No se pudieron cargar las ventas: sin conexion/)).toBeInTheDocument()
  })

  test('"Actualizar" vuelve a pedir las ventas', async () => {
    const api = montar()
    await screen.findByText('Ticket #12')
    await userEvent.click(screen.getByRole('button', { name: 'Actualizar' }))
    await waitFor(() => expect(api.hechos('/api/ventas')).toHaveLength(2))
  })
})

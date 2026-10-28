// Pruebas de la página de Reportes: opciones, filtros (métricas, período, cámaras, formato) y exportación.
import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { apiFalsa } from '../test/apiFalsa.js'
import { ReportsV2Page } from './ReportsV2Page'

// Forma real de GET /api/reportes/opciones (frontend/api/reportes_export.py + reportes_datos.catalogo())
const OPCIONES = {
  metricas: [
    { id: 'personas_flujo', categoria: 'personas', titulo: 'Conteo y flujo de personas', descripcion: 'Personas únicas por día, por día de semana y por cámara.' },
    { id: 'personas_permanencia', categoria: 'personas', titulo: 'Tiempos de permanencia promedio', descripcion: 'Minutos promedio y máximos por día y por zona (caja, góndolas, salón).' },
    { id: 'personas_congestion', categoria: 'personas', titulo: 'Picos de congestión y franjas horarias críticas', descripcion: 'Matriz día × hora y franjas críticas detectadas.' },
    { id: 'stock_deteccion', categoria: 'stock', titulo: 'Detección y ocupación de góndolas/estanterías', descripcion: 'Productos detectados, confianza del modelo y presencia frente a góndolas.' },
    { id: 'stock_faltantes', categoria: 'stock', titulo: 'Faltantes y rotación de stock', descripcion: 'Productos agotados o con stock bajo, rotación y cobertura.' },
  ],
  formatos: [
    { id: 'pdf', titulo: 'PDF', descripcion: 'Resumen ejecutivo con estadísticas y gráficos.' },
    { id: 'xlsx', titulo: 'Excel (.xlsx)', descripcion: 'Una hoja por tabla, listo para analizar.' },
    { id: 'csv', titulo: 'CSV', descripcion: 'Datos tabulares crudos (ZIP si hay varias tablas).' },
    { id: 'png', titulo: 'Imágenes', descripcion: 'PNG de los gráficos estadísticos (ZIP si hay varios).' },
  ],
  camaras: [{ id: 1, nombre: 'Entrada' }, { id: 2, nombre: 'Góndolas' }, { id: 4, nombre: 'Caja' }],
  fecha_min: '2026-06-01',
  fecha_max: '2026-10-15',
}
const IDS = OPCIONES.metricas.map((m) => m.id)

const archivo = (nombre, contenido, tipo) => ({
  blob: new Blob([contenido], { type: tipo }),
  headers: { 'Content-Type': tipo, 'Content-Disposition': `attachment; filename="${nombre}"` },
})

let descargas
beforeEach(() => {
  // Captura la descarga: el <a download> que arma la página y el blob que se convierte en URL.
  descargas = []
  vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => { descargas.push({ blob }); return `blob:reporte-${descargas.length}` })
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
    Object.assign(descargas[descargas.length - 1], { href: this.href, nombre: this.download, enDocumento: document.body.contains(this) })
  })
})

async function abrir(reglas = {}) {
  const api = apiFalsa({ 'GET /api/reportes/opciones': OPCIONES, ...reglas })
  const user = userEvent.setup()
  const utils = render(<ReportsV2Page />)
  await screen.findByRole('switch', { name: /Seleccionar todo/ })
  return { api, user, ...utils }
}

const boton = () => screen.getByRole('button', { name: /Generar reporte|Generando/ })
const barra = () => screen.getByRole('contentinfo')
const exportaciones = (api) => api.hechos('/api/reportes/exportar', 'POST')

describe('carga de opciones', () => {
  test('mientras carga muestra el aviso y luego las métricas agrupadas por categoría', async () => {
    const api = apiFalsa({ 'GET /api/reportes/opciones': OPCIONES })
    render(<ReportsV2Page />)
    expect(screen.getByText('Cargando opciones…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Generar/ })).toBeNull()

    const personas = await screen.findByRole('region', { name: 'Personas / Afluencia' })
    expect(screen.queryByText('Cargando opciones…')).toBeNull()
    expect(within(personas).getByText('3 de 3')).toBeInTheDocument()
    expect(within(personas).getAllByRole('switch')).toHaveLength(3)
    const stock = screen.getByRole('region', { name: 'Stock y Productos' })
    expect(within(stock).getByText('2 de 2')).toBeInTheDocument()
    expect(within(stock).getByText('Productos agotados o con stock bajo, rotación y cobertura.')).toBeInTheDocument()
    expect(api.pedidos.map((p) => p.ruta)).toEqual(['/api/reportes/opciones'])
  })

  test('por defecto están todas las métricas activas, PDF elegido, todo el período y todas las cámaras', async () => {
    await abrir()
    expect(screen.getByRole('switch', { name: /Seleccionar todo/ })).toBeChecked()
    expect(screen.getByText('Descargar el reporte completo (5 métricas)')).toBeInTheDocument()
    for (const s of screen.getAllByRole('switch')) expect(s).toBeChecked()
    expect(screen.getByRole('radio', { name: /PDF/ })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Todo' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(barra()).getByText(/5 de 5 métricas · PDF/)).toBeInTheDocument()
    expect(within(barra()).getByText('Todo el período · Todas las cámaras')).toBeInTheDocument()
    expect(screen.getByText(/Datos disponibles del 01\/06\/2026 al 15\/10\/2026/)).toBeInTheDocument()
    expect(boton()).toBeEnabled()
  })

  test('las fechas limitan el rango a los días con datos', async () => {
    await abrir()
    expect(screen.getByLabelText('Desde')).toHaveAttribute('min', '2026-06-01')
    expect(screen.getByLabelText('Desde')).toHaveAttribute('max', '2026-10-15')
    expect(screen.getByLabelText('Hasta')).toHaveAttribute('max', '2026-10-15')
  })

  test('sin datos todavía (fechas nulas) muestra guiones en el rango disponible', async () => {
    await abrir({ 'GET /api/reportes/opciones': { ...OPCIONES, fecha_min: null, fecha_max: null } })
    expect(screen.getByText(/Datos disponibles del — al —/)).toBeInTheDocument()
  })

  test('error del servidor: muestra el mensaje y Reintentar vuelve a pedir las opciones', async () => {
    const user = userEvent.setup()
    let intentos = 0
    const api = apiFalsa({
      'GET /api/reportes/opciones': () => (++intentos === 1 ? { status: 503, json: { error: 'sin conexión a la base de datos' } } : OPCIONES),
    })
    render(<ReportsV2Page />)
    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('No se pudieron cargar las opciones del reporte: sin conexión a la base de datos')
    expect(screen.queryByRole('contentinfo')).toBeNull()

    await user.click(within(alerta).getByRole('button', { name: 'Reintentar' }))
    await screen.findByRole('switch', { name: /Seleccionar todo/ })
    expect(screen.queryByText(/No se pudieron cargar/)).toBeNull()
    expect(api.hechos('/api/reportes/opciones')).toHaveLength(2)
  })

  test('error sin cuerpo JSON muestra el código HTTP', async () => {
    apiFalsa({ 'GET /api/reportes/opciones': { status: 502, texto: '<html>Bad Gateway</html>' } })
    render(<ReportsV2Page />)
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudieron cargar las opciones del reporte: Error 502')
  })

  test('falla de red muestra el error', async () => {
    apiFalsa({ 'GET /api/reportes/opciones': new TypeError('Failed to fetch') })
    render(<ReportsV2Page />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to fetch')
  })
})

describe('selección de métricas', () => {
  test('apagar una métrica actualiza el contador de su categoría, "Seleccionar todo" y la barra', async () => {
    const { user } = await abrir()
    await user.click(screen.getByRole('switch', { name: /Faltantes y rotación de stock/ }))
    expect(within(screen.getByRole('region', { name: 'Stock y Productos' })).getByText('1 de 2')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: /Seleccionar todo/ })).not.toBeChecked()
    expect(within(barra()).getByText(/4 de 5 métricas/)).toBeInTheDocument()
  })

  test('"Seleccionar todo" apaga y prende todas; sin métricas no se puede generar', async () => {
    const { user, api } = await abrir()
    const todo = screen.getByRole('switch', { name: /Seleccionar todo/ })
    await user.click(todo)
    for (const s of screen.getAllByRole('switch')) expect(s).not.toBeChecked()
    expect(within(barra()).getByText('Ninguna métrica seleccionada')).toBeInTheDocument()
    expect(boton()).toBeDisabled()
    await user.click(boton())
    expect(exportaciones(api)).toHaveLength(0)

    await user.click(todo)
    for (const s of screen.getAllByRole('switch')) expect(s).toBeChecked()
    expect(boton()).toBeEnabled()
  })

  test('una categoría sin métricas en el catálogo no se muestra', async () => {
    await abrir({ 'GET /api/reportes/opciones': { ...OPCIONES, metricas: OPCIONES.metricas.filter((m) => m.categoria === 'personas') } })
    expect(screen.queryByRole('region', { name: 'Stock y Productos' })).toBeNull()
    expect(screen.getByText('Descargar el reporte completo (3 métricas)')).toBeInTheDocument()
  })
})

describe('período', () => {
  test.each([
    ['7 días', '2026-10-09'],
    ['30 días', '2026-09-16'],
    ['90 días', '2026-07-18'],
  ])('el rango rápido "%s" cuenta hacia atrás desde el último día con datos', async (nombre, desde) => {
    const { user } = await abrir()
    await user.click(screen.getByRole('button', { name: nombre }))
    expect(screen.getByRole('button', { name: nombre })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Desde')).toHaveValue(desde)
    expect(screen.getByLabelText('Hasta')).toHaveValue('2026-10-15')
    expect(within(barra()).getByText(`${desde.split('-').reverse().join('/')} → 15/10/2026 · Todas las cámaras`)).toBeInTheDocument()
  })

  test('"Todo" limpia las fechas', async () => {
    const { user } = await abrir()
    await user.click(screen.getByRole('button', { name: '30 días' }))
    await user.click(screen.getByRole('button', { name: 'Todo' }))
    expect(screen.getByLabelText('Desde')).toHaveValue('')
    expect(screen.getByLabelText('Hasta')).toHaveValue('')
    expect(within(barra()).getByText(/Todo el período/)).toBeInTheDocument()
  })

  test('sin fecha máxima en la base, los rangos rápidos cuentan desde hoy', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-20T15:00:00Z'))
    const { user } = await abrir({ 'GET /api/reportes/opciones': { ...OPCIONES, fecha_max: null } })
    await user.click(screen.getByRole('button', { name: '7 días' }))
    expect(screen.getByLabelText('Desde')).toHaveValue('2026-10-14')
    expect(screen.getByLabelText('Hasta')).toHaveValue('2026-10-20')
  })

  test('fechas a mano: solo desde, solo hasta, y el preset deja de estar marcado', async () => {
    await abrir()
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-08-01' } })
    expect(within(barra()).getByText(/^Desde 01\/08\/2026 ·/)).toBeInTheDocument()
    for (const b of within(screen.getByRole('group', { name: 'Rango rápido' })).getAllByRole('button')) {
      expect(b).toHaveAttribute('aria-pressed', 'false')
    }
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-09-30' } })
    expect(within(barra()).getByText(/^Hasta 30\/09\/2026 ·/)).toBeInTheDocument()
    expect(screen.getByLabelText('Desde')).toHaveAttribute('max', '2026-09-30')
  })

  test('"Desde" posterior a "Hasta" avisa el error y bloquea la generación', async () => {
    const { user, api } = await abrir()
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-10-10' } })
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-10-01' } })
    expect(screen.getByText('La fecha "Desde" no puede ser posterior a "Hasta".')).toBeInTheDocument()
    expect(screen.getByLabelText('Desde')).toHaveAttribute('aria-invalid', 'true')
    expect(boton()).toBeDisabled()
    await user.click(boton())
    expect(exportaciones(api)).toHaveLength(0)

    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-10-12' } })
    expect(screen.queryByText(/no puede ser posterior/)).toBeNull()
    expect(boton()).toBeEnabled()
  })
})

describe('cámaras y formato', () => {
  test('elegir cámaras las resume en la barra y "Quitar selección" vuelve a todas', async () => {
    const { user } = await abrir()
    const grupo = screen.getByRole('group', { name: 'Cámaras' })
    expect(screen.queryByRole('button', { name: 'Quitar selección' })).toBeNull()
    await user.click(within(grupo).getByRole('checkbox', { name: 'Caja' }))
    await user.click(within(grupo).getByRole('checkbox', { name: 'Entrada' }))
    expect(within(grupo).getByRole('checkbox', { name: 'Caja' })).toHaveAttribute('aria-checked', 'true')
    expect(within(grupo).getByRole('checkbox', { name: 'Góndolas' })).toHaveAttribute('aria-checked', 'false')
    expect(within(barra()).getByText('Todo el período · Entrada, Caja')).toBeInTheDocument()

    await user.click(within(grupo).getByRole('checkbox', { name: 'Caja' }))
    expect(within(barra()).getByText('Todo el período · Entrada')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Quitar selección' }))
    expect(within(barra()).getByText('Todo el período · Todas las cámaras')).toBeInTheDocument()
    expect(within(grupo).getByRole('checkbox', { name: 'Entrada' })).toHaveAttribute('aria-checked', 'false')
  })

  test('cambiar el formato lo marca y lo muestra en la barra', async () => {
    const { user } = await abrir()
    await user.click(screen.getByRole('radio', { name: /Excel \(\.xlsx\)/ }))
    expect(screen.getByRole('radio', { name: /Excel/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /PDF/ })).not.toBeChecked()
    expect(within(barra()).getByText(/5 de 5 métricas · Excel \(\.xlsx\)/)).toBeInTheDocument()
  })

  test('un formato desconocido para el frontend igual se puede elegir (ícono por defecto)', async () => {
    const { user } = await abrir({ 'GET /api/reportes/opciones': { ...OPCIONES, formatos: [...OPCIONES.formatos, { id: 'json', titulo: 'JSON', descripcion: 'Crudo.' }] } })
    await user.click(screen.getByRole('radio', { name: /JSON/ }))
    expect(within(barra()).getByText(/· JSON/)).toBeInTheDocument()
  })
})

// ZIP sin comprimir (metodo 'stored') armado a mano, como los que arma zipfile/openpyxl pero sin deflate: alcanza
// para probar la vista previa de los ZIP de imagenes/CSV y de los Excel (un .xlsx es un ZIP con XML).
function zip(archivos) {
  const enc = new TextEncoder()
  const locales = [], centrales = []
  let offset = 0
  for (const [nombre, contenido] of Object.entries(archivos)) {
    const n = enc.encode(nombre)
    const datos = typeof contenido === 'string' ? enc.encode(contenido) : contenido
    const local = new Uint8Array(30 + n.length + datos.length)
    const dl = new DataView(local.buffer)
    dl.setUint32(0, 0x04034b50, true); dl.setUint32(18, datos.length, true); dl.setUint32(22, datos.length, true)
    dl.setUint16(26, n.length, true); local.set(n, 30); local.set(datos, 30 + n.length)
    const central = new Uint8Array(46 + n.length)
    const dc = new DataView(central.buffer)
    dc.setUint32(0, 0x02014b50, true); dc.setUint32(20, datos.length, true); dc.setUint32(24, datos.length, true)
    dc.setUint16(28, n.length, true); dc.setUint32(42, offset, true); central.set(n, 46)
    locales.push(local); centrales.push(central); offset += local.length
  }
  const tamCentral = centrales.reduce((t, c) => t + c.length, 0)
  const fin = new Uint8Array(22)
  const df = new DataView(fin.buffer)
  df.setUint32(0, 0x06054b50, true); df.setUint16(8, centrales.length, true); df.setUint16(10, centrales.length, true)
  df.setUint32(12, tamCentral, true); df.setUint32(16, offset, true)
  return new Uint8Array(new Blob([...locales, ...centrales, fin]).size && [...locales, ...centrales, fin].flatMap((a) => [...a]))
}

const XLSX = zip({
  'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Resumen" sheetId="1" r:id="rId1"/><sheet name="Conteo" sheetId="2" r:id="rId2"/></sheets></workbook>',
  'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="/xl/worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>',
  'xl/sharedStrings.xml': '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>OptiFull - Reporte</t></si><si><t>Día</t></si><si><t>Personas</t></si><si><t>Lunes</t></si></sst>',
  'xl/worksheets/sheet1.xml': '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>',
  'xl/worksheets/sheet2.xml': '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>1</v></c><c r="B1" t="s"><v>2</v></c></row><row r="2"><c r="A2" t="s"><v>3</v></c><c r="B2"><v>8.699999999999999</v></c><c r="C2"><v>42</v></c></row></sheetData></worksheet>',
  'xl/media/image1.png': 'png',
})

const dialogo = () => screen.findByRole('dialog', { name: 'Vista previa del reporte' })
const bajadas = () => descargas.filter((d) => d.nombre)

async function generarYDescargar(user) {
  await user.click(boton())
  const d = await dialogo()
  await user.click(within(d).getByRole('button', { name: 'Descargar' }))
}

describe('exportación', () => {
  test.each([
    ['PDF', 'pdf', 'application/pdf'],
    ['Excel (.xlsx)', 'xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
    ['CSV', 'csv', 'text/csv'],
    ['Imágenes', 'png', 'application/zip'],
  ])('%s: genera el reporte, lo muestra en la vista previa y recién ahí lo descarga', async (titulo, id, tipo) => {
    const nombre = `optifull_reporte_20261020_1015.${id === 'png' ? 'zip' : id}`
    const contenido = 'x'.repeat(3000)
    const { user, api } = await abrir({ 'POST /api/reportes/exportar': archivo(nombre, contenido, tipo) })
    await user.click(screen.getByRole('radio', { name: new RegExp(titulo.replace(/[().]/g, '\\$&')) }))
    await user.click(boton())

    const d = await dialogo()
    expect(within(d).getByText(new RegExp(`${nombre.replace('.', '\\.')} · .* · 3 KB`))).toBeInTheDocument()
    expect(bajadas()).toHaveLength(0)                 // generar ya no descarga solo
    expect(within(barra()).getByText('Reporte generado: revisalo en la vista previa.')).toBeInTheDocument()
    const [pedido] = exportaciones(api)
    expect(pedido.cuerpo).toEqual({ metricas: IDS, formato: id, desde: null, hasta: null, camaras: [] })

    await user.click(within(d).getByRole('button', { name: 'Descargar' }))
    expect(await within(barra()).findByText(`✓ ${nombre} (3 KB) se descargó correctamente.`)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(bajadas()).toHaveLength(1)
    expect(bajadas()[0]).toMatchObject({ nombre, enDocumento: true })
    expect(await bajadas()[0].blob.text()).toBe(contenido)
    // El enlace temporal no queda colgado en la página
    expect(document.querySelector('a[download]')).toBeNull()
  })

  test('PDF: la vista previa lo muestra en el visor del navegador', async () => {
    const { user } = await abrir({ 'POST /api/reportes/exportar': archivo('r.pdf', '%PDF-1.4', 'application/pdf') })
    await user.click(boton())
    const visor = within(await dialogo()).getByTitle('Vista previa de r.pdf')
    expect(visor.tagName).toBe('IFRAME')
    expect(visor.getAttribute('src')).toMatch(/^blob:reporte-/)
  })

  test('CSV: la vista previa lo muestra como tabla (con comillas y comas adentro de una celda)', async () => {
    const csv = '﻿Día,Personas,Zona\r\nLunes,12,"Caja, salida"\r\nMartes,8,"Góndola ""A"""\r\n'
    const { user } = await abrir({ 'POST /api/reportes/exportar': archivo('r.csv', csv, 'text/csv') })
    await user.click(screen.getByRole('radio', { name: /CSV/ }))
    await user.click(boton())
    const d = await dialogo()
    expect(within(d).getAllByRole('columnheader').map((c) => c.textContent)).toEqual(['Día', 'Personas', 'Zona'])
    expect(within(d).getAllByRole('row').slice(1).map((r) => [...r.cells].map((c) => c.textContent))).toEqual([
      ['Lunes', '12', 'Caja, salida'], ['Martes', '8', 'Góndola "A"'],
    ])
  })

  test('una tabla muy larga se recorta en la vista previa y avisa que el archivo trae todo', async () => {
    const csv = 'n\n' + Array.from({ length: 350 }, (_, i) => i).join('\n') + '\n'
    const { user } = await abrir({ 'POST /api/reportes/exportar': archivo('r.csv', csv, 'text/csv') })
    await user.click(boton())
    const d = await dialogo()
    expect(within(d).getAllByRole('row')).toHaveLength(301)
    expect(within(d).getByText('Se muestran 300 de 350 filas. El archivo descargado las incluye todas.')).toBeInTheDocument()
  })

  test('Imágenes (ZIP): muestra cada gráfico y los parámetros, para revisarlos scrolleando', async () => {
    const contenido = zip({ 'personas_flujo__por_dia.png': 'png1', 'stock_faltantes__top.png': 'png2', 'parametros.txt': 'OptiFull - Reporte\nPeríodo: Todo' })
    const { user } = await abrir({ 'POST /api/reportes/exportar': archivo('r.zip', contenido, 'application/zip') })
    await user.click(boton())
    const d = await dialogo()
    expect(within(d).getAllByRole('img').map((i) => i.getAttribute('alt'))).toEqual(['personas_flujo__por_dia.png', 'stock_faltantes__top.png'])
    expect(within(d).getByText(/Período: Todo/)).toBeInTheDocument()
    expect(within(d).getByRole('heading', { name: 'parametros.txt' })).toBeInTheDocument()
  })

  test('Excel: muestra cada hoja como tabla y sus gráficos', async () => {
    const { user } = await abrir({ 'POST /api/reportes/exportar': archivo('r.xlsx', XLSX, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') })
    await user.click(boton())
    const d = await dialogo()
    expect(within(d).getByRole('heading', { name: 'Resumen' })).toBeInTheDocument()
    expect(within(d).getByRole('heading', { name: 'Conteo' })).toBeInTheDocument()
    const tablas = within(d).getAllByRole('table')
    expect(within(tablas[0]).getByRole('columnheader', { name: 'OptiFull - Reporte' })).toBeInTheDocument()
    // una fila mas ancha que la cabecera no pierde columnas, y el float de Excel se muestra redondeado
    expect([...within(tablas[1]).getAllByRole('row')[1].cells].map((c) => c.textContent)).toEqual(['Lunes', '8.7', '42'])
    expect(within(d).getByRole('img', { name: 'Gráfico 1' })).toBeInTheDocument()
  })

  test('si la vista previa no se puede armar, lo avisa y deja descargar igual', async () => {
    const { user } = await abrir({ 'POST /api/reportes/exportar': archivo('r.zip', 'no es un zip', 'application/zip') })
    await user.click(boton())
    const d = await dialogo()
    expect(within(d).getByText(/No se pudo armar la vista previa .*Igual podés descargar el archivo/)).toBeInTheDocument()
    await user.click(within(d).getByRole('button', { name: 'Descargar' }))
    expect(bajadas()).toHaveLength(1)
  })

  test.each([
    ['Descartar', (user, d) => user.click(within(d).getByRole('button', { name: 'Descartar' }))],
    ['la cruz', (user, d) => user.click(within(d).getByRole('button', { name: 'Cerrar vista previa' }))],
    ['Escape', (user) => user.keyboard('{Escape}')],
    ['un clic afuera', (user) => user.click(document.querySelector('.rp2-prev-overlay'))],
  ])('cerrar la vista previa con %s descarta el reporte sin descargarlo', async (_, cerrar) => {
    const { user } = await abrir({ 'POST /api/reportes/exportar': archivo('r.zip', zip({ 'a.png': 'png' }), 'application/zip') })
    await user.click(boton())
    await cerrar(user, await dialogo())
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(bajadas()).toHaveLength(0)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:reporte-1')   // la imagen de la vista previa se libera
    expect(within(barra()).queryByText(/Reporte generado|se descargó/)).toBeNull()
    expect(boton()).toBeEnabled()
  })

  test('un clic adentro de la vista previa no la cierra', async () => {
    const { user } = await abrir({ 'POST /api/reportes/exportar': archivo('r.csv', 'a,b\n1,2', 'text/csv') })
    await user.click(boton())
    const d = await dialogo()
    await user.click(within(d).getByText('Vista previa del reporte'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  test('el pedido lleva solo las métricas activas, el rango y las cámaras elegidas', async () => {
    const { user, api } = await abrir({ 'POST /api/reportes/exportar': archivo('r.csv', 'a,b', 'text/csv') })
    await user.click(screen.getByRole('switch', { name: /Seleccionar todo/ }))
    await user.click(screen.getByRole('switch', { name: /Conteo y flujo de personas/ }))
    await user.click(screen.getByRole('switch', { name: /Faltantes y rotación de stock/ }))
    await user.click(screen.getByRole('button', { name: '7 días' }))
    await user.click(screen.getByRole('checkbox', { name: 'Caja' }))
    await user.click(screen.getByRole('checkbox', { name: 'Góndolas' }))
    await user.click(screen.getByRole('radio', { name: /CSV/ }))
    await user.click(boton())
    await dialogo()

    expect(exportaciones(api)[0].cuerpo).toEqual({
      metricas: ['personas_flujo', 'stock_faltantes'], formato: 'csv',
      desde: '2026-10-09', hasta: '2026-10-15', camaras: [4, 2],
    })
  })

  test('mientras genera muestra el progreso y bloquea el botón', async () => {
    let responder
    const { user, api } = await abrir({ 'POST /api/reportes/exportar': () => new Promise((r) => { responder = r }) })
    await user.click(boton())
    expect(boton()).toBeDisabled()
    expect(boton()).toHaveAttribute('aria-busy', 'true')
    expect(boton()).toHaveTextContent('Generando…')
    expect(within(barra()).getByText(/Consultando datos y armando el reporte/)).toBeInTheDocument()
    await user.click(boton())
    expect(exportaciones(api)).toHaveLength(1)

    responder(archivo('optifull_reporte.pdf', '%PDF-1.4', 'application/pdf'))
    await dialogo()
    expect(boton()).toHaveTextContent('Generar reporte')
    expect(boton()).toBeEnabled()
  })

  test('sin Content-Disposition usa un nombre por defecto con la extensión del formato', async () => {
    const { user } = await abrir({ 'POST /api/reportes/exportar': { blob: new Blob(['a']), headers: { 'Content-Type': 'application/pdf' } } })
    await generarYDescargar(user)
    await within(barra()).findByText('✓ optifull_reporte.pdf (1 KB) se descargó correctamente.')
    expect(bajadas()[0].nombre).toBe('optifull_reporte.pdf')
  })

  test('archivos grandes se informan en MB', async () => {
    const { user } = await abrir({ 'POST /api/reportes/exportar': archivo('grande.csv', new Uint8Array(2.5 * 1048576), 'text/csv') })
    await user.click(boton())
    expect(within(await dialogo()).getByText(/grande\.csv · CSV · 2\.5 MB/)).toBeInTheDocument()
  })

  test('libera la URL del archivo descargado a los 10 segundos', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    apiFalsa({ 'GET /api/reportes/opciones': OPCIONES, 'POST /api/reportes/exportar': archivo('r.csv', 'a', 'text/csv') })
    render(<ReportsV2Page />)
    await user.click(await screen.findByRole('button', { name: 'Generar reporte' }))
    await user.click(within(await dialogo()).getByRole('button', { name: 'Descargar' }))
    await within(barra()).findByText(/se descargó correctamente/)
    const url = `blob:reporte-${descargas.length}`
    expect(URL.revokeObjectURL).not.toHaveBeenCalledWith(url)
    vi.advanceTimersByTime(10000)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(url)
    vi.useRealTimers()
  })

  test.each([
    [422, 'No hay gráficos para exportar con los filtros elegidos. Probá ampliar el período o las cámaras.'],
    [400, 'Elegí al menos una métrica para el reporte.'],
    [500, 'No se pudo generar el archivo PDF: font not found'],
  ])('error %i del servidor muestra su mensaje y no abre la vista previa', async (status, error) => {
    const { user } = await abrir({ 'POST /api/reportes/exportar': { status, json: { error } } })
    await user.click(boton())
    expect(await within(barra()).findByText(error)).toHaveAttribute('role', 'alert')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(descargas).toHaveLength(0)
    expect(boton()).toBeEnabled()
  })

  test('error sin cuerpo JSON informa el código HTTP', async () => {
    const { user } = await abrir({ 'POST /api/reportes/exportar': { status: 504, texto: 'Gateway Timeout' } })
    await user.click(boton())
    await within(barra()).findByText('El servidor respondió 504')
  })

  test('falla de red muestra el error y se puede reintentar con éxito', async () => {
    let intentos = 0
    const { user, api } = await abrir({
      'POST /api/reportes/exportar': () => (++intentos === 1 ? new TypeError('Failed to fetch') : archivo('r.csv', 'a', 'text/csv')),
    })
    await user.click(boton())
    await within(barra()).findByText('Failed to fetch')
    await generarYDescargar(user)
    await within(barra()).findByText(/r\.csv .* se descargó correctamente/)
    expect(screen.queryByText('Failed to fetch')).toBeNull()
    expect(exportaciones(api)).toHaveLength(2)
  })

  test('salir de la página durante la generación cancela el pedido sin mostrar errores', async () => {
    let señal
    const errores = vi.spyOn(console, 'error')
    const { user, unmount } = await abrir({
      'POST /api/reportes/exportar': () => new Promise(() => {}),
    })
    window.fetch.mockImplementationOnce((_url, op) => {
      señal = op.signal
      return new Promise((_, rechazar) => op.signal.addEventListener('abort', () => rechazar(new DOMException('aborted', 'AbortError'))))
    })
    await user.click(boton())
    expect(señal.aborted).toBe(false)
    unmount()
    expect(señal.aborted).toBe(true)
    await waitFor(() => expect(errores).not.toHaveBeenCalled())
    expect(descargas).toHaveLength(0)
  })

  test('salir de la página con la vista previa abierta libera sus archivos', async () => {
    const { user, unmount } = await abrir({ 'POST /api/reportes/exportar': archivo('r.pdf', '%PDF', 'application/pdf') })
    await user.click(boton())
    await dialogo()
    unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:reporte-1')
  })
})

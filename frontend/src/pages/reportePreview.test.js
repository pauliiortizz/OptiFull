// Pruebas del lector de la vista previa de reportes (reportePreview.js) con archivos comprimidos de verdad: los ZIP
// de zipfile y los .xlsx de openpyxl vienen con deflate (en ReportsV2Page.test.jsx los ZIP de prueba van sin comprimir).
import { describe, test, expect } from 'vitest'
import { leerZip, parsearCsv } from './reportePreview'

async function deflate(texto) {
  const stream = new Response(new TextEncoder().encode(texto)).body.pipeThrough(new CompressionStream('deflate-raw'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

// ZIP de una entrada comprimida con deflate (metodo 8), como lo escribe zipfile.ZIP_DEFLATED.
async function zipDeflate(nombre, texto) {
  const n = new TextEncoder().encode(nombre)
  const datos = await deflate(texto)
  const local = new Uint8Array(30 + n.length + datos.length)
  const dl = new DataView(local.buffer)
  dl.setUint32(0, 0x04034b50, true); dl.setUint16(8, 8, true); dl.setUint32(18, datos.length, true)
  dl.setUint16(26, n.length, true); local.set(n, 30); local.set(datos, 30 + n.length)
  const central = new Uint8Array(46 + n.length)
  const dc = new DataView(central.buffer)
  dc.setUint32(0, 0x02014b50, true); dc.setUint16(10, 8, true); dc.setUint32(20, datos.length, true)
  dc.setUint16(28, n.length, true); central.set(n, 46)
  const fin = new Uint8Array(22)
  const df = new DataView(fin.buffer)
  df.setUint32(0, 0x06054b50, true); df.setUint16(10, 1, true); df.setUint32(12, central.length, true); df.setUint32(16, local.length, true)
  const todo = new Uint8Array(local.length + central.length + fin.length)
  todo.set(local); todo.set(central, local.length); todo.set(fin, local.length + central.length)
  return todo.buffer
}

describe('vista previa de reportes', () => {
  test('lee entradas comprimidas con deflate', async () => {
    const texto = 'Día,Personas\n' + 'Lunes,12\n'.repeat(200)
    const [entrada] = await leerZip(await zipDeflate('personas.csv', texto))
    expect(entrada.nombre).toBe('personas.csv')
    expect(new TextDecoder().decode(entrada.datos)).toBe(texto)
  })

  test('un archivo que no es ZIP da un error claro', async () => {
    await expect(leerZip(new TextEncoder().encode('hola').buffer)).rejects.toThrow('El archivo no es un ZIP válido.')
  })

  test('CSV: comillas, comas y saltos de línea dentro de una celda; con o sin salto al final', () => {
    expect(parsearCsv('a,b\n"x, y","línea 1\nlínea 2"\n')).toEqual([['a', 'b'], ['x, y', 'línea 1\nlínea 2']])
    expect(parsearCsv('a,b\r\n1,2')).toEqual([['a', 'b'], ['1', '2']])
  })
})

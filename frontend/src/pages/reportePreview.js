// Vista previa de un reporte ya generado (el mismo archivo que se descarga, ver POST /api/reportes/exportar):
// se arma en el navegador, sin pedirle nada mas al servidor. Segun el archivo:
//   PDF          -> se muestra tal cual (visor del navegador)
//   PNG          -> la imagen
//   CSV          -> tabla
//   ZIP          -> cada archivo de adentro (los graficos PNG o las tablas CSV de varias metricas + parametros.txt)
//   XLSX (Excel) -> cada hoja como tabla y sus graficos (un .xlsx es un ZIP con XML adentro)

const decoder = new TextDecoder('utf-8')
const texto = (bytes) => decoder.decode(bytes).replace(/^﻿/, '')   // el CSV viene con BOM (utf-8-sig)

// ── ZIP ──────────────────────────────────────────────────────────────────────
// Lector minimo (directorio central + entradas 'stored' o 'deflate'), suficiente para los ZIP de zipfile y openpyxl.
async function inflar(datos) {
  const stream = new Response(datos).body.pipeThrough(new DecompressionStream('deflate-raw'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

export async function leerZip(buffer) {
  const bytes = new Uint8Array(buffer)
  const dv = new DataView(buffer)
  let fin = -1
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { fin = i; break }
  }
  if (fin < 0) throw new Error('El archivo no es un ZIP válido.')
  const total = dv.getUint16(fin + 10, true)
  let p = dv.getUint32(fin + 16, true)
  const entradas = []
  for (let n = 0; n < total; n++) {
    if (dv.getUint32(p, true) !== 0x02014b50) throw new Error('El ZIP está dañado.')
    const metodo = dv.getUint16(p + 10, true)
    const comprimido = dv.getUint32(p + 20, true)
    const largoNombre = dv.getUint16(p + 28, true)
    const largoExtra = dv.getUint16(p + 30, true)
    const largoComent = dv.getUint16(p + 32, true)
    const local = dv.getUint32(p + 42, true)
    const nombre = decoder.decode(bytes.subarray(p + 46, p + 46 + largoNombre))
    const inicio = local + 30 + dv.getUint16(local + 26, true) + dv.getUint16(local + 28, true)
    const crudo = bytes.subarray(inicio, inicio + comprimido)
    if (!nombre.endsWith('/')) entradas.push({ nombre, datos: metodo === 8 ? await inflar(crudo) : crudo.slice() })
    p += 46 + largoNombre + largoExtra + largoComent
  }
  return entradas
}

// ── CSV ──────────────────────────────────────────────────────────────────────
export function parsearCsv(csv) {
  const filas = []
  let fila = [], celda = '', comillas = false
  for (let i = 0; i < csv.length; i++) {
    const c = csv[i]
    if (comillas) {
      if (c === '"' && csv[i + 1] === '"') { celda += '"'; i++ }
      else if (c === '"') comillas = false
      else celda += c
    } else if (c === '"') comillas = true
    else if (c === ',') { fila.push(celda); celda = '' }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && csv[i + 1] === '\n') i++
      fila.push(celda); filas.push(fila); fila = []; celda = ''
    } else celda += c
  }
  if (celda !== '' || fila.length) { fila.push(celda); filas.push(fila) }
  return filas
}

// ── XLSX ─────────────────────────────────────────────────────────────────────
const xml = (bytes) => new DOMParser().parseFromString(texto(bytes), 'application/xml')
const porNombre = (nodo, tag) => [...nodo.getElementsByTagName('*')].filter((e) => e.localName === tag)
// Excel guarda el float tal cual (8.7 -> 8.699999999999999); se muestra como lo muestra Excel
const numero = (v) => (/^-?\d+\.\d{10,}$/.test(v) ? String(Number(Number(v).toPrecision(12))) : v)
const columna = (ref) => [...ref.replace(/\d+/g, '')].reduce((n, l) => n * 26 + l.charCodeAt(0) - 64, 0) - 1

function hojasXlsx(archivos) {
  const compartidos = archivos['xl/sharedStrings.xml']
    ? porNombre(xml(archivos['xl/sharedStrings.xml']), 'si').map((si) => porNombre(si, 't').map((t) => t.textContent).join(''))
    : []
  // nombre de cada hoja -> su archivo (workbook.xml + sus relaciones)
  const rels = {}
  if (archivos['xl/_rels/workbook.xml.rels']) {
    for (const r of porNombre(xml(archivos['xl/_rels/workbook.xml.rels']), 'Relationship')) {
      rels[r.getAttribute('Id')] = 'xl/' + r.getAttribute('Target').replace(/^\/?xl\//, '')
    }
  }
  const hojas = archivos['xl/workbook.xml'] ? porNombre(xml(archivos['xl/workbook.xml']), 'sheet') : []
  return hojas.map((h, i) => {
    const ruta = rels[h.getAttribute('r:id') || [...h.attributes].find((a) => a.localName === 'id')?.value]
      || `xl/worksheets/sheet${i + 1}.xml`
    const filas = []
    if (archivos[ruta]) {
      for (const row of porNombre(xml(archivos[ruta]), 'row')) {
        const fila = []
        for (const c of porNombre(row, 'c')) {
          const tipo = c.getAttribute('t')
          const v = porNombre(c, 'v')[0]?.textContent ?? ''
          fila[columna(c.getAttribute('r') || 'A')] =
            tipo === 's' ? compartidos[Number(v)] ?? ''
              : tipo === 'inlineStr' ? porNombre(c, 't').map((t) => t.textContent).join('')
                : tipo === 'b' ? (v === '1' ? 'VERDADERO' : 'FALSO') : numero(v)
        }
        filas.push(Array.from(fila, (x) => x ?? ''))
      }
    }
    return { tipo: 'tabla', nombre: h.getAttribute('name') || `Hoja ${i + 1}`, filas }
  })
}

// ── armado ───────────────────────────────────────────────────────────────────
const MIME_IMG = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg' }
const ext = (nombre) => nombre.split('.').pop().toLowerCase()

function parte(nombre, datos) {
  const e = ext(nombre)
  if (MIME_IMG[e]) return { tipo: 'imagen', nombre, url: URL.createObjectURL(new Blob([datos], { type: MIME_IMG[e] })) }
  if (e === 'csv') return { tipo: 'tabla', nombre, filas: parsearCsv(texto(datos)) }
  if (e === 'txt') return { tipo: 'texto', nombre, texto: texto(datos) }
  return null
}

// Vista previa de 'blob' (nombre de archivo 'archivo'): { tipo: 'pdf', url } o { tipo: 'partes', partes: [...] }.
// Las URLs blob: que crea hay que liberarlas con liberarVista() al cerrar.
export async function armarVista(blob, archivo) {
  const e = ext(archivo)
  if (e === 'pdf') return { tipo: 'pdf', url: URL.createObjectURL(new Blob([blob], { type: 'application/pdf' })) }
  const datos = new Uint8Array(await blob.arrayBuffer())
  if (e === 'zip' || e === 'xlsx') {
    const entradas = await leerZip(datos.buffer)
    if (e === 'xlsx') {
      const archivos = Object.fromEntries(entradas.map((x) => [x.nombre, x.datos]))
      // los graficos insertados en el Excel (openpyxl los guarda como xl/media/imageN.jpeg), en orden
      const nro = (nombre) => Number(/(\d+)\.\w+$/.exec(nombre)?.[1] ?? 0)
      const graficos = entradas.filter((x) => x.nombre.startsWith('xl/media/') && MIME_IMG[ext(x.nombre)])
        .sort((a, b) => nro(a.nombre) - nro(b.nombre))
        .map((x, i) => ({ ...parte(x.nombre, x.datos), nombre: `Gráfico ${i + 1}` }))
      return { tipo: 'partes', partes: [...hojasXlsx(archivos), ...graficos] }
    }
    return { tipo: 'partes', partes: entradas.map((x) => parte(x.nombre, x.datos)).filter(Boolean) }
  }
  const unica = parte(archivo, datos)
  return { tipo: 'partes', partes: unica ? [unica] : [] }
}

export function liberarVista(vista) {
  if (!vista) return
  if (vista.url) URL.revokeObjectURL(vista.url)
  for (const p of vista.partes || []) if (p.url) URL.revokeObjectURL(p.url)
}

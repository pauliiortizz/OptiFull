import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useToast, PageHeader } from '../components/Toast'
import {
  IcoDownload, IcoSpinner, IcoCheck2, IcoAlert, IcoCalendar, IcoCam, IcoUsers, IcoBox,
  IcoDocs, IcoStock, IcoCode, IcoHeat, IcoClock,
} from '../components/Icons'
import './ReportsV2Page.css'

// Reportes 2.0 — exportación configurable de métricas.
// Backend: GET /api/reportes/opciones (catálogo, cámaras, rango con datos) y
// POST /api/reportes/exportar (frontend/api/reportes_export.py). La versión
// anterior sigue disponible como página "reports-legacy" (ReportsPage.jsx).

const CATEGORIAS = [
  { id: 'personas', titulo: 'Personas / Afluencia', Ico: IcoUsers },
  { id: 'stock',    titulo: 'Stock y Productos',    Ico: IcoBox },
]
const ICONO_FORMATO = { pdf: IcoDocs, xlsx: IcoStock, csv: IcoCode, png: IcoHeat }
const PRESETS = [['todo', 'Todo'], ['7d', '7 días'], ['30d', '30 días'], ['90d', '90 días']]

const aISO = (d) => d.toISOString().slice(0, 10)
const restarDias = (iso, n) => { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() - n); return aISO(d) }
const fmtFecha = (iso) => (iso ? iso.split('-').reverse().join('/') : '—')
const fmtTamano = (bytes) => (bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`)

// Checkbox nativo con soporte de estado indeterminado (el atributo solo se
// puede setear por propiedad DOM, no como prop de React).
function Check({ checked, indeterminate = false, onChange, children, className = '' }) {
  const ref = useRef(null)
  useEffect(() => { if (ref.current) ref.current.indeterminate = indeterminate }, [indeterminate])
  return (
    <label className={`rp2-check ${className}`}>
      <input ref={ref} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="rp2-check-body">{children}</span>
    </label>
  )
}

function usarOpciones() {
  const [estado, setEstado] = useState({ cargando: true, error: null, datos: null })
  const cargar = useCallback(() => {
    setEstado({ cargando: true, error: null, datos: null })
    fetch('/api/reportes/opciones')
      .then(async (r) => {
        const d = await r.json().catch(() => ({}))
        if (!r.ok) throw new Error(d.error || `Error ${r.status}`)
        setEstado({ cargando: false, error: null, datos: d })
      })
      .catch((e) => setEstado({ cargando: false, error: e.message, datos: null }))
  }, [])
  useEffect(() => { cargar() }, [cargar])
  return { ...estado, recargar: cargar }
}

function ReportsV2Page({ onNavigate = () => {} }) {
  const toast = useToast()
  const { cargando, error, datos, recargar } = usarOpciones()

  const [seleccion, setSeleccion] = useState(null)   // Set de ids; null hasta que cargan las opciones
  const [formato, setFormato] = useState('pdf')
  const [preset, setPreset] = useState('todo')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [camaras, setCamaras] = useState(new Set())  // vacío = todas
  const [generacion, setGeneracion] = useState({ fase: 'idle' })   // idle | cargando | ok | error
  const abortRef = useRef(null)

  useEffect(() => () => abortRef.current?.abort(), [])
  // Por defecto, todas las métricas tildadas.
  useEffect(() => { if (datos && !seleccion) setSeleccion(new Set(datos.metricas.map((m) => m.id))) }, [datos, seleccion])

  const metricas = datos?.metricas ?? []
  const sel = seleccion ?? new Set()
  const todas = metricas.length > 0 && sel.size === metricas.length

  const alternar = (ids, on) => setSeleccion((prev) => {
    const s = new Set(prev)
    ids.forEach((id) => (on ? s.add(id) : s.delete(id)))
    return s
  })

  const aplicarPreset = (p) => {
    setPreset(p)
    if (p === 'todo') { setDesde(''); setHasta(''); return }
    const fin = datos?.fecha_max || aISO(new Date())
    setHasta(fin)
    setDesde(restarDias(fin, { '7d': 6, '30d': 29, '90d': 89 }[p]))
  }
  const cambiarFecha = (setter) => (e) => { setPreset('custom'); setter(e.target.value) }

  const alternarCamara = (id) => setCamaras((prev) => {
    const s = new Set(prev)
    s.has(id) ? s.delete(id) : s.add(id)
    return s
  })

  const rangoInvalido = desde && hasta && desde > hasta
  const puedeGenerar = sel.size > 0 && !rangoInvalido && generacion.fase !== 'cargando'
  const formatoElegido = datos?.formatos.find((f) => f.id === formato)

  const generar = async () => {
    abortRef.current?.abort()
    const ctl = new AbortController()
    abortRef.current = ctl
    setGeneracion({ fase: 'cargando' })
    try {
      const res = await fetch('/api/reportes/exportar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: ctl.signal,
        body: JSON.stringify({
          metricas: [...sel], formato,
          desde: desde || null, hasta: hasta || null, camaras: [...camaras],
        }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.error || `El servidor respondió ${res.status}`)
      }
      const blob = await res.blob()
      const archivo = /filename="?([^";]+)"?/.exec(res.headers.get('Content-Disposition') || '')?.[1] || `optifull_reporte.${formato}`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = archivo
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
      setGeneracion({ fase: 'ok', archivo, tamano: blob.size })
      toast(`Reporte descargado: ${archivo}`, { kind: 'success' })
    } catch (e) {
      if (e.name === 'AbortError') return
      setGeneracion({ fase: 'error', mensaje: e.message })
      toast('No se pudo generar el reporte', { kind: 'warn' })
    }
  }

  const resumenPeriodo = useMemo(() => {
    if (desde && hasta) return `${fmtFecha(desde)} → ${fmtFecha(hasta)}`
    if (desde) return `Desde ${fmtFecha(desde)}`
    if (hasta) return `Hasta ${fmtFecha(hasta)}`
    return 'Todo el período con datos'
  }, [desde, hasta])

  const resumenCamaras = useMemo(() => {
    if (camaras.size === 0) return 'Todas'
    return (datos?.camaras ?? []).filter((c) => camaras.has(c.id)).map((c) => c.nombre).join(', ')
  }, [camaras, datos])

  return (
    <main className="content rp2">
      <PageHeader
        title={<>Reportes <span className="rp2-tag">2.0</span></>}
        subtitle="Elegí qué métricas incluir, el período y el formato de descarga."
        right={
          <button className="btn-sec" onClick={() => onNavigate('reports-legacy')}>
            Ver versión anterior
          </button>
        }
      />

      {cargando && <div className="panel rp2-estado"><IcoSpinner className="rp2-spin" /> Cargando opciones…</div>}

      {error && (
        <div className="panel rp2-estado rp2-error" role="alert">
          <IcoAlert /> <span>No se pudieron cargar las opciones del reporte: {error}</span>
          <button className="btn-sec" onClick={recargar}>Reintentar</button>
        </div>
      )}

      {datos && (
        <div className="rp2-grid">
          <div className="rp2-main">
            {/* 1 · Métricas */}
            <section className="panel" aria-labelledby="rp2-h-metricas">
              <div className="panel-head">
                <div className="panel-title" id="rp2-h-metricas">1 · Métricas a incluir</div>
              </div>
              <Check
                className="rp2-todo"
                checked={todas}
                indeterminate={sel.size > 0 && !todas}
                onChange={(on) => alternar(metricas.map((m) => m.id), on)}
              >
                <b>Seleccionar todo</b>
                <span className="rp2-desc">Descargar el reporte completo ({metricas.length} métricas)</span>
              </Check>

              {CATEGORIAS.map(({ id, titulo, Ico }) => {
                const items = metricas.filter((m) => m.categoria === id)
                if (!items.length) return null
                const n = items.filter((m) => sel.has(m.id)).length
                return (
                  <fieldset key={id} className="rp2-grupo">
                    <legend className="sr-only">{titulo}</legend>
                    <Check
                      className="rp2-grupo-head"
                      checked={n === items.length}
                      indeterminate={n > 0 && n < items.length}
                      onChange={(on) => alternar(items.map((m) => m.id), on)}
                    >
                      <span className="rp2-grupo-titulo"><Ico /> {titulo}</span>
                      <span className="rp2-cuenta">{n}/{items.length}</span>
                    </Check>
                    <div className="rp2-items">
                      {items.map((m) => (
                        <Check key={m.id} checked={sel.has(m.id)} onChange={(on) => alternar([m.id], on)}>
                          <span>{m.titulo}</span>
                          <span className="rp2-desc">{m.descripcion}</span>
                        </Check>
                      ))}
                    </div>
                  </fieldset>
                )
              })}
            </section>

            {/* 2 · Período y cámaras */}
            <section className="panel" aria-labelledby="rp2-h-periodo">
              <div className="panel-head">
                <div className="panel-title" id="rp2-h-periodo"><span className="ico"><IcoCalendar /></span>2 · Período y cámaras</div>
                <div className="range-tabs" role="group" aria-label="Rango rápido">
                  {PRESETS.map(([k, l]) => (
                    <button key={k} type="button" className={preset === k ? 'on' : ''} onClick={() => aplicarPreset(k)}>{l}</button>
                  ))}
                </div>
              </div>
              <div className="rp2-fechas">
                <label className="rp2-campo">
                  <span>Desde</span>
                  <input type="date" value={desde} min={datos.fecha_min || undefined} max={hasta || datos.fecha_max || undefined}
                    onChange={cambiarFecha(setDesde)} aria-invalid={rangoInvalido} />
                </label>
                <label className="rp2-campo">
                  <span>Hasta</span>
                  <input type="date" value={hasta} min={desde || datos.fecha_min || undefined} max={datos.fecha_max || undefined}
                    onChange={cambiarFecha(setHasta)} aria-invalid={rangoInvalido} />
                </label>
              </div>
              {rangoInvalido
                ? <p className="rp2-hint rp2-hint-error" role="alert">La fecha "Desde" no puede ser posterior a "Hasta".</p>
                : <p className="rp2-hint">
                    Datos disponibles del {fmtFecha(datos.fecha_min)} al {fmtFecha(datos.fecha_max)}. Los rangos rápidos se cuentan hacia atrás desde el último día con datos.
                  </p>}

              <div className="rp2-sub"><IcoCam /> Cámaras <span className="rp2-desc">(sin selección = todas)</span></div>
              <div className="rp2-chips" role="group" aria-label="Cámaras">
                {datos.camaras.map((c) => (
                  <button key={c.id} type="button" className={`rp2-chip ${camaras.has(c.id) ? 'on' : ''}`}
                    aria-pressed={camaras.has(c.id)} onClick={() => alternarCamara(c.id)}>
                    {c.nombre}
                  </button>
                ))}
                {camaras.size > 0 && <button type="button" className="rp2-limpiar" onClick={() => setCamaras(new Set())}>Limpiar</button>}
              </div>
              <p className="rp2-hint">Aplica a las métricas de personas y a la ocupación de góndolas; faltantes y rotación de stock no dependen de la cámara.</p>
            </section>

            {/* 3 · Formato */}
            <section className="panel" aria-labelledby="rp2-h-formato">
              <div className="panel-head">
                <div className="panel-title" id="rp2-h-formato">3 · Formato de exportación</div>
              </div>
              <div className="rp2-formatos" role="radiogroup" aria-label="Formato de exportación">
                {datos.formatos.map((f) => {
                  const Ico = ICONO_FORMATO[f.id] || IcoDocs
                  return (
                    <label key={f.id} className={`rp2-formato ${formato === f.id ? 'on' : ''}`}>
                      <input type="radio" name="rp2-formato" value={f.id} checked={formato === f.id} onChange={() => setFormato(f.id)} />
                      <span className="rp2-formato-ico"><Ico /></span>
                      <span className="rp2-formato-txt"><b>{f.titulo}</b><span className="rp2-desc">{f.descripcion}</span></span>
                    </label>
                  )
                })}
              </div>
            </section>
          </div>

          {/* Resumen + acción */}
          <aside className="rp2-side">
            <section className="panel" aria-labelledby="rp2-h-resumen">
              <div className="panel-head">
                <div className="panel-title" id="rp2-h-resumen">Tu reporte</div>
              </div>
              <dl className="rp2-resumen">
                <div><dt>Métricas</dt><dd>{sel.size === 0 ? <span className="rp2-vacio">Ninguna seleccionada</span> : `${sel.size} de ${metricas.length}`}</dd></div>
                <div><dt>Período</dt><dd>{resumenPeriodo}</dd></div>
                <div><dt>Cámaras</dt><dd>{resumenCamaras}</dd></div>
                <div><dt>Formato</dt><dd>{formatoElegido?.titulo}</dd></div>
              </dl>

              <button className="rp2-btn" onClick={generar} disabled={!puedeGenerar} aria-busy={generacion.fase === 'cargando'}>
                {generacion.fase === 'cargando'
                  ? <><IcoSpinner className="rp2-spin" /> Generando…</>
                  : <><IcoDownload /> Generar y descargar reporte</>}
              </button>
              {sel.size === 0 && <p className="rp2-hint">Elegí al menos una métrica para habilitar la descarga.</p>}

              <div className="rp2-feedback" role="status" aria-live="polite">
                {generacion.fase === 'cargando' && (
                  <p className="rp2-msg"><IcoClock /> Consultando datos y armando el archivo. Puede tardar unos segundos.</p>
                )}
                {generacion.fase === 'ok' && (
                  <p className="rp2-msg rp2-ok"><IcoCheck2 /> <span><b>{generacion.archivo}</b> ({fmtTamano(generacion.tamano)}) se descargó correctamente.</span></p>
                )}
                {generacion.fase === 'error' && (
                  <p className="rp2-msg rp2-ko" role="alert"><IcoAlert /> <span>{generacion.mensaje}</span></p>
                )}
              </div>
            </section>
          </aside>
        </div>
      )}
    </main>
  )
}

export { ReportsV2Page }

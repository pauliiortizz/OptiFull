import { useState, useEffect, useLayoutEffect, useMemo, useRef, useCallback } from 'react'
import { IcoDocs, IcoStock, IcoCode, IcoHeat } from '../components/Icons'
import { PageHeader } from '../components/Toast'
import './ReportsV2Page.css'

// Reportes 2.0 — exportación configurable de métricas, con estética iOS
// (fondo agrupado, tarjetas blancas, toggles verdes, checks azules, barras
// con efecto vidrio esmerilado).
// Backend: GET /api/reportes/opciones (catálogo, cámaras, rango con datos) y
// POST /api/reportes/exportar (frontend/api/reportes_export.py). La versión
// anterior sigue disponible como página "reports-legacy" (ReportsPage.jsx).

const CATEGORIAS = [
  { id: 'personas', titulo: 'Personas / Afluencia' },
  { id: 'stock',    titulo: 'Stock y Productos' },
]
const ICONO_FORMATO = { pdf: IcoDocs, xlsx: IcoStock, csv: IcoCode, png: IcoHeat }
const TINTE_FORMATO = { pdf: '255,59,48', xlsx: '52,199,89', csv: '142,142,147', png: '255,149,0' }   // colores del sistema iOS
const PRESETS = [['todo', 'Todo'], ['7d', '7 días'], ['30d', '30 días'], ['90d', '90 días']]

const aISO = (d) => d.toISOString().slice(0, 10)
const restarDias = (iso, n) => { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() - n); return aISO(d) }
const fmtFecha = (iso) => (iso ? iso.split('-').reverse().join('/') : '—')
const fmtTamano = (bytes) => (bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`)

function CheckAzul({ grande = false }) {
  return (
    <svg className={grande ? 'rp2-check-ico rp2-check-ico-lg' : 'rp2-check-ico'} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m4.5 12.5 5 5L19.5 7" />
    </svg>
  )
}

// Fila con toggle verde estilo iOS. Toda la fila es clickeable (label).
function FilaToggle({ checked, onChange, titulo, descripcion, destacada = false }) {
  return (
    <label className={`rp2-row rp2-row-toggle ${destacada ? 'rp2-row-strong' : ''}`}>
      <span className="rp2-row-text">
        <span className="rp2-row-title">{titulo}</span>
        {descripcion && <span className="rp2-row-sub">{descripcion}</span>}
      </span>
      <input type="checkbox" role="switch" className="rp2-switch" checked={checked}
        onChange={(e) => onChange(e.target.checked)} />
    </label>
  )
}

// Control segmentado con indicador deslizante -- misma tecnica que el pill
// activo del Sidebar (medir la posicion real del boton on, trasladar una
// sola capa ahi) en vez de que cada boton prenda/apague su propio fondo.
function SegSlider({ options, value, onChange, ariaLabel }) {
  const wrapRef  = useRef(null);
  const itemRefs = useRef({});
  const [pill, setPill] = useState(null);

  useLayoutEffect(() => {
    const wrap = wrapRef.current;
    const el   = itemRefs.current[value];
    if (!wrap || !el) { setPill(null); return; }
    const wrapRect = wrap.getBoundingClientRect();
    const elRect   = el.getBoundingClientRect();
    setPill({ left: elRect.left - wrapRect.left, width: elRect.width });
  }, [value, options]);

  return (
    <div className="rp2-seg" ref={wrapRef} role="group" aria-label={ariaLabel}>
      {pill && (
        <span className="rp2-seg-pill" aria-hidden="true"
          style={{ transform: `translateX(${pill.left}px)`, width: pill.width }} />
      )}
      {options.map(([k, l]) => (
        <button key={k} type="button" ref={(el) => { itemRefs.current[k] = el; }}
          className={value === k ? 'on' : ''} aria-pressed={value === k}
          onClick={() => onChange(k)}>{l}</button>
      ))}
    </div>
  );
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
  // Por defecto, todas las métricas activadas.
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
    if (s.has(id)) s.delete(id)
    else s.add(id)
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
    } catch (e) {
      if (e.name === 'AbortError') return
      setGeneracion({ fase: 'error', mensaje: e.message })
    }
  }

  const resumenPeriodo = useMemo(() => {
    if (desde && hasta) return `${fmtFecha(desde)} → ${fmtFecha(hasta)}`
    if (desde) return `Desde ${fmtFecha(desde)}`
    if (hasta) return `Hasta ${fmtFecha(hasta)}`
    return 'Todo el período'
  }, [desde, hasta])

  const resumenCamaras = useMemo(() => {
    if (camaras.size === 0) return 'Todas las cámaras'
    return (datos?.camaras ?? []).filter((c) => camaras.has(c.id)).map((c) => c.nombre).join(', ')
  }, [camaras, datos])

  return (
    <main className="content rp2">
      <PageHeader
        title="Reportes"
        tag="2.0"
        subtitle="Elegí qué métricas incluir, el período y el formato de descarga. El resumen operativo con cifras en vivo vive en el Dashboard."
        right={<button type="button" className="rp2-link" onClick={() => onNavigate('reports-legacy')}>Versión anterior</button>}
      />

      <div className="rp2-wrap">
        {cargando && <div className="rp2-card rp2-estado"><span className="rp2-spinner rp2-spinner-dark" /> Cargando opciones…</div>}

        {error && (
          <div className="rp2-card rp2-estado rp2-error" role="alert">
            <span>No se pudieron cargar las opciones del reporte: {error}</span>
            <button type="button" className="rp2-link" onClick={recargar}>Reintentar</button>
          </div>
        )}

        {datos && (
          <div className="rp2-cols">
            <div className="rp2-col">
            {/* Métricas */}
            <section aria-labelledby="rp2-h-todo">
              <div className="rp2-card">
                <FilaToggle destacada checked={todas} onChange={(on) => alternar(metricas.map((m) => m.id), on)}
                  titulo={<span id="rp2-h-todo">Seleccionar todo</span>}
                  descripcion={`Descargar el reporte completo (${metricas.length} métricas)`} />
              </div>
            </section>

            {CATEGORIAS.map(({ id, titulo }) => {
              const items = metricas.filter((m) => m.categoria === id)
              if (!items.length) return null
              const n = items.filter((m) => sel.has(m.id)).length
              return (
                <section key={id} aria-label={titulo}>
                  <h2 className="rp2-sec-h">{titulo}<span className="rp2-sec-count">{n} de {items.length}</span></h2>
                  <div className="rp2-card">
                    {items.map((m) => (
                      <FilaToggle key={m.id} checked={sel.has(m.id)} onChange={(on) => alternar([m.id], on)}
                        titulo={m.titulo} descripcion={m.descripcion} />
                    ))}
                  </div>
                </section>
              )
            })}

            </div>
            <div className="rp2-col">
            {/* Período */}
            <section aria-labelledby="rp2-h-periodo">
              <h2 className="rp2-sec-h" id="rp2-h-periodo">Período</h2>
              <div className="rp2-card">
                <div className="rp2-row rp2-row-seg">
                  <SegSlider options={PRESETS} value={preset} onChange={aplicarPreset} ariaLabel="Rango rápido" />
                </div>
                <label className="rp2-row">
                  <span className="rp2-row-title">Desde</span>
                  <input type="date" className="rp2-date" value={desde} min={datos.fecha_min || undefined}
                    max={hasta || datos.fecha_max || undefined} onChange={cambiarFecha(setDesde)} aria-invalid={rangoInvalido} />
                </label>
                <label className="rp2-row">
                  <span className="rp2-row-title">Hasta</span>
                  <input type="date" className="rp2-date" value={hasta} min={desde || datos.fecha_min || undefined}
                    max={datos.fecha_max || undefined} onChange={cambiarFecha(setHasta)} aria-invalid={rangoInvalido} />
                </label>
              </div>
              {rangoInvalido
                ? <p className="rp2-sec-f rp2-sec-f-error" role="alert">La fecha "Desde" no puede ser posterior a "Hasta".</p>
                : <p className="rp2-sec-f">Datos disponibles del {fmtFecha(datos.fecha_min)} al {fmtFecha(datos.fecha_max)}. Los rangos rápidos se cuentan hacia atrás desde el último día con datos.</p>}
            </section>

            {/* Cámaras */}
            <section aria-labelledby="rp2-h-camaras">
              <h2 className="rp2-sec-h" id="rp2-h-camaras">Cámaras</h2>
              <div className="rp2-card" role="group" aria-label="Cámaras">
                {datos.camaras.map((c) => {
                  const on = camaras.has(c.id)
                  return (
                    <button key={c.id} type="button" role="checkbox" aria-checked={on}
                      className="rp2-row rp2-row-btn" onClick={() => alternarCamara(c.id)}>
                      <span className="rp2-row-title">{c.nombre}</span>
                      {on && <CheckAzul />}
                    </button>
                  )
                })}
              </div>
              <p className="rp2-sec-f">
                Sin selección se incluyen todas. Aplica a las métricas de personas y a la ocupación de góndolas; faltantes y rotación de stock no dependen de la cámara.
                {camaras.size > 0 && <> <button type="button" className="rp2-link rp2-link-inline" onClick={() => setCamaras(new Set())}>Quitar selección</button></>}
              </p>
            </section>

            {/* Formato */}
            <section aria-labelledby="rp2-h-formato">
              <h2 className="rp2-sec-h" id="rp2-h-formato">Formato de exportación</h2>
              <div className="rp2-formatos" role="radiogroup" aria-label="Formato de exportación">
                {datos.formatos.map((f) => {
                  const Ico = ICONO_FORMATO[f.id] || IcoDocs
                  const on = formato === f.id
                  return (
                    <label key={f.id} className={`rp2-formato ${on ? 'on' : ''}`}>
                      <input type="radio" name="rp2-formato" value={f.id} checked={on} onChange={() => setFormato(f.id)} />
                      <span className="rp2-formato-ico" style={{ background: `rgba(${TINTE_FORMATO[f.id] || '142,142,147'},.14)` }}><Ico /></span>
                      <span className="rp2-formato-txt"><b>{f.titulo}</b><span>{f.descripcion}</span></span>
                      {on && <span className="rp2-formato-badge"><CheckAzul grande /></span>}
                    </label>
                  )
                })}
              </div>
            </section>
            </div>
          </div>
        )}
      </div>

      {/* Barra inferior con efecto vidrio esmerilado: resumen + acción */}
      {datos && (
        <footer className="rp2-bar">
          <div className="rp2-bar-inner">
            <div className="rp2-bar-info" aria-live="polite">
              <span className="rp2-bar-main">
                {sel.size === 0 ? <span className="rp2-vacio">Ninguna métrica seleccionada</span> : `${sel.size} de ${metricas.length} métricas`}
                {' · '}{formatoElegido?.titulo}
              </span>
              <span className="rp2-bar-sub">{resumenPeriodo} · {resumenCamaras}</span>
              <span className="rp2-feedback" role="status">
                {generacion.fase === 'cargando' && 'Consultando datos y armando el archivo. Puede tardar unos segundos…'}
                {generacion.fase === 'ok' && <span className="rp2-ok">✓ {generacion.archivo} ({fmtTamano(generacion.tamano)}) se descargó correctamente.</span>}
                {generacion.fase === 'error' && <span className="rp2-ko" role="alert">{generacion.mensaje}</span>}
              </span>
            </div>
            <button type="button" className="rp2-btn" onClick={generar} disabled={!puedeGenerar}
              aria-busy={generacion.fase === 'cargando'}>
              {generacion.fase === 'cargando' ? <><span className="rp2-spinner" /> Generando…</> : 'Generar y descargar reporte'}
            </button>
          </div>
        </footer>
      )}
    </main>
  )
}

export { ReportsV2Page }

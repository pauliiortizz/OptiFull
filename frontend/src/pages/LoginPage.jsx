import { useRef, useState } from 'react'
import { Logo } from '../components/Logo'
import { guardarSesion } from '../components/useSesion'
import { ThemeToggle } from '../components/ThemeToggle'
import '../efectos/seguir.css'
import { estira, reduceMovimiento } from '../efectos/seguir.js'
import './LoginPage.css'

// Pantalla de inicio de sesión. "Ya soy cliente" de la landing lleva acá y, al ingresar, se pasa al panel
// ("/dashboard"). Las cuentas las crea el administrador de la sucursal: no hay registro.
export function LoginPage({ onLogin, onBack, onDemo }) {
  const [usuario, setUsuario] = useState('')
  const [clave, setClave] = useState('')
  const [verClave, setVerClave] = useState(false)
  const [mantener, setMantener] = useState(true)
  const [enviando, setEnviando] = useState(false)
  const [errores, setErrores] = useState({})          // { usuario, clave, general }
  const [listo, setListo] = useState(false)           // ingreso confirmado: el botón muestra «¡Listo!»
  const boton = useRef(null)

  const cambiar = (campo, setter) => (e) => {
    setter(e.target.value)
    if (errores[campo] || errores.general) setErrores((x) => ({ ...x, [campo]: undefined, general: undefined }))
  }

  const ingresar = (e) => {
    e.preventDefault()
    // Validación en la pantalla (el servidor repite la misma validación).
    const faltan = {}
    if (!usuario.trim()) faltan.usuario = 'Completá el usuario o el email.'
    if (!clave) faltan.clave = 'Completá la contraseña.'
    if (faltan.usuario || faltan.clave) {
      setErrores(faltan)
      estira(boton.current, false)
      document.getElementById(faltan.usuario ? 'login-usuario' : 'login-clave')?.focus()
      return
    }
    setEnviando(true)
    setErrores({})
    estira(boton.current)
    fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario: usuario.trim(), clave, mantener }),
    })
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (!ok || !d.ok) {
          setErrores(d.campos ? { ...d.campos } : { general: d.error || 'No se pudo iniciar sesión.' })
          estira(boton.current, false)
          setEnviando(false)
          return
        }
        guardarSesion(d, mantener)
        // la sesión ya quedó guardada; se espera solo a que se dibuje la palomita antes de pasar al panel
        setListo(true)
        setTimeout(() => onLogin(d), reduceMovimiento() ? 0 : 750)
      })
      .catch(() => {
        setErrores({ general: 'No se pudo conectar con el servidor. Probá de nuevo en un momento.' })
        estira(boton.current, false)
        setEnviando(false)
      })
  }

  return (
    <div className="landing login">
      <div className="landing-frame">
        <header className="landing-head">
          <Logo className="landing-logo" />
          <div className="landing-nav">
            <button type="button" className="landing-client-link" onClick={onBack}>← Volver al inicio</button>
            <ThemeToggle />
          </div>
        </header>

        <main className="login-main">
          <div className="login-wrap">
            <div className="login-intro">
              <h1 className="login-title">Iniciá sesión</h1>
              <p className="login-sub">Accedé al panel de tu sucursal.</p>
            </div>

            <form className="login-card" onSubmit={ingresar} noValidate>
              <div className="login-field">
                <label htmlFor="login-usuario">Email o usuario</label>
                <input id="login-usuario" type="text" name="usuario" autoComplete="username" autoFocus
                  placeholder="nombre@tutienda.com" value={usuario} onChange={cambiar('usuario', setUsuario)}
                  aria-invalid={!!errores.usuario} aria-describedby={errores.usuario ? 'login-usuario-error' : undefined} />
                {errores.usuario && <p className="login-field-error" id="login-usuario-error" role="alert">{errores.usuario}</p>}
              </div>

              <div className="login-field">
                <label htmlFor="login-clave">Contraseña</label>
                <span className="login-pwd">
                  <input id="login-clave" type={verClave ? 'text' : 'password'} name="clave" autoComplete="current-password"
                    placeholder="••••••••" value={clave} onChange={cambiar('clave', setClave)}
                    aria-invalid={!!errores.clave} aria-describedby={errores.clave ? 'login-clave-error' : undefined} />
                  <button type="button" className="login-eye" onClick={() => setVerClave((v) => !v)}
                    aria-label={verClave ? 'Ocultar contraseña' : 'Mostrar contraseña'} aria-pressed={verClave}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" />
                      {verClave && <path d="M3 3l18 18" />}
                    </svg>
                  </button>
                </span>
                {errores.clave && <p className="login-field-error" id="login-clave-error" role="alert">{errores.clave}</p>}
              </div>

              <label className="login-check">
                <input type="checkbox" checked={mantener} onChange={(e) => setMantener(e.target.checked)} />
                Mantener sesión iniciada
              </label>

              {errores.general && <p className="login-error" role="alert">{errores.general}</p>}

              {/* data-sin-iman: el estirón y el imán usan transform y ::before/::after del mismo botón */}
              <button type="submit" ref={boton} className={'btn-primary login-submit sg-boton' + (listo ? ' is-sigue' : '')}
                disabled={enviando} aria-busy={enviando && !listo} data-sin-iman>
                <span className="sg-fondo" aria-hidden="true" />
                <span className="sg-cara sg-antes" aria-hidden={listo}>{enviando ? 'Ingresando…' : 'Ingresar'}</span>
                <span className="sg-cara sg-despues" aria-hidden={!listo}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.6 4.6L19 7.5" /></svg>
                  ¡Listo!
                </span>
              </button>

              <p className="login-note">
                Las cuentas las crea el administrador de tu sucursal. Si no tenés acceso, pedíselo a él.
              </p>
            </form>

            <p className="login-demo">
              ¿Tu tienda todavía no usa OptiFull?{' '}
              <button type="button" className="login-link" onClick={onDemo} data-sin-iman>Pedí una demo</button>
            </p>
          </div>
        </main>
      </div>
    </div>
  )
}

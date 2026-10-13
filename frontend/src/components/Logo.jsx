import logoDia from '../assets/logo-dia.png'
import logoNoche from '../assets/logo-noche.png'
import iconoDia from '../assets/icono-dia.png'
import iconoNoche from '../assets/icono-noche.png'

// Logo de OptiFull en sus dos versiones: la de modo día (marca oscura) y la de modo noche (marca clara). Se
// renderizan las dos y el CSS muestra la que corresponde según <html data-theme> (ver index.css), así el cambio
// de modo no necesita recargar nada ni parpadea. 'icono' es solo el círculo (menú lateral plegado).
export function Logo({ className = '', icono = false }) {
  const [dia, noche] = icono ? [iconoDia, iconoNoche] : [logoDia, logoNoche]
  return (
    <>
      <img className={`logo-dia ${className}`.trim()} src={dia} alt="OptiFull" />
      <img className={`logo-noche ${className}`.trim()} src={noche} alt="OptiFull" />
    </>
  )
}

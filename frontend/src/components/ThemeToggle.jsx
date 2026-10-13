import { useTheme } from './useTheme'
import { IcoSun, IcoMoon } from './Icons'

// Botón para pasar de modo día a modo noche y viceversa (misma lógica que el del panel, ver useTheme.js).
// Muestra el ícono del modo al que se va a cambiar: sol estando de noche, luna estando de día.
export function ThemeToggle({ className = '' }) {
  const { tema, alternar } = useTheme()
  const aNoche = tema !== 'dark'
  const etiqueta = aNoche ? 'Cambiar a modo noche' : 'Cambiar a modo día'
  return (
    <button type="button" className={`theme-toggle ${className}`.trim()} onClick={alternar}
      aria-label={etiqueta} title={etiqueta}>
      {aNoche ? <IcoMoon /> : <IcoSun />}
    </button>
  )
}

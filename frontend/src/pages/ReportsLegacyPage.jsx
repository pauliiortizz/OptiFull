import { ReportsPage } from './ReportsPage'
import './ReportsV2Page.css'

// Respaldo de la versión anterior de Reportes (ReportsPage.jsx, sin cambios).
// Solo agrega una barra para volver a Reportes 2.0.
function ReportsLegacyPage({ onNavigate = () => {} }) {
  return (
    <>
      <div className="rp2-legacy-bar" role="note">
        <span>Estás viendo la <b>versión anterior</b> de Reportes (respaldo).</span>
        <button type="button" className="btn-sec" onClick={() => onNavigate('reports')}>Ir a Reportes 2.0</button>
      </div>
      <ReportsPage />
    </>
  )
}

export { ReportsLegacyPage }

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './efectos/iman.css'
import { iniciarImanes } from './efectos/iman.js'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// efecto magnético en botones, pestañas y navegación (excepto los data-sin-iman)
iniciarImanes()

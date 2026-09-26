import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import './styles/global.css'
import './styles/layout.css'
import './styles/ui.css'
import './styles/dashboard.css'
import './styles/calendar.css'
import './styles/insights.css'
import './styles/owl.css'
import './styles/experiments.css'

const container = document.getElementById('root')
if (!container) {
  throw new Error('Root container #root is missing from index.html.')
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

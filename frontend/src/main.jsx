import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { SiteInfoProvider } from './hooks/useSiteInfo'
import './styles/global.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <SiteInfoProvider>
        <App />
      </SiteInfoProvider>
    </BrowserRouter>
  </StrictMode>,
)

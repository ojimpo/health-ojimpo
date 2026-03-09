import { Routes, Route } from 'react-router-dom'
import DashboardPage from './pages/DashboardPage'
import SharedViewPage from './pages/SharedViewPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<SharedViewPage />} />
      <Route path="/shared/:token" element={<SharedViewPage />} />
      <Route path="/admin" element={<DashboardPage />} />
      <Route path="/settings" element={<SettingsPage />} />
    </Routes>
  )
}

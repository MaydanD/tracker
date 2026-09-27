import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './layout/AppShell'
import { AreasPage } from './pages/AreasPage'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { CheckInPage } from './pages/CheckInPage'
import { DashboardPage } from './pages/DashboardPage'
import { ExperimentDetailPage } from './pages/ExperimentDetailPage'
import { ExperimentsPage } from './pages/ExperimentsPage'
import { HabitsPage } from './pages/HabitsPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { SettingsPage } from './pages/SettingsPage'

/**
 * HashRouter on purpose: the future pywebview/PyInstaller build loads the SPA
 * straight from disk, where the History API is unavailable. Using hashes now
 * means desktop packaging will not require rewriting navigation.
 */
export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="check-in" element={<CheckInPage />} />
          <Route path="calendar" element={<Navigate to="/analytics" replace />} />
          <Route path="habits" element={<HabitsPage />} />
          <Route path="areas" element={<AreasPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="insights" element={<Navigate to="/analytics" replace />} />
          <Route path="experiments" element={<ExperimentsPage />} />
          <Route path="experiments/:experimentId" element={<ExperimentDetailPage />} />
          <Route path="records" element={<Navigate to="/analytics" replace />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}

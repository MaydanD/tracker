import { HashRouter, Route, Routes } from 'react-router-dom'

import { AppShell } from './layout/AppShell'
import { AreasPage } from './pages/AreasPage'
import { CalendarPage } from './pages/CalendarPage'
import { CheckInPage } from './pages/CheckInPage'
import { DashboardPage } from './pages/DashboardPage'
import { ExperimentsPage } from './pages/ExperimentsPage'
import { HabitsPage } from './pages/HabitsPage'
import { InsightsPage } from './pages/InsightsPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { RecordsPage } from './pages/RecordsPage'
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
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="habits" element={<HabitsPage />} />
          <Route path="areas" element={<AreasPage />} />
          <Route path="insights" element={<InsightsPage />} />
          <Route path="experiments" element={<ExperimentsPage />} />
          <Route path="records" element={<RecordsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}

import { Outlet, useLocation } from 'react-router-dom'

import { BackendStatus } from '../components/BackendStatus'
import { useBackendStatus } from '../hooks/useBackendStatus'
import { NAVIGATION_ITEMS } from '../navigation'
import { Sidebar } from './Sidebar'

/**
 * Application frame: sidebar navigation, a header showing the live backend
 * state, and the routed content area.
 */
export function AppShell() {
  const backend = useBackendStatus()
  const location = useLocation()
  const current = NAVIGATION_ITEMS.find((item) => item.path === location.pathname)

  return (
    <div className="shell">
      <Sidebar />
      <div className="shell__main">
        <header className="topbar">
          <div>
            <p className="topbar__eyebrow">Tracker</p>
            <h2 className="topbar__title">{current?.label ?? 'Unknown screen'}</h2>
          </div>
          <BackendStatus backend={backend} />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

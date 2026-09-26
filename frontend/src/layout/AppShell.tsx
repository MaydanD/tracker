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
  // Exact route first, then the longest parent section: a detail page such as
  // `/experiments/3` still belongs to the «Эксперименты» section.
  const current =
    NAVIGATION_ITEMS.find((item) => item.path === location.pathname)
    ?? NAVIGATION_ITEMS
      .filter((item) => item.path !== '/' && location.pathname.startsWith(`${item.path}/`))
      .sort((a, b) => b.path.length - a.path.length)[0]

  return (
    <div className="shell">
      <Sidebar />
      <div className="shell__main">
        <header className="topbar">
          <div>
            <p className="topbar__eyebrow">Tracker</p>
            <h2 className="topbar__title">{current?.label ?? 'Неизвестный раздел'}</h2>
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

import { useEffect } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'

import { OwlLogo } from '../components/owl/OwlLogo'
import { useTodayLabel } from '../hooks/useTodayLabel'
import { NAVIGATION_ITEMS } from '../navigation'
import { telegramAction } from '../api/backup'

/**
 * Application frame: a single compact navigation bar that carries the brand and
 * every main navigation link, with the routed content area underneath it.
 *
 * Backend state deliberately lives on the Settings screen, not here: the bar
 * stays a bar.
 */
export function AppShell() {
  const location = useLocation()
  const today = useTodayLabel()
  useEffect(() => {
    const check = () => { void telegramAction('auto').catch(() => { /* Settings shows persisted errors. */ }) }
    check()
    window.addEventListener('focus', check)
    return () => window.removeEventListener('focus', check)
  }, [today])
  // Exact route first, then the longest parent section: a detail page such as
  // `/experiments/3` still belongs to the «Эксперименты» section.
  const current =
    NAVIGATION_ITEMS.find((item) => item.path === location.pathname)
    ?? NAVIGATION_ITEMS
      .filter((item) => item.path !== '/' && location.pathname.startsWith(`${item.path}/`))
      .sort((a, b) => b.path.length - a.path.length)[0]

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__lead">
          <OwlLogo />
          <Link to="/" className="topbar__name">
            Tracker
          </Link>
          <span className="topbar__title">{current?.label ?? 'Неизвестный раздел'}</span>
        </div>

        {/* Today, in two short lines: it fits inside the mascot's height. */}
        <div className="topbar__today">
          <span className="topbar__today-label">Сегодня</span>
          <span className="topbar__today-date">{today}</span>
        </div>

        <nav className="topnav" aria-label="Основная навигация">
          <ul>
            {NAVIGATION_ITEMS.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  end={item.path === '/'}
                  className={({ isActive }) =>
                    isActive ? 'nav-link nav-link--active' : 'nav-link'
                  }
                  title={item.summary}
                >
                  <span className="nav-link__label">{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}

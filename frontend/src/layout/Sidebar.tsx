import { NavLink } from 'react-router-dom'

import { NAVIGATION_ITEMS } from '../navigation'

export function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__logo" aria-hidden="true">
          ◉
        </span>
        <div>
          <p className="sidebar__name">Tracker</p>
          <p className="sidebar__tagline">Привычки, самочувствие и аналитика</p>
        </div>
      </div>

      <nav className="sidebar__nav" aria-label="Основная навигация">
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
                <span className="nav-link__stage">{item.plannedIn}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <footer className="sidebar__footer">
        <p>Этапы 1–2 — Основа и настройка</p>
        <p>Для вас · данные на компьютере</p>
      </footer>
    </aside>
  )
}

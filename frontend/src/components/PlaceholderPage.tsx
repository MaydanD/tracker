import type { ReactNode } from 'react'

export interface PlaceholderPageProps {
  title: string
  summary: string
  plannedIn: string
  children?: ReactNode
}

/**
 * Stage 1 screens are intentionally empty: this renders the shell's content
 * area with a clear statement of what the screen will become and when.
 */
export function PlaceholderPage({
  title,
  summary,
  plannedIn,
  children,
}: PlaceholderPageProps) {
  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">{title}</h1>
        <span className="badge">Planned for {plannedIn}</span>
      </header>
      <p className="page__summary">{summary}</p>
      {children}
      <div className="placeholder">
        <p className="placeholder__title">Not implemented yet</p>
        <p className="placeholder__text">
          Stage 1 delivers the foundation only — database, migrations, API shell,
          health checks and this application frame. The screen above is added in{' '}
          {plannedIn}.
        </p>
      </div>
    </section>
  )
}

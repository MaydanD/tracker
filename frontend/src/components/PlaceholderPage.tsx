import type { ReactNode } from 'react'

export interface PlaceholderPageProps {
  title: string
  summary: string
  plannedIn: string
  children?: ReactNode
}

/**
 * Этап 1 screens are intentionally empty: this renders the shell's content
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
        <span className="badge">Запланировано: {plannedIn}</span>
      </header>
      <p className="page__summary">{summary}</p>
      {children}
      <div className="placeholder">
        <p className="placeholder__title">Раздел пока в разработке</p>
        <p className="placeholder__text">
          Сейчас доступны сферы, настройка привычек и отметки по дням. Этот раздел
          появится позже: {plannedIn}.
        </p>
      </div>
    </section>
  )
}

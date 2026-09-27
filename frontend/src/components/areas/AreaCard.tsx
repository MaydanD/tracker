import type { ReactNode } from 'react'

import type { Area } from '../../api/types'

interface AreaCardProps {
  area: Area
  habitCount: number
  busy: boolean
  formOpen: boolean
  onEdit: () => void
  onArchive: () => void
  onUnarchive: () => void
  onAddHabit: () => void
  children: ReactNode
}

export function AreaCard({
  area, habitCount, busy, formOpen, onEdit, onArchive, onUnarchive, onAddHabit, children,
}: AreaCardProps) {
  return (
    <section className="habit-area" aria-labelledby={`area-${area.id}`} style={{ borderLeftColor: area.color }}>
      <header className="habit-area__header">
        <div className="habit-area__identity">
          <h2 className="habit-area__title" id={`area-${area.id}`}>
            <span className="swatch" style={{ backgroundColor: area.color }} aria-hidden="true" />
            {area.name}
          </h2>
          <span className="habit-group__count">Привычек: {habitCount}</span>
          {area.is_archived ? <span className="badge badge--muted">Сфера в архиве</span> : null}
        </div>
        <div className="list__actions">
          <button type="button" className="button button--small" onClick={onEdit} disabled={busy || formOpen}>
            Изменить сферу
          </button>
          <button
            type="button" className="button button--small"
            onClick={area.is_archived ? onUnarchive : onArchive} disabled={busy || formOpen}
          >
            {area.is_archived ? 'Восстановить сферу' : 'Архивировать сферу'}
          </button>
          {!area.is_archived ? (
            <button type="button" className="button button--small button--primary" onClick={onAddHabit} disabled={busy || formOpen}>
              Добавить привычку
            </button>
          ) : null}
        </div>
      </header>
      {children}
    </section>
  )
}

import type { Habit } from '../../api/types'
import { configurationDateLabel, weightLabel, scheduleLabel, trackingModeLabel } from './options'

export interface HabitListProps {
  habits: Habit[]
  onEdit: (habit: Habit) => void
  onArchive: (habit: Habit) => void
  onUnarchive: (habit: Habit) => void
  onToggleHistory: (habit: Habit) => void
  historyHabitId?: number | null
  busyId?: number | null
  editingId?: number | null
  actionsDisabled?: boolean
}

export function HabitList({
  habits,
  onEdit,
  onArchive,
  onUnarchive,
  onToggleHistory,
  historyHabitId = null,
  busyId = null,
  editingId = null,
  actionsDisabled = false,
}: HabitListProps) {
  return (
    <ul className="list habit-list">
      {habits.map((habit) => {
        const busy = busyId === habit.id
        return (
          <li
            key={habit.id}
            className={`list__row list__row--stacked${
              editingId === habit.id ? ' list__row--active' : ''
            }${habit.is_archived ? ' list__row--archived' : ''}`}
          >
            <span className="list__main">
              <span className="list__title">
                {habit.name}
                {habit.is_archived ? (
                  <span className="badge badge--muted">В архиве</span>
                ) : null}
              </span>
              <span className="list__meta">
                <span className="pill">Важность: {weightLabel(habit.weight)}</span>
                <span className="pill">
                  {trackingModeLabel(
                    habit.tracking_mode,
                    habit.quantity_unit,
                    habit.value_type,
                  )}
                </span>
                <span className="pill">{scheduleLabel(habit.schedule)}</span>
                <span className="pill">
                  Версия {habit.current_version.version_number} с{' '}
                  {configurationDateLabel(habit.current_version.effective_from)}
                </span>
              </span>
              {habit.description ? (
                <span className="list__note">{habit.description}</span>
              ) : null}
            </span>

            <span className="list__actions">
              <button
                type="button"
                className="button button--small"
                onClick={() => onEdit(habit)}
                disabled={busy || actionsDisabled}
              >
                Изменить
              </button>
              <button
                type="button"
                className="button button--small"
                onClick={() => onToggleHistory(habit)}
                aria-expanded={historyHabitId === habit.id}
              >
                {historyHabitId === habit.id ? 'Скрыть историю' : 'История'}
              </button>
              {habit.is_archived ? (
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => onUnarchive(habit)}
                  disabled={busy || actionsDisabled}
                >
                  Восстановить
                </button>
              ) : (
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => onArchive(habit)}
                  disabled={busy || actionsDisabled}
                >
                  В архив
                </button>
              )}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

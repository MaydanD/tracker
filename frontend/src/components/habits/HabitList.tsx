import type { Habit } from '../../api/types'
import { configurationDateLabel, scheduleLabel, trackingModeLabel, weightLabel } from './options'

export interface HabitListProps {
  habits: Habit[]
  onEdit: (habit: Habit) => void
  onArchive: (habit: Habit) => void
  onUnarchive: (habit: Habit) => void
  onToggleHistory: (habit: Habit) => void
  historyHabitId?: number | null
  busyId?: number | null
  editingId?: number | null
}

interface AreaGroup {
  areaName: string
  areaColor: string
  habits: Habit[]
}

/** Group habits by their current area, preserving the API's ordering. */
function groupByArea(habits: Habit[]): AreaGroup[] {
  const groups = new Map<number, AreaGroup>()
  for (const habit of habits) {
    const existing = groups.get(habit.area.id)
    if (existing) {
      existing.habits.push(habit)
    } else {
      groups.set(habit.area.id, {
        areaName: habit.area.name,
        areaColor: habit.area.color,
        habits: [habit],
      })
    }
  }
  return [...groups.values()]
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
}: HabitListProps) {
  return (
    <div className="habit-groups">
      {groupByArea(habits).map((group) => (
        <section key={group.areaName} className="habit-group">
          <h3 className="habit-group__heading">
            <span
              className="swatch swatch--small"
              style={{ backgroundColor: group.areaColor }}
              aria-hidden="true"
            />
            {group.areaName}
            <span className="habit-group__count">
              Привычек: {group.habits.length}
            </span>
          </h3>

          <ul className="list">
            {group.habits.map((habit) => {
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
                      <span className="pill">Важность {habit.weight} ·{' '}
                        {weightLabel(habit.weight)}
                      </span>
                      <span className="pill">
                        {trackingModeLabel(habit.tracking_mode, habit.quantity_unit)}
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
                      disabled={busy}
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
                        disabled={busy}
                      >
                        Восстановить
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="button button--small"
                        onClick={() => onArchive(habit)}
                        disabled={busy}
                      >
                        В архив
                      </button>
                    )}
                  </span>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>
  )
}

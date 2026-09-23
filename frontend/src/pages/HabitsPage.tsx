import { useMemo, useState } from 'react'

import { describeApiError } from '../api/client'
import { archiveHabit, unarchiveHabit } from '../api/habits'
import type { Habit } from '../api/types'
import { EmptyState, ErrorBanner, LoadingText } from '../components/Feedback'
import { HabitForm, type AreaOption } from '../components/habits/HabitForm'
import { HabitHistory } from '../components/habits/HabitHistory'
import { HabitList } from '../components/habits/HabitList'
import { useAreas } from '../hooks/useAreas'
import { useHabits } from '../hooks/useHabits'

export function HabitsPage() {
  const [includeArchived, setIncludeArchived] = useState(false)
  const [areaFilter, setAreaFilter] = useState<number | null>(null)

  const { habits, loading, error, reload } = useHabits({
    includeArchived,
    areaId: areaFilter,
  })
  const { areas, error: areasError } = useAreas(false)

  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Habit | null>(null)
  const [historyHabitId, setHistoryHabitId] = useState<number | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  // A habit may belong to an area that has since been archived; it must still
  // be selectable while editing that habit.
  const areaOptions = useMemo<AreaOption[]>(() => {
    const options = areas.map((area) => ({ id: area.id, name: area.name }))
    if (editing && !options.some((option) => option.id === editing.area_id)) {
      options.push({
        id: editing.area_id,
        name: `${editing.area.name} (в архиве)`,
      })
    }
    return options
  }, [areas, editing])

  function closeForm() {
    setCreating(false)
    setEditing(null)
  }

  async function handleArchive(habit: Habit) {
    setBusyId(habit.id)
    setActionError(null)
    try {
      await archiveHabit(habit.id)
      if (editing?.id === habit.id) closeForm()
      if (historyHabitId === habit.id) setHistoryHabitId(null)
      reload()
    } catch (cause) {
      setActionError(describeApiError(cause))
    } finally {
      setBusyId(null)
    }
  }

  async function handleUnarchive(habit: Habit) {
    setBusyId(habit.id)
    setActionError(null)
    try {
      await unarchiveHabit(habit.id)
      reload()
    } catch (cause) {
      setActionError(describeApiError(cause))
    } finally {
      setBusyId(null)
    }
  }

  function afterSave() {
    closeForm()
    reload()
  }

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Привычки</h1>
        <span className="badge">Этап 2</span>
      </header>
      <p className="page__summary">
        Настройте действия, которые хотите выполнять регулярно. Изменения
        настроек сохраняются по дням; правки в течение одного дня объединяются.
        Отмечать выполнение можно будет на этапе 3.
      </p>

      <div className="toolbar">
        <button
          type="button"
          className="button button--primary"
          onClick={() => {
            setEditing(null)
            setCreating(true)
          }}
          disabled={creating || editing !== null}
        >
          Новая привычка
        </button>

        <label className="field field--inline">
          <span className="field__label">Фильтр по сфере</span>
          <select
            className="field__input"
            value={areaFilter === null ? '' : String(areaFilter)}
            onChange={(event) =>
              setAreaFilter(event.target.value === '' ? null : Number(event.target.value))
            }
          >
            <option value="">Все сферы</option>
            {areaOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
          />
          <span>Показывать архивные</span>
        </label>
      </div>

      <ErrorBanner message={actionError} />
      <ErrorBanner message={areasError} />
      <ErrorBanner message={error} />

      {creating || editing ? (
        <HabitForm
          key={editing?.id ?? 'new'}
          areas={areaOptions}
          habit={editing}
          onSaved={afterSave}
          onCancel={closeForm}
        />
      ) : null}

      {loading ? (
        <LoadingText>Загрузка привычек…</LoadingText>
      ) : habits.length === 0 ? (
        <EmptyState>
          {includeArchived || areaFilter !== null
            ? 'По выбранным фильтрам привычек нет.'
            : 'Привычек пока нет. Сначала создайте сферу, затем добавьте привычку.'}
        </EmptyState>
      ) : (
        <HabitList
          habits={habits}
          busyId={busyId}
          editingId={editing?.id ?? null}
          historyHabitId={historyHabitId}
          onEdit={(habit) => {
            setCreating(false)
            setEditing(habit)
          }}
          onArchive={handleArchive}
          onUnarchive={handleUnarchive}
          onToggleHistory={(habit) =>
            setHistoryHabitId((current) => (current === habit.id ? null : habit.id))
          }
        />
      )}

      {historyHabitId !== null ? (
        <section className="card">
          <h3 className="card__title">История настроек</h3>
          <HabitHistory habitId={historyHabitId} />
        </section>
      ) : null}
    </section>
  )
}

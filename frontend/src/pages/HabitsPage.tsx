import { useMemo, useState } from 'react'

import { archiveArea, unarchiveArea } from '../api/areas'
import { describeApiError } from '../api/client'
import { archiveHabit, unarchiveHabit } from '../api/habits'
import type { Area, Habit } from '../api/types'
import { AreaCard } from '../components/areas/AreaCard'
import { AreaForm } from '../components/areas/AreaForm'
import { EmptyState, ErrorBanner, LoadingText } from '../components/Feedback'
import { HabitForm, type AreaOption } from '../components/habits/HabitForm'
import { HabitHistory } from '../components/habits/HabitHistory'
import { HabitList } from '../components/habits/HabitList'
import { useAreas } from '../hooks/useAreas'
import { useHabits } from '../hooks/useHabits'

// A single editor keeps drafts in their area and prevents competing forms.
type Editor =
  | { kind: 'area'; area: Area | null }
  | { kind: 'habit'; habit: Habit | null; areaId?: number }
  | null

export function HabitsPage() {
  const [includeArchived, setIncludeArchived] = useState(false)
  const [areaFilter, setAreaFilter] = useState<number | null>(null)
  const { habits, loading, error, reload } = useHabits({ includeArchived, areaId: null })
  // Load all parents so archived habits always have their own area card.
  const { areas, loading: areasLoading, error: areasError, reload: reloadAreas } = useAreas(true)
  const [editor, setEditor] = useState<Editor>(null)
  const [historyHabitId, setHistoryHabitId] = useState<number | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [busyAreaId, setBusyAreaId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const editing = editor?.kind === 'habit' ? editor.habit : null
  const areaOptions = useMemo<AreaOption[]>(() => {
    const options = areas.filter((area) => !area.is_archived).map(({ id, name }) => ({ id, name }))
    if (editing && !options.some((option) => option.id === editing.area_id)) {
      const ownArea = areas.find((area) => area.id === editing.area_id) ?? editing.area
      options.push({ id: ownArea.id, name: `${ownArea.name} (в архиве)` })
    }
    return options
  }, [areas, editing])

  const groups = useMemo(() => {
    const byArea = new Map<number, Habit[]>()
    for (const habit of habits) {
      const group = byArea.get(habit.area_id) ?? []
      group.push(habit)
      byArea.set(habit.area_id, group)
    }
    return areas
      .filter((area) => includeArchived || !area.is_archived || byArea.has(area.id))
      .map((area) => ({ area, habits: byArea.get(area.id) ?? [] }))
  }, [areas, habits, includeArchived])
  const visibleGroups = groups.filter(({ area }) => areaFilter === null || area.id === areaFilter)

  function refresh() {
    reloadAreas()
    reload()
  }

  async function changeHabitArchive(habit: Habit) {
    setBusyId(habit.id)
    setActionError(null)
    try {
      await (habit.is_archived ? unarchiveHabit(habit.id) : archiveHabit(habit.id))
      if (historyHabitId === habit.id) setHistoryHabitId(null)
      reload()
    } catch (cause) {
      setActionError(describeApiError(cause))
    } finally {
      setBusyId(null)
    }
  }

  async function changeAreaArchive(area: Area) {
    setBusyAreaId(area.id)
    setActionError(null)
    try {
      await (area.is_archived ? unarchiveArea(area.id) : archiveArea(area.id))
      if (!includeArchived && areaFilter === area.id) setAreaFilter(null)
      refresh()
    } catch (cause) {
      setActionError(describeApiError(cause))
    } finally {
      setBusyAreaId(null)
    }
  }

  function afterHabitSave(habit: Habit) {
    setEditor(null)
    // A moved habit remains visible even when the old area was filtered.
    if (areaFilter !== null) setAreaFilter(habit.area_id)
    refresh()
  }

  function afterAreaSave(area: Area) {
    setEditor(null)
    if (areaFilter !== null) setAreaFilter(area.id)
    refresh()
  }

  function habitForm() {
    if (editor?.kind !== 'habit') return null
    return (
      <HabitForm
        key={editor.habit?.id ?? `new-${editor.areaId ?? 'global'}`}
        areas={areaOptions} habit={editor.habit} areaId={editor.areaId}
        onSaved={afterHabitSave} onCancel={() => setEditor(null)}
      />
    )
  }

  return (
    <section className="page habits-page">
      <header className="page__header">
        <h1 className="page__title">Привычки</h1>
      </header>
      <div className="toolbar">
        <button type="button" className="button button--primary" disabled={editor !== null}
          onClick={() => setEditor({ kind: 'area', area: null })}>
          Добавить сферу
        </button>
        <button type="button" className="button" disabled={editor !== null}
          onClick={() => setEditor({ kind: 'habit', habit: null })}>
          Новая привычка
        </button>
        <label className="field field--inline">
          <span className="field__label">Фильтр по сфере</span>
          <select className="field__input" value={areaFilter ?? ''} disabled={editor !== null}
            onChange={(event) => setAreaFilter(event.target.value === '' ? null : Number(event.target.value))}>
            <option value="">Все сферы</option>
            {groups.map(({ area }) => <option key={area.id} value={area.id}>{area.name}</option>)}
          </select>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={includeArchived} disabled={editor !== null}
            onChange={(event) => {
              setIncludeArchived(event.target.checked)
              setAreaFilter(null)
            }} />
          <span>Показывать архивные</span>
        </label>
      </div>

      <ErrorBanner message={actionError} />
      <ErrorBanner message={areasError} />
      <ErrorBanner message={error} />

      {editor?.kind === 'area' && !editor.area ? (
        <AreaForm existingColors={areas.map((area) => area.color)}
          onSaved={afterAreaSave} onCancel={() => setEditor(null)} />
      ) : null}
      {editor?.kind === 'habit' && !editor.habit && editor.areaId === undefined ? habitForm() : null}

      {loading || areasLoading ? <LoadingText>Загрузка привычек…</LoadingText> : null}
      {!loading && !areasLoading && !error && !areasError && visibleGroups.length === 0 ? (
        <EmptyState>
          {includeArchived ? 'Сфер пока нет. Добавьте первую сферу.' : 'Нет активных сфер. Создайте сферу, чтобы добавить привычки.'}
        </EmptyState>
      ) : null}
      <div className="habit-groups">
        {visibleGroups.map(({ area, habits: areaHabits }) => (
          <AreaCard key={area.id} area={area} habitCount={areaHabits.length}
            busy={busyAreaId === area.id} formOpen={editor !== null}
            onEdit={() => setEditor({ kind: 'area', area })}
            onArchive={() => changeAreaArchive(area)} onUnarchive={() => changeAreaArchive(area)}
            onAddHabit={() => setEditor({ kind: 'habit', habit: null, areaId: area.id })}>
            {editor?.kind === 'area' && editor.area?.id === area.id ? (
              <AreaForm key={area.id} area={editor.area} onSaved={afterAreaSave} onCancel={() => setEditor(null)} />
            ) : null}
            {editor?.kind === 'habit' && (editor.habit?.area_id ?? editor.areaId) === area.id ? habitForm() : null}
            {areaHabits.length === 0 ? (
              <p className="habit-area__empty">Пока нет привычек</p>
            ) : (
              <HabitList habits={areaHabits} busyId={busyId} editingId={editing?.id}
                actionsDisabled={editor !== null} historyHabitId={historyHabitId}
                onEdit={(habit) => setEditor({ kind: 'habit', habit })}
                onArchive={changeHabitArchive} onUnarchive={changeHabitArchive}
                onToggleHistory={(habit) => setHistoryHabitId((current) => current === habit.id ? null : habit.id)} />
            )}
            {historyHabitId !== null && areaHabits.some((habit) => habit.id === historyHabitId) ? (
              <section className="card habit-area__history">
                <h3 className="card__title">История настроек</h3>
                <HabitHistory key={historyHabitId} habitId={historyHabitId} />
              </section>
            ) : null}
          </AreaCard>
        ))}
      </div>
    </section>
  )
}

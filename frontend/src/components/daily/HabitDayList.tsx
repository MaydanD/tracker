import type { DayItem, ProgressState } from '../../api/types'
import { resolveOwlAsset } from '../owl/owlAssets'
import { DayHabitRow, entryKey } from './DayHabitRow'

export interface HabitDayListProps {
  items: DayItem[]
  entryDate: string
  isFuture: boolean
  onChanged: () => void
  progress?: ProgressState | null
}

/** Summary of a fully-marked day: a real state, not an empty screen. */
function DayComplete({ items }: { items: DayItem[] }) {
  const done = items.filter((item) => item.entry?.status === 'done').length
  const missed = items.filter((item) => item.entry?.status === 'missed').length
  const skipped = items.filter((item) => item.entry?.status === 'skipped').length
  const allDone = done === items.length

  return (
    <section className="day-complete" aria-label="Состояние дня">
      <img
        className="day-complete__image"
        src={resolveOwlAsset(allDone ? 'owl_all_done' : 'owl_pending')}
        alt="Сова Tracker"
      />
      <div className="day-complete__body">
        <h2 className="day-complete__title">
          {allDone ? 'День завершён' : 'Все привычки отмечены'}
        </h2>
        <p className="day-complete__text">
          {allDone
            ? 'Все привычки на этот день выполнены. Отличная работа!'
            : `Выполнено: ${done}, пропущено: ${missed}, осознанно пропущено: ${skipped}. Записи можно изменить ниже.`}
        </p>
      </div>
    </section>
  )
}

/**
 * Every habit that existed on the chosen date, split by what still needs doing.
 *
 * The point of the screen is the habits the user has *not* marked yet, so those
 * stay in view. Already-recorded habits move into a collapsed «Уже отмечено»
 * block — nothing is removed, hidden read-only or made unreachable; it is one
 * click away and still fully editable. When nothing is left to mark, the day
 * shows a finished state (with the Owl) instead of an empty screen.
 *
 * The row key combines the date with the stored record, so a row's draft is
 * rebuilt from the server as soon as what is stored changes. A save can never
 * leave a field showing something that is no longer true, and moving to another
 * day never carries a draft across.
 */
export function HabitDayList({
  items,
  entryDate,
  isFuture,
  onChanged,
  progress,
}: HabitDayListProps) {
  const open = items.filter((item) => item.entry === null)
  const recorded = items.filter((item) => item.entry !== null)
  const mixed = open.length > 0 && recorded.length > 0

  const render = (item: DayItem) => (
    <DayHabitRow
      key={`${entryDate}:${entryKey(item.habit_id, item.entry)}`}
      item={item}
      entryDate={entryDate}
      isFuture={isFuture}
      onChanged={onChanged}
      streak={progress?.streaks.find((s) => s.habit_id === item.habit_id)}
      weekProgress={progress?.week.habits.find((p) => p.habit_id === item.habit_id)}
    />
  )

  return (
    <div className="day-sections">
      {open.length === 0 && recorded.length > 0 ? <DayComplete items={recorded} /> : null}

      {open.length > 0 ? (
        <>
          {mixed ? <h2 className="day-sections__title">Осталось отметить</h2> : null}
          <ul className="day-list">{open.map(render)}</ul>
        </>
      ) : null}

      {recorded.length > 0 ? (
        <details className="day-recorded">
          <summary className="day-recorded__summary">{`Уже отмечено · ${recorded.length}`}</summary>
          <ul className="day-list day-recorded__list">{recorded.map(render)}</ul>
        </details>
      ) : null}
    </div>
  )
}

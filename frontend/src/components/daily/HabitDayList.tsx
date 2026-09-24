import type { DayItem } from '../../api/types'
import { DayHabitRow, entryKey } from './DayHabitRow'

export interface HabitDayListProps {
  items: DayItem[]
  entryDate: string
  isFuture: boolean
  onChanged: () => void
}

/**
 * Every habit that existed on the chosen date.
 *
 * The key combines the date with the stored record, so a row's draft is rebuilt
 * from the server as soon as what is stored changes. A save can therefore never
 * leave a field showing something that is no longer true, and moving to another
 * day never carries a draft across.
 */
export function HabitDayList({
  items,
  entryDate,
  isFuture,
  onChanged,
}: HabitDayListProps) {
  return (
    <ul className="day-list">
      {items.map((item) => (
        <DayHabitRow
          key={`${entryDate}:${entryKey(item.habit_id, item.entry)}`}
          item={item}
          entryDate={entryDate}
          isFuture={isFuture}
          onChanged={onChanged}
        />
      ))}
    </ul>
  )
}

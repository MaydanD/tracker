import { addDays, formatDayLabel, relativeDayLabel } from './dates'

export interface DayNavigatorProps {
  entryDate: string
  /** The server's date; the authority for «Сегодня» and the future rules. */
  today: string
  disabled?: boolean
  onChange: (entryDate: string) => void
}

/**
 * Pick the day being recorded: previous, next, today, or an explicit date.
 *
 * The date is a plain calendar date and never crosses a timezone: the value sent
 * to the API is the same string the user sees.
 */
export function DayNavigator({
  entryDate,
  today,
  disabled = false,
  onChange,
}: DayNavigatorProps) {
  const relative = relativeDayLabel(entryDate, today)

  return (
    <section className="day-nav" aria-label="Выбор дня">
      <div className="day-nav__label">
        <h2 className="day-nav__date">{formatDayLabel(entryDate)}</h2>
        {relative !== null ? <span className="badge">{relative}</span> : null}
      </div>

      <div className="day-nav__controls">
        <button
          type="button"
          className="button button--small"
          onClick={() => onChange(addDays(entryDate, -1))}
          disabled={disabled}
        >
          ← Предыдущий день
        </button>
        <button
          type="button"
          className="button button--small"
          onClick={() => onChange(addDays(entryDate, 1))}
          disabled={disabled}
        >
          Следующий день →
        </button>
        <button
          type="button"
          className="button button--small"
          onClick={() => onChange(today)}
          disabled={disabled || entryDate === today}
        >
          Сегодня
        </button>

        <label className="field field--inline">
          <span className="field__label">Дата</span>
          <input
            type="date"
            className="field__input field__input--date"
            value={entryDate}
            onChange={(event) => {
              if (event.target.value !== '') onChange(event.target.value)
            }}
            disabled={disabled}
          />
        </label>
      </div>
    </section>
  )
}

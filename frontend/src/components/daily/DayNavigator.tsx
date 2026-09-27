import { addDays, formatDayLabel, relativeDayLabel } from './dates'

export interface DayNavigatorProps {
  entryDate: string
  /** The server's date; the authority for «Сегодня» and the future rules. */
  today: string
  disabled?: boolean
  onChange: (entryDate: string) => void
}

/**
 * Compact date navigator.
 *
 * Fits in a single horizontal row on desktop: date label on the left, all
 * controls on the right.  The date input is intentionally kept small and
 * inline — it's an escape hatch, not the primary way to pick a date.
 */
export function DayNavigator({
  entryDate,
  today,
  disabled = false,
  onChange,
}: DayNavigatorProps) {
  const relative = relativeDayLabel(entryDate, today)

  return (
    <nav className="day-nav" aria-label="Выбор дня">
      {/* ── Left: current date label ───────────────────────── */}
      <div className="day-nav__label">
        <span className="day-nav__date">{formatDayLabel(entryDate)}</span>
        {relative !== null ? (
          <span className="badge day-nav__badge">{relative}</span>
        ) : null}
      </div>

      {/* ── Right: navigation controls ─────────────────────── */}
      <div className="day-nav__controls">
        <button
          type="button"
          className="button button--small button--icon-text"
          aria-label="Предыдущий день"
          onClick={() => onChange(addDays(entryDate, -1))}
          disabled={disabled}
        >
          ←
        </button>
        <button
          type="button"
          className="button button--small button--icon-text"
          aria-label="Следующий день"
          onClick={() => onChange(addDays(entryDate, 1))}
          disabled={disabled}
        >
          →
        </button>
        <button
          type="button"
          className="button button--small"
          onClick={() => onChange(today)}
          disabled={disabled || entryDate === today}
        >
          Сегодня
        </button>

        <input
          type="date"
          className="field__input field__input--date day-nav__date-input"
          aria-label="Выбрать дату"
          value={entryDate}
          onChange={(e) => {
            if (e.target.value !== '') onChange(e.target.value)
          }}
          disabled={disabled}
        />
      </div>
    </nav>
  )
}

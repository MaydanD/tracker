import { fetchCalendarRange, type CalendarDaySummaryRead } from '../../api/calendar'
import { useAsyncData } from '../../hooks/useAsyncData'
import { ErrorBanner, LoadingText } from '../Feedback'
import { addDays, formatDayLabel, parseIsoDate } from './dates'
import '../../styles/recent-days.css'

function status(day: CalendarDaySummaryRead) {
  if (day.is_future || day.total_items === undefined) return 'unknown'
  if (day.total_items === 0) return 'empty'
  return day.answered_items === day.total_items ? 'complete' : 'incomplete'
}

function description(day: CalendarDaySummaryRead) {
  switch (status(day)) {
    case 'complete': return 'Заполнено'
    case 'incomplete': return `Отмечено ${day.answered_items} из ${day.total_items}`
    case 'empty': return 'Нет привычек'
    default: return 'Нет данных'
  }
}

export function RecentDays({ today, selectedDate, onSelect, revision = 0, missedOnly = false }: {
  today: string
  selectedDate?: string
  onSelect?: (date: string) => void
  revision?: number
  missedOnly?: boolean
}) {
  const end = missedOnly ? addDays(today, -1) : today
  const start = addDays(end, missedOnly ? -29 : -9)
  const { data, loading, error, reload } = useAsyncData(
    (signal) => fetchCalendarRange(start, end, signal),
    [start, end, revision],
  )
  const days = (data ?? []).filter(day => day.entry_date >= start && day.entry_date <= end
    && (!missedOnly || status(day) === 'incomplete'))
  if (missedOnly && data && !loading && !error && days.length === 0) return null

  return <section className={`recent-days${missedOnly ? ' recent-days--missed' : ''}`}
    aria-label={missedOnly ? 'Незаполненные дни' : 'Последние 10 дней'}>
    <div className="recent-days__header">
      <h2>{missedOnly ? 'Остались незаполненные дни' : 'Последние 10 дней'}</h2>
      <p>{missedOnly
        ? 'За последние 30 дней · выберите дату, чтобы добавить отметки'
        : 'Зелёный — всё заполнено · красный — есть пустые отметки'}</p>
    </div>
    {error ? <>
      <ErrorBanner message={error} />
      <button className="button button--small" onClick={reload}>Повторить загрузку дней</button>
    </> : loading && !data ? <LoadingText>Загрузка дней…</LoadingText> : null}
    <div className="recent-days__list" aria-busy={loading}>
      {days.map(day => {
        const date = parseIsoDate(day.entry_date)
        const label = `${formatDayLabel(day.entry_date)}: ${description(day)}`
        const className = `recent-day recent-day--${status(day)}`
        const content = <>
          <span className="recent-day__weekday">{day.entry_date === today ? 'Сегодня' : date.toLocaleDateString('ru-RU', { weekday: 'short' })}</span>
          <strong>{date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</strong>
          <span className="recent-day__status">{status(day) === 'complete' ? '✓ Заполнено'
            : status(day) === 'incomplete' ? `${day.answered_items} / ${day.total_items}` : '—'}</span>
        </>
        return missedOnly ? <a key={day.entry_date} href={`#/check-in?date=${day.entry_date}`}
          className={className} aria-label={label} title={label}>{content}</a>
          : <button key={day.entry_date} type="button" className={className}
            aria-label={label} title={label} aria-pressed={day.entry_date === selectedDate}
            onClick={() => onSelect?.(day.entry_date)}>{content}</button>
      })}
    </div>
  </section>
}

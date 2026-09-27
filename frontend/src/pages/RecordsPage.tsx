import { fetchRecords } from '../api/records'
import type { RecordsRead } from '../api/records'
import { EmptyState, ErrorBanner, LoadingText } from '../components/Feedback'
import { RecordCard } from '../components/records/RecordCard'
import { formatMonth, formatPercent, formatRange, streakValue } from '../components/records/recordsLabels'
import { useAsyncData } from '../hooks/useAsyncData'
import { formatShortDateLabel } from '../utils/dateUtils'

export function HabitRecordsSection() {
  const { data, error, loading, reload } = useAsyncData((signal) => fetchRecords(signal), [])

  return (
    <section className="page analytics-records" aria-label="Рекорды привычек">
      <header className="page__header">
        <h2 className="page__title">Рекорды по привычкам</h2>
      </header>
      <ErrorBanner message={error} />
      {loading && data === null ? <LoadingText>Загрузка рекордов…</LoadingText> : null}
      {error !== null && data === null ? (
        <button className="button" onClick={reload}>Повторить попытку</button>
      ) : null}
      {data !== null ? <HabitRecords data={data} /> : null}
    </section>
  )
}

export function RecordsPage() {
  return <HabitRecordsSection />
}

function HabitRecords({ data }: { data: RecordsRead }) {
  const { longest_streak: streak, consistency } = data.records

  if (streak === null && consistency.length === 0) {
    return <EmptyState>Рекордов по привычкам пока нет.</EmptyState>
  }

  return (
    <div className="records-grid">
      {streak !== null ? (
        <RecordCard
          tone="accent"
          title="Лучшая серия"
          value={streakValue(streak.best_streak, streak.unit)}
          context={streak.archived ? `${streak.name} · в архиве` : streak.name}
          meta={
            streak.best_start !== null && streak.best_end !== null
              ? formatRange(streak.best_start, streak.best_end)
              : null
          }
          footnote={
            streak.current_streak > 0
              ? `Сейчас идёт: ${streakValue(streak.current_streak, streak.unit)}`
              : 'Сейчас серия не идёт.'
          }
        />
      ) : null}

      {consistency.map((item) => (
        <RecordCard
          key={item.habit_id}
          title="Стабильность привычки"
          value={formatPercent(item.ratio)}
          context={item.archived ? `${item.name} · в архиве` : item.name}
          meta={formatMonth(item.period_start)}
          footnote={`${item.done_days} из ${item.obligation_days} дней · ${formatShortDateLabel(item.period_start)} — ${formatShortDateLabel(item.period_end)}`}
        />
      ))}
    </div>
  )
}

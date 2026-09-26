import { fetchRecords } from '../api/records'
import type { RecordsRead } from '../api/records'
import { EmptyState, ErrorBanner, LoadingText } from '../components/Feedback'
import { AchievementCard } from '../components/records/AchievementCard'
import { RecordCard } from '../components/records/RecordCard'
import {
  formatCount,
  formatMonth,
  formatPercent,
  formatRange,
  streakValue,
  summaryLines,
} from '../components/records/recordsLabels'
import { useAsyncData } from '../hooks/useAsyncData'
import { formatShortDateLabel } from '../utils/dateUtils'

export function RecordsPage() {
  const { data, error, loading, reload } = useAsyncData((signal) => fetchRecords(signal), [])

  if (loading && data === null) {
    return (
      <section className="page">
        <LoadingText>Загрузка рекордов…</LoadingText>
      </section>
    )
  }

  if (error !== null || data === null) {
    return (
      <section className="page">
        <ErrorBanner message={error ?? 'Не удалось загрузить рекорды'} />
        <button className="button" onClick={reload}>Повторить попытку</button>
      </section>
    )
  }

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Рекорды и достижения</h1>
        <span className="badge">Этап 11</span>
      </header>
      <p className="page__summary">
        Личные рекорды и вехи, собранные из вашей истории: серии, лучшие дни и недели,
        стабильность привычек и пройденные этапы. Рекорды пересчитываются из текущих
        данных — если записи изменятся, изменятся и они.
      </p>

      <ErrorBanner message={error} />

      <Summary data={data} />

      <h2 className="records-section__title">Личные рекорды</h2>
      <Records data={data} />

      <h2 className="records-section__title">Достижения</h2>
      <Achievements data={data} />
    </section>
  )
}

function Summary({ data }: { data: RecordsRead }) {
  return (
    <section className="records-summary" aria-label="Общая статистика">
      {summaryLines(data.summary).map((line) => (
        <p key={line} className="records-summary__line">{line}</p>
      ))}
      <p className="records-summary__line">
        {data.summary.first_tracked_day !== null
          ? `Первая запись: ${formatShortDateLabel(data.summary.first_tracked_day)}`
          : 'Пока нет ни одной записи.'}
      </p>
    </section>
  )
}

function Records({ data }: { data: RecordsRead }) {
  const { records } = data
  const streak = records.longest_streak
  const hasAny =
    streak !== null || records.best_day !== null || records.best_week !== null
    || records.most_completed !== null || records.consistency.length > 0

  if (!hasAny) {
    return <EmptyState>Рекордов пока нет. Начните отмечать привычки — и они появятся.</EmptyState>
  }

  return (
    <div className="records-grid">
      {streak !== null ? (
        <RecordCard
          tone="accent"
          title="Самая длинная серия"
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

      {records.best_day !== null ? (
        <RecordCard
          title="Лучший день"
          value={formatPercent(records.best_day.score)}
          context={`Выполнено: ${records.best_day.completed_weight} / ${records.best_day.required_weight}`}
          meta={`Дата: ${formatShortDateLabel(records.best_day.day)}`}
          footnote={
            records.best_day.ties > 1
              ? `Таких же лучших дней: ${formatCount(records.best_day.ties)}`
              : null
          }
        />
      ) : null}

      {records.best_week !== null ? (
        <RecordCard
          title="Лучшая неделя"
          value={formatPercent(records.best_week.score)}
          context={records.best_week.coverage !== null
            ? `Покрытие: ${Math.round(records.best_week.coverage * 100)}%`
            : null}
          meta={formatRange(records.best_week.week_start, records.best_week.week_end)}
          footnote={
            records.best_week.ties > 1
              ? `Таких же лучших недель: ${formatCount(records.best_week.ties)}`
              : null
          }
        />
      ) : null}

      {records.most_completed !== null ? (
        <RecordCard
          title="Больше всего привычек за день"
          value={`${formatCount(records.most_completed.completed_count)}`}
          context={`Из ${formatCount(records.most_completed.required_count)} обязательных`}
          meta={`Дата: ${formatShortDateLabel(records.most_completed.day)}`}
          footnote={
            records.most_completed.ties > 1
              ? `Таких же дней: ${formatCount(records.most_completed.ties)}`
              : null
          }
        />
      ) : null}

      {records.consistency.length > 0 ? (
        <article className="record-card record-card--wide">
          <h3 className="record-card__title">Самая стабильная привычка</h3>
          <ul className="record-consistency">
            {records.consistency.map((item) => (
              <li key={item.habit_id} className="record-consistency__row">
                <span className="record-consistency__name">
                  {item.archived ? `${item.name} · в архиве` : item.name}
                </span>
                <span className="record-consistency__value">{formatPercent(item.ratio)}</span>
                <span className="record-consistency__meta">
                  {`${formatMonth(item.period_start)} · ${formatCount(item.done_days)} из ${formatCount(item.obligation_days)} дней`}
                </span>
              </li>
            ))}
          </ul>
          <p className="record-card__footnote">
            Считаются только полностью прошедшие месяцы с достаточным числом дней.
          </p>
        </article>
      ) : null}
    </div>
  )
}

function Achievements({ data }: { data: RecordsRead }) {
  const recentKeys = new Set(data.recent_achievements.map((item) => item.key))
  const achieved = data.achievements.filter((item) => item.achieved)
  const older = achieved.filter((item) => !recentKeys.has(item.key))
  const locked = data.achievements.filter((item) => !item.achieved)

  return (
    <section className="achievements" aria-label="Достижения">
      <p className="achievements__count">
        {`Получено ${formatCount(data.achieved_count)} из ${formatCount(data.total_count)}`}
      </p>

      {data.recent_achievements.length > 0 ? (
        <>
          <h3 className="achievements__subtitle">Недавно получено</h3>
          <ul className="achievements__list">
            {data.recent_achievements.map((item) => (
              <AchievementCard key={item.key} achievement={item} />
            ))}
          </ul>
        </>
      ) : null}

      {older.length > 0 ? (
        <>
          <h3 className="achievements__subtitle">Полученные</h3>
          <ul className="achievements__list">
            {older.map((item) => (
              <AchievementCard key={item.key} achievement={item} />
            ))}
          </ul>
        </>
      ) : null}

      <h3 className="achievements__subtitle">Следующие цели</h3>
      {locked.length === 0 ? (
        <p className="achievements__empty">
          Все достижения из списка уже получены.
        </p>
      ) : (
        <ul className="achievements__list">
          {locked.map((item) => (
            <AchievementCard key={item.key} achievement={item} />
          ))}
        </ul>
      )}
    </section>
  )
}

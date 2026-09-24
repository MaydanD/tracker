import { fetchDashboard } from '../api/dashboard'
import { ErrorBanner, LoadingText } from '../components/Feedback'
import { statusLabel } from '../components/daily/status'
import { useAsyncData } from '../hooks/useAsyncData'
import { formatFullDateLabel, formatShortDateLabel } from '../utils/dateUtils'
import { formatMinutes, formatPreferredWeekdays, formatSleepStatus, formatStreakText } from '../utils/formatters'

const WEEK_STATUS_LABELS: Record<string, string> = {
  satisfied: 'Выполнено',
  pending: 'В процессе',
  failed: 'Не выполнено',
}

export function DashboardPage() {
  const { data, error, loading, reload } = useAsyncData((signal) => fetchDashboard(signal), [])

  if (loading) {
    return (
      <section className="page">
        <LoadingText>Загрузка главного экрана…</LoadingText>
      </section>
    )
  }

  if (error || !data) {
    return (
      <section className="page">
        <ErrorBanner message={error ?? 'Не удалось загрузить данные'} />
        <button className="button" onClick={reload}>Повторить попытку</button>
      </section>
    )
  }

  const { today, today_progress, week_progress, streaks, yesterday_state, today_items } = data

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Главный обзор</h1>
        <span className="badge">Этап 6</span>
      </header>
      <p className="page__summary">
        Обзор вашей активности: результаты сегодняшнего дня, прогресс текущей недели,
        серии выполнений и вчерашнее состояние.
      </p>

      <div className="dashboard-grid">
        {/* Card 1: Сегодня */}
        <section className="dashboard-card" aria-label="Сегодня">
          <header className="dashboard-card__header">
            <h2 className="dashboard-card__title">Сегодня</h2>
            <span className="badge">{formatFullDateLabel(today)}</span>
          </header>

          <div className="dashboard-card__score">
            <span className="dashboard-card__score-value">
              {today_progress.score === null
                ? '—'
                : `${today_progress.score.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`}
            </span>
            <span className="dashboard-card__score-sub">
              {today_progress.score === null
                ? 'Нет обязательных привычек'
                : `Важность: ${today_progress.completed_weight} / ${today_progress.required_weight}`}
            </span>
          </div>

          <h3 className="card__title">Привычки на сегодня</h3>
          {today_items.length === 0 ? (
            <p className="loading">На сегодня привычки не запланированы.</p>
          ) : (
            <ul className="dashboard-habits-list">
              {today_items.map((item) => {
                const statusText = item.entry ? statusLabel(item.entry.status) : 'Нет отметки'
                const statusClass = item.entry ? `state--${item.entry.status}` : 'state--none'
                return (
                  <li key={item.habit_id} className="dashboard-habit-item">
                    <div className="dashboard-habit-item__main">
                      <span className="dashboard-habit-item__name">{item.name}</span>
                      {item.entry?.quantity_value !== null && item.entry?.quantity_value !== undefined ? (
                        <span className="dashboard-habit-item__meta">
                          {item.entry.quantity_value} {item.entry.quantity_unit ?? ''}
                        </span>
                      ) : null}
                    </div>
                    <span className={`state ${statusClass}`}>{statusText}</span>
                  </li>
                )
              })}
            </ul>
          )}

          <div className="card__actions">
            <a href={`#/check-in?date=${today}`} className="button button--primary button--small">
              Перейти в Итоги дня →
            </a>
          </div>
        </section>

        {/* Card 2: Эта неделя */}
        <section className="dashboard-card" aria-label="Эта неделя">
          <header className="dashboard-card__header">
            <h2 className="dashboard-card__title">Эта неделя</h2>
            <span className="badge">
              {formatShortDateLabel(week_progress.week_start)} — {formatShortDateLabel(week_progress.week_end)}
            </span>
          </header>

          <div className="dashboard-card__score">
            <span className="dashboard-card__score-value">
              {week_progress.score === null
                ? '—'
                : `${week_progress.score.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`}
            </span>
            <span className="dashboard-card__score-sub">
              {week_progress.score === null
                ? 'Нет обязательных привычек'
                : `Важность: ${week_progress.completed_weight} / ${week_progress.required_weight}`}
            </span>
          </div>

          <h3 className="card__title">Прогресс недельных привычек</h3>
          {week_progress.habits.length === 0 ? (
            <p className="loading">Нет недельных привычек.</p>
          ) : (
            <ul className="dashboard-habits-list">
              {week_progress.habits.map((habit) => {
                const prefDaysText = formatPreferredWeekdays(habit.preferred_weekdays)
                return (
                  <li key={habit.habit_id} className="dashboard-habit-item">
                    <div className="dashboard-habit-item__main">
                      <span className="dashboard-habit-item__name">{habit.name}</span>
                      <span className="dashboard-habit-item__meta">
                        Квота: {habit.completed_count} / {habit.quota}
                        {prefDaysText ? ` · Предпочтительно: ${prefDaysText}` : ''}
                      </span>
                    </div>
                    <span className={`status-badge status-badge--${habit.status}`}>
                      {WEEK_STATUS_LABELS[habit.status] ?? habit.status}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        {/* Card 3: Текущие серии */}
        <section className="dashboard-card" aria-label="Текущие серии">
          <header className="dashboard-card__header">
            <h2 className="dashboard-card__title">Текущие серии</h2>
          </header>

          {streaks.length === 0 ? (
            <p className="loading">Нет активных привычек с сериями.</p>
          ) : (
            <ul className="dashboard-habits-list">
              {streaks.map((s) => {
                const habitName =
                  today_items.find((i) => i.habit_id === s.habit_id)?.name ??
                  week_progress.habits.find((h) => h.habit_id === s.habit_id)?.name ??
                  `Привычка #${s.habit_id}`
                return (
                  <li key={s.habit_id} className="dashboard-streak-item">
                    <span>{habitName}</span>
                    <span className="dashboard-streak-item__value">
                      {formatStreakText(s.current_streak, s.unit)}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        {/* Card 4: Вчерашнее состояние */}
        <section className="dashboard-card" aria-label="Вчерашнее состояние">
          <header className="dashboard-card__header">
            <h2 className="dashboard-card__title">Вчера</h2>
          </header>

          {yesterday_state === null ? (
            <div className="empty">Состояние вчера не заполнено</div>
          ) : (
            <div className="state-summary-grid">
              {yesterday_state.mood !== null && yesterday_state.mood !== undefined ? (
                <div className="state-summary-item">
                  <span className="state-summary-item__label">Настроение</span>
                  <span className="state-summary-item__value">{yesterday_state.mood} / 5</span>
                </div>
              ) : null}

              {yesterday_state.energy !== null && yesterday_state.energy !== undefined ? (
                <div className="state-summary-item">
                  <span className="state-summary-item__label">Энергия</span>
                  <span className="state-summary-item__value">{yesterday_state.energy} / 5</span>
                </div>
              ) : null}

              {yesterday_state.wellbeing !== null && yesterday_state.wellbeing !== undefined ? (
                <div className="state-summary-item">
                  <span className="state-summary-item__label">Самочувствие</span>
                  <span className="state-summary-item__value">{yesterday_state.wellbeing} / 5</span>
                </div>
              ) : null}

              {(yesterday_state.sleep_status || yesterday_state.sleep_minutes !== null) ? (
                <div className="state-summary-item">
                  <span className="state-summary-item__label">Сон</span>
                  <span className="state-summary-item__value">
                    {formatSleepStatus(yesterday_state.sleep_status)}
                    {yesterday_state.sleep_minutes !== null
                      ? ` · ${formatMinutes(yesterday_state.sleep_minutes)}`
                      : ''}
                  </span>
                </div>
              ) : null}

              {yesterday_state.alcohol !== null && yesterday_state.alcohol !== undefined ? (
                <div className="state-summary-item">
                  <span className="state-summary-item__label">Алкоголь</span>
                  <span className="state-summary-item__value">
                    {yesterday_state.alcohol
                      ? `Да${yesterday_state.alcohol_detail ? ` · ${yesterday_state.alcohol_detail}` : ''}`
                      : 'Нет'}
                  </span>
                </div>
              ) : null}

              {yesterday_state.gaming !== null && yesterday_state.gaming !== undefined ? (
                <div className="state-summary-item">
                  <span className="state-summary-item__label">Игры</span>
                  <span className="state-summary-item__value">
                    {yesterday_state.gaming
                      ? formatMinutes(yesterday_state.gaming_minutes)
                      : 'Нет'}
                  </span>
                </div>
              ) : null}

              {yesterday_state.computer_overuse !== null && yesterday_state.computer_overuse !== undefined ? (
                <div className="state-summary-item">
                  <span className="state-summary-item__label">Компьютер</span>
                  <span className="state-summary-item__value">
                    {yesterday_state.computer_overuse
                      ? `Слишком много${yesterday_state.computer_minutes !== null ? ` · ${formatMinutes(yesterday_state.computer_minutes)}` : ''}`
                      : 'Нормально'}
                  </span>
                </div>
              ) : null}

              {yesterday_state.note ? (
                <div className="state-summary-item" style={{ gridColumn: '1 / -1' }}>
                  <span className="state-summary-item__label">Заметка</span>
                  <span className="state-summary-item__value">{yesterday_state.note}</span>
                </div>
              ) : null}
            </div>
          )}
        </section>
      </div>
    </section>
  )
}

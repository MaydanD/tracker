import { useEffect } from 'react'

import { fetchDashboard } from '../api/dashboard'
import { BackupReminder } from '../components/BackupReminder'
import { ErrorBanner, LoadingText } from '../components/Feedback'
import { DashboardAreaTrends } from '../components/dashboard/DashboardAreaTrends'
import { OwlAssistantBanner } from '../components/owl/OwlAssistantBanner'
import { resolveOwlAsset } from '../components/owl/owlAssets'
import { setOwl } from '../components/owl/owlStore'
import { useAsyncData } from '../hooks/useAsyncData'
import { formatShortDateLabel } from '../utils/dateUtils'
import { formatStreakText } from '../utils/formatters'

export function DashboardPage() {
  const { data, error, loading, reload } = useAsyncData((signal) => fetchDashboard(signal), [])

  useEffect(() => {
    if (data) setOwl(data.owl)
  }, [data?.owl?.fingerprint])

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

  const { today, today_progress, week_progress, streaks, today_items, owl } = data
  const needsCheckIn = today_progress.obligations.some((obligation) => obligation.entry_status === null)
  const weekPercent = week_progress.score
  const weekProgressText = weekPercent === null
    ? 'Нет запланированных привычек'
    : `${week_progress.completed_weight} / ${week_progress.required_weight} по весу`

  return (
    <section className="page dashboard-page">
      <figure className="dashboard-character">
        <img
          className="dashboard-character__image"
          src={resolveOwlAsset(owl?.asset_key ?? 'owl_insight')}
          alt="Сова-помощник"
        />
      </figure>

      {owl ? (
        <OwlAssistantBanner
          state={owl}
          variant="dashboard"
          action={needsCheckIn ? (
            <a href={`#/check-in?date=${today}`} className="button button--primary dashboard-message__action">
              Заполнить
            </a>
          ) : null}
        />
      ) : (
        <section className="dashboard-message dashboard-message--quiet" aria-label="Сова-помощник">
          <p className="dashboard-message__lead">Пока без особых новостей.</p>
          <p className="dashboard-message__fact">Отметьте сегодняшний день, чтобы следить за своим прогрессом.</p>
          {needsCheckIn ? (
            <a href={`#/check-in?date=${today}`} className="button button--primary dashboard-message__action">
              Заполнить
            </a>
          ) : null}
        </section>
      )}

      <DashboardAreaTrends today={today} />

      <section className="dashboard-week" aria-label="Прогресс недели">
        <div className="dashboard-week__summary">
          <div>
            <h2 className="dashboard-section-title">Эта неделя</h2>
            <p className="dashboard-week__dates">
              {formatShortDateLabel(week_progress.week_start)} — {formatShortDateLabel(week_progress.week_end)}
            </p>
          </div>
          <div className="dashboard-week__score">
            <strong>{weekPercent === null
              ? '—'
              : `${weekPercent.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`}</strong>
            <span>{weekProgressText}</span>
          </div>
        </div>
        <div
          className="dashboard-week__bar"
          role="progressbar"
          aria-label="Недельный прогресс"
          aria-valuemin={weekPercent === null ? undefined : 0}
          aria-valuemax={weekPercent === null ? undefined : 100}
          aria-valuenow={weekPercent ?? undefined}
          aria-valuetext={weekPercent === null ? 'Нет запланированных привычек' : undefined}
        >
          <span style={{ width: `${Math.max(0, Math.min(weekPercent ?? 0, 100))}%` }} />
        </div>
      </section>

      <section className="dashboard-streaks" aria-label="Текущие серии">
        <h2 className="dashboard-section-title">Серии привычек</h2>
        {streaks.length === 0 ? (
          <p className="dashboard-streaks__empty">Пока нет активных серий.</p>
        ) : (
          <ul className="dashboard-streaks__list">
            {streaks.map((streak) => {
              const habitName =
                today_items.find((item) => item.habit_id === streak.habit_id)?.name ??
                week_progress.habits.find((habit) => habit.habit_id === streak.habit_id)?.name ??
                `Привычка #${streak.habit_id}`
              return (
                <li key={streak.habit_id} className="dashboard-streak">
                  <span className="dashboard-streak__name">{habitName}</span>
                  <span className="dashboard-streak__value">{formatStreakText(streak.current_streak, streak.unit)}</span>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <div className="dashboard-backup-reminder">
        <BackupReminder today={today} />
      </div>
    </section>
  )
}

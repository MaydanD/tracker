import type { RecordsPreview } from '../../api/records'
import { formatShortDateLabel } from '../../utils/dateUtils'
import { streakValue } from './recordsLabels'

export interface RecordsPreviewCardProps {
  records: RecordsPreview | null
}

/**
 * The dashboard's compact records block: at most one headline record and the
 * latest achievement. All detail lives on the records page.
 */
export function RecordsPreviewCard({ records }: RecordsPreviewCardProps) {
  if (records === null) return null

  const streak = records.longest_streak
  const latest = records.latest_achievement

  return (
    <section className="dashboard-card" aria-label="Рекорды">
      <header className="dashboard-card__header">
        <h2 className="dashboard-card__title">Рекорды</h2>
        <span className="badge">{`${records.achieved_count} из ${records.total_count}`}</span>
      </header>

      {streak === null && latest === null ? (
        <p className="loading">Рекордов пока нет.</p>
      ) : null}

      {streak !== null ? (
        <p className="records-preview__line">
          <span className="records-preview__label">Лучшая серия</span>
          <span className="records-preview__value">
            {`${streak.name} — ${streakValue(streak.best_streak, streak.unit)}`}
          </span>
        </p>
      ) : null}

      {latest !== null ? (
        <p className="records-preview__line">
          <span className="records-preview__label">Последнее достижение</span>
          <span className="records-preview__value">
            {latest.title}
            {latest.achieved_on !== null ? ` · ${formatShortDateLabel(latest.achieved_on)}` : ''}
          </span>
        </p>
      ) : null}

      <div className="card__actions">
        {/* Hash anchor, matching the dashboard's other cross-links. */}
        <a className="button button--small" href="#/records">Все рекорды →</a>
      </div>
    </section>
  )
}

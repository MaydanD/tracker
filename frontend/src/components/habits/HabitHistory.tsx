import { fetchHabitVersions } from '../../api/habits'
import { useAsyncData } from '../../hooks/useAsyncData'
import { ErrorBanner, LoadingText } from '../Feedback'
import { configurationDateLabel, scheduleLabel, trackingModeLabel, weightLabel } from './options'

export interface HabitHistoryProps {
  habitId: number
}

/**
 * История настроек for one habit.
 *
 * Shows that a change is recorded rather than applied retroactively: each entry
 * is a configuration that was effective from a calendar date onwards.
 */
export function HabitHistory({ habitId }: HabitHistoryProps) {
  const { data, error, loading } = useAsyncData(
    (signal) => fetchHabitVersions(habitId, signal),
    [habitId],
  )

  if (loading) return <LoadingText>Загрузка истории…</LoadingText>
  if (error !== null) return <ErrorBanner message={error} />
  if (data === null || data.length === 0) {
    return <p className="empty">История настроек пока пуста.</p>
  }

  return (
    <ol className="versions">
      {data.map((version) => (
        <li key={version.version_number} className="versions__item">
          <span className="versions__heading">
            Версия {version.version_number}
            <span className="versions__date">Действует с {configurationDateLabel(version.effective_from)}</span>
          </span>
          <span className="versions__detail">
            {version.name} · {version.area.name} · важность {version.weight} (
            {weightLabel(version.weight)}) ·{' '}
            {trackingModeLabel(version.tracking_mode, version.quantity_unit)} ·{' '}
            {scheduleLabel(version.schedule)}
          </span>
          {version.description ? (
            <span className="versions__note">{version.description}</span>
          ) : null}
        </li>
      ))}
    </ol>
  )
}

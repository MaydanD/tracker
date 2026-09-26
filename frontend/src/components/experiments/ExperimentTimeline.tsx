import { parseIsoDate } from '../daily/dates'
import type { ExperimentWindows, ExperimentStage } from '../../api/experiments'
import { STAGE_LABELS } from './labels'

export interface ExperimentTimelineProps {
  windows: ExperimentWindows
  /** Today's ISO date, used only to place the "you are here" marker. */
  today: string
}

const DAY_MS = 86_400_000

function daysBetween(start: string, end: string): number {
  const first = parseIsoDate(start).getTime()
  const last = parseIsoDate(end).getTime()
  return Math.max(0, Math.round((last - first) / DAY_MS) + 1)
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/**
 * A proportional before / during / after bar with the current day marked.
 *
 * Deliberately plain CSS: it is a three-segment ruler, not a chart, and does not
 * justify a charting dependency. Segment width equals its real day count, so an
 * empty (cancelled-before-start) experiment collapses instead of pretending.
 */
export function ExperimentTimeline({ windows, today }: ExperimentTimelineProps) {
  const order: ExperimentStage[] = ['before', 'during', 'after']
  const lengths = order.map((key) => daysBetween(windows[key].start, windows[key].end))
  const total = lengths.reduce((sum, value) => sum + value, 0)

  const markerStage = order.find(
    (key) => windows[key].start <= today && today <= windows[key].end,
  )
  let markerPercent: number | null = null
  if (markerStage !== undefined && total > 0) {
    // Offset of today inside its own segment, then across the whole ruler.
    const index = order.indexOf(markerStage)
    const beforeLength = lengths.slice(0, index).reduce((sum, value) => sum + value, 0)
    const window = windows[markerStage]
    const dayInSegment = Math.max(1, daysBetween(window.start, today))
    const absolute = beforeLength + dayInSegment - 1
    markerPercent = clamp((absolute / total) * 100, 0, 100)
  }

  return (
    <div className="experiment-timeline" data-testid="experiment-timeline">
      <div className="experiment-timeline__bar" role="img" aria-label="Периоды эксперимента: до, во время, после">
        {order.map((key, index) => (
          <div
            key={key}
            className={`experiment-timeline__segment experiment-timeline__segment--${key}`}
            style={{ flexGrow: Math.max(1, lengths[index] ?? 0) }}
            data-days={lengths[index] ?? 0}
          >
            <span className="experiment-timeline__name">{STAGE_LABELS[key]}</span>
            <span className="experiment-timeline__days">
              {windowLengthText(lengths[index] ?? 0)}
            </span>
          </div>
        ))}
        {markerPercent !== null ? (
          <span
            className="experiment-timeline__marker"
            style={{ left: `${markerPercent}%` }}
            title={`Сегодня: ${today}`}
            aria-hidden="true"
          />
        ) : null}
      </div>
      <p className="experiment-timeline__legend">
        Метка показывает текущий день. Ширина отрезка соответствует числу дней.
      </p>
    </div>
  )
}

function windowLengthText(days: number): string {
  if (days <= 0) return 'нет дней'
  return `${days} дн.`
}

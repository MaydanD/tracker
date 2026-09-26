import type { SeriesPoint } from '../../api/experiments'
import { formatDate, STAGE_LABELS } from './labels'

export interface ExperimentChartProps {
  series: SeriesPoint[]
}

/**
 * Daily progress across the three windows.
 *
 * Unobserved days are drawn as gaps, never as a zero-height bar: a missing day
 * is missing, not a failed one. The experiment boundaries are marked so the
 * period is visible without reading the dates.
 */
export function ExperimentChart({ series }: ExperimentChartProps) {
  if (series.length === 0) {
    return (
      <p className="empty">В этом диапазоне нет ни одного дня с историей — строить график не из чего.</p>
    )
  }

  const boundaries: { index: number; label: string }[] = []
  series.forEach((point, index) => {
    if (index === 0) return
    if (point.phase !== series[index - 1]?.phase) {
      boundaries.push({ index, label: STAGE_LABELS[point.phase] })
    }
  })

  return (
    <figure className="experiment-chart">
      <div className="experiment-chart__plot" role="img" aria-label="Дневной прогресс по периодам эксперимента">
        {series.map((point) => (
          <div
            key={point.date}
            className={`experiment-chart__day experiment-chart__day--${point.phase}`}
            data-date={point.date}
            data-phase={point.phase}
            data-observed={point.score !== null}
            title={point.score === null
              ? `${formatDate(point.date)}: нет отметки`
              : `${formatDate(point.date)}: ${Math.round(point.score)}%`}
          >
            {point.score === null ? (
              <span className="experiment-chart__gap" aria-hidden="true" />
            ) : (
              <span
                className="experiment-chart__bar"
                style={{ height: `${Math.max(2, Math.min(100, point.score))}%` }}
                aria-hidden="true"
              />
            )}
          </div>
        ))}
        {boundaries.map((boundary) => (
          <span
            key={boundary.index}
            className="experiment-chart__boundary"
            style={{ left: `${(boundary.index / series.length) * 100}%` }}
            aria-hidden="true"
          />
        ))}
      </div>
      <figcaption className="experiment-chart__caption">
        Столбик — дневной прогресс; пунктир — день без отметки; линии — границы эксперимента.
      </figcaption>
    </figure>
  )
}

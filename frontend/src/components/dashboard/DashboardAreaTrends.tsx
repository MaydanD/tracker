import { ErrorBanner, LoadingText } from '../Feedback'
import { fetchCalendarRange, type CalendarDaySummaryRead } from '../../api/calendar'
import { useAsyncData } from '../../hooks/useAsyncData'
import { formatShortDateLabel } from '../../utils/dateUtils'

const CHART_WIDTH = 1000
const CHART_HEIGHT = 300
const PADDING = { top: 20, right: 18, bottom: 34, left: 42 }

interface Area {
  id: number
  name: string
  color: string
}

function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function areaPath(days: CalendarDaySummaryRead[], areaId: number): string {
  const width = CHART_WIDTH - PADDING.left - PADDING.right
  const height = CHART_HEIGHT - PADDING.top - PADDING.bottom
  let path = ''
  let previousIndex = -2

  days.forEach((day, index) => {
    const score = day.area_scores.find((area) => area.area_id === areaId)?.score
    if (score === undefined) {
      previousIndex = -2
      return
    }
    const x = PADDING.left + (index / Math.max(days.length - 1, 1)) * width
    const y = PADDING.top + ((100 - score) / 100) * height
    path += `${index === previousIndex + 1 ? 'L' : 'M'} ${x.toFixed(1)} ${y.toFixed(1)} `
    previousIndex = index
  })

  return path.trim()
}

function collectAreas(days: CalendarDaySummaryRead[]): Area[] {
  const areas = new Map<number, Area>()
  for (const day of days) {
    for (const score of day.area_scores) {
      areas.set(score.area_id, { id: score.area_id, name: score.name, color: score.color })
    }
  }
  return [...areas.values()].sort((left, right) => left.id - right.id)
}

export function DashboardAreaTrends({ today }: { today: string }) {
  const endDate = new Date(`${today}T00:00:00`)
  const startDate = new Date(endDate)
  startDate.setDate(startDate.getDate() - 29)
  const start = isoDate(startDate)
  const { data, error, loading } = useAsyncData(
    (signal) => fetchCalendarRange(start, today, signal, true),
    [start, today],
  )
  const areas = collectAreas(data ?? [])
  const tickIndexes = data && data.length > 0
    ? [...new Set([0, Math.floor((data.length - 1) / 2), data.length - 1])]
    : []
  const dateTicks = data
    ? tickIndexes.flatMap((index) => data[index] ? [{ day: data[index], index }] : [])
    : []

  return (
    <section className="dashboard-trends" aria-label="Динамика по сферам">
      <header className="dashboard-trends__header">
        <h2 className="dashboard-section-title">Динамика по сферам</h2>
        <span className="dashboard-trends__period">
          {formatShortDateLabel(start)} — {formatShortDateLabel(today)}
        </span>
      </header>
      <ErrorBanner message={error} />
      {loading && data === null ? <LoadingText>Загрузка динамики…</LoadingText> : null}
      {data !== null && areas.length > 0 ? (
        <>
          <div className="dashboard-trends__chart">
            <svg
              viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
              role="img"
              aria-label="Оценка выполнения привычек по сферам за последние 30 дней"
              className="dashboard-trends__svg"
            >
              {[0, 25, 50, 75, 100].map((value) => {
                const y = PADDING.top + ((100 - value) / 100) * (CHART_HEIGHT - PADDING.top - PADDING.bottom)
                return (
                  <g key={value}>
                    <line
                      x1={PADDING.left}
                      y1={y}
                      x2={CHART_WIDTH - PADDING.right}
                      y2={y}
                      className="dashboard-trends__gridline"
                    />
                    <text x={PADDING.left - 10} y={y + 4} textAnchor="end" className="dashboard-trends__axis-label">
                      {value}%
                    </text>
                  </g>
                )
              })}
              {areas.map((area) => (
                <path
                  key={area.id}
                  d={areaPath(data, area.id)}
                  fill="none"
                  stroke={area.color}
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  data-area-id={area.id}
                >
                  <title>{area.name}</title>
                </path>
              ))}
              {dateTicks.map(({ day, index }) => {
                const x = PADDING.left +
                  (index / Math.max(data.length - 1, 1)) * (CHART_WIDTH - PADDING.left - PADDING.right)
                return (
                  <text
                    key={day.entry_date}
                    x={x}
                    y={CHART_HEIGHT - 8}
                    textAnchor={index === 0 ? 'start' : index === data.length - 1 ? 'end' : 'middle'}
                    className="dashboard-trends__axis-label"
                  >
                    {formatShortDateLabel(day.entry_date)}
                  </text>
                )
              })}
            </svg>
          </div>
          <ul className="dashboard-trends__legend">
            {areas.map((area) => (
              <li key={area.id}>
                <span className="dashboard-trends__swatch" style={{ backgroundColor: area.color }} />
                {area.name}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {data !== null && areas.length === 0 ? (
        <p className="dashboard-trends__empty">Пока нет данных по сферам для графика.</p>
      ) : null}
    </section>
  )
}

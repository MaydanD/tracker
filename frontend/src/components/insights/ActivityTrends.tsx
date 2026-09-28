import { ErrorBanner, LoadingText } from '../Feedback'
import { fetchCalendarRange } from '../../api/calendar'
import { useAsyncData } from '../../hooks/useAsyncData'
import { formatAxisDateLabel, formatShortDateLabel, spansDifferentYears, tickIndexes } from '../../utils/dateUtils'
import { formatNumber } from './labels'
import { ChartFigure } from './charts'

const WIDTH = 640
const HEIGHT = 180
const PAD_LEFT = 38
const PAD_RIGHT = 10
/** Room above the plot for the unit caption, which sits clear of the top tick. */
const PAD_TOP = 22
const PAD_BOTTOM = 26
const PLOT_WIDTH = WIDTH - PAD_LEFT - PAD_RIGHT
const PLOT_HEIGHT = HEIGHT - PAD_TOP - PAD_BOTTOM
/** Five dates along 640px stay legible; a 90-day range gets start, quarters, end. */
const MAX_DATE_TICKS = 5

function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

interface TrendPoint {
  date: string
  value: number | null
}

function chartPath(points: TrendPoint[], min: number, max: number) {
  const available = points
    .map((point, index) => ({ point, index, value: point.value }))
    .filter((item): item is { point: TrendPoint; index: number; value: number } =>
      item.value !== null,
    )
  const x = (index: number) => PAD_LEFT + (index / Math.max(points.length - 1, 1)) * PLOT_WIDTH
  const y = (value: number) =>
    HEIGHT - PAD_BOTTOM - ((value - min) / (max - min)) * PLOT_HEIGHT

  let path = ''
  let previousIndex = -2
  for (const item of available) {
    // A day without a value breaks the line; it is never drawn as zero.
    path += `${item.index === previousIndex + 1 ? 'L' : 'M'} ${x(item.index).toFixed(1)} ${y(item.value).toFixed(1)} `
    previousIndex = item.index
  }
  return { path, available, x, y }
}

/**
 * One measured quantity over time: the value axis, the dates of the range and
 * a tooltip per observation. The line only covers days that actually have a
 * value — a gap in the data stays a gap in the chart.
 */
function TrendChart({
  title,
  summary,
  points,
  min,
  max,
  color,
  valueUnit = '%',
  unitCaption,
}: {
  title: string
  summary: string
  points: TrendPoint[]
  min: number
  max: number
  color?: string
  valueUnit?: string
  unitCaption?: string
}) {
  const chart = chartPath(points, min, max)
  const observed = chart.available.length
  const first = points[0]?.date
  const last = points.at(-1)?.date
  const period = first && last ? `${formatShortDateLabel(first)} — ${formatShortDateLabel(last)}` : ''
  const withYear = first !== undefined && last !== undefined && spansDifferentYears(first, last)

  return (
    <ChartFigure
      title={title}
      summary={summary}
      period={period}
      empty={observed === 0}
      label={`${title}. Период ${period}. ${summary}`}
    >
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="insight-chart__svg" aria-hidden="true" focusable="false">
        {[max, (max + min) / 2, min].map((value, index) => {
          const y = PAD_TOP + (index / 2) * PLOT_HEIGHT
          return (
            <g key={`${value}-${index}`}>
              <line x1={PAD_LEFT} y1={y} x2={WIDTH - PAD_RIGHT} y2={y} className="insight-chart__gridline" />
              <text x={PAD_LEFT - 5} y={y + 3} textAnchor="end" className="insight-chart__tick">
                {valueUnit === '%' ? `${formatNumber(value, 0)}%` : formatNumber(value, 0)}
              </text>
            </g>
          )
        })}
        {unitCaption ? (
          <text x={PAD_LEFT - 5} y={PAD_TOP - 9} textAnchor="end" className="insight-chart__tick">
            {unitCaption}
          </text>
        ) : null}
        <line x1={PAD_LEFT} y1={HEIGHT - PAD_BOTTOM} x2={WIDTH - PAD_RIGHT} y2={HEIGHT - PAD_BOTTOM} className="insight-chart__axis" />
        <path d={chart.path} className="insight-chart__line" style={color ? { stroke: color } : undefined} />
        {chart.available.map(({ point, index, value }) => (
          <circle key={point.date} className="insight-chart__dot"
            style={color ? { fill: color } : undefined}
            cx={chart.x(index)} cy={chart.y(value)} r={2}>
            <title>{`${formatShortDateLabel(point.date)}: ${formatNumber(value, 1)} ${valueUnit}`}</title>
          </circle>
        ))}
        {tickIndexes(points.length, MAX_DATE_TICKS).flatMap((index) => {
          const point = points[index]
          if (!point) return []
          const anchor = index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'
          return (
            <text key={point.date} x={chart.x(index)} y={HEIGHT - 8} textAnchor={anchor}
              className="insight-chart__tick">
              {formatAxisDateLabel(point.date, withYear)}
            </text>
          )
        })}
      </svg>
    </ChartFigure>
  )
}

export function ActivityTrends({ today: pinnedToday }: { today?: string }) {
  const end = pinnedToday ?? isoDate(new Date())
  const firstDay = new Date(`${end}T00:00:00`)
  firstDay.setDate(firstDay.getDate() - 89)
  const start = isoDate(firstDay)
  const { data, error, loading } = useAsyncData(
    (signal) => fetchCalendarRange(start, end, signal, true),
    [start, end],
  )
  const areas = new Map<number, { name: string; color: string }>()
  const habits = new Map<number, { name: string; areaName: string; color: string }>()
  for (const day of data ?? []) {
    for (const area of day.area_scores ?? []) areas.set(area.area_id, { name: area.name, color: area.color })
    for (const habit of day.habit_scores ?? []) {
      habits.set(habit.habit_id, { name: habit.name, areaName: habit.area_name, color: habit.color })
    }
  }
  const days = data ?? []
  const period = days.length > 0
    ? `Период: ${formatShortDateLabel(days[0]!.entry_date)} — ${formatShortDateLabel(days.at(-1)!.entry_date)}`
    : null

  return (
    <section className="analytics-trends" aria-label="Графики активности">
      <header className="page__header">
        <h2 className="page__title">Графики за последние 90 дней</h2>
        {period ? <span className="analytics-trends__period">{period}</span> : null}
      </header>
      <ErrorBanner message={error} />
      {loading && data === null ? <LoadingText>Загрузка графиков…</LoadingText> : null}
      {data !== null ? (
        <div className="analytics-trend-groups">
          <div className="insight-charts">
            <TrendChart
              title="Выполнение привычек"
              summary="Доля выполненной важности среди обязательных привычек за день."
              points={data.map((point) => ({ date: point.entry_date, value: point.daily_score }))}
              min={0}
              max={100}
            />
            <TrendChart
              title="Настроение"
              summary="Оценка настроения по дням, когда заполнено состояние дня."
              points={data.map((point) => ({ date: point.entry_date, value: point.mood }))}
              min={1}
              max={5}
              valueUnit="из 5"
              unitCaption="из 5"
            />
          </div>
          {areas.size > 0 ? (
            <section className="analytics-trend-group" aria-label="Графики по сферам">
              <h3 className="analytics-trend-group__title">По сферам</h3>
              <div className="insight-charts">
                {[...areas].map(([areaId, area]) => (
                  <TrendChart
                    key={`area-${areaId}`}
                    title={`Сфера: ${area.name}`}
                    summary="«Выполнено» от отметок «Выполнено» и «Пропущено»; плановые пропуски и пустые дни исключены."
                    points={data.map((day) => ({
                      date: day.entry_date,
                      value: day.area_scores?.find((score) => score.area_id === areaId)?.score ?? null,
                    }))}
                    min={0}
                    max={100}
                    color={area.color}
                  />
                ))}
              </div>
            </section>
          ) : null}
          {habits.size > 0 ? (
            <section className="analytics-trend-group" aria-label="Графики по привычкам">
              <h3 className="analytics-trend-group__title">По привычкам</h3>
              <div className="insight-charts">
                {[...habits].map(([habitId, habit]) => (
                  <TrendChart
                    key={`habit-${habitId}`}
                    title={`Привычка: ${habit.name}`}
                    summary={`${habit.areaName}: выполнено — 100%, пропущено — 0%; плановые пропуски и пустые дни исключены.`}
                    points={data.map((day) => ({
                      date: day.entry_date,
                      value: day.habit_scores?.find((score) => score.habit_id === habitId)?.score ?? null,
                    }))}
                    min={0}
                    max={100}
                    color={habit.color}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

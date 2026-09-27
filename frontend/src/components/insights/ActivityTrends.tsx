import { ErrorBanner, LoadingText } from '../Feedback'
import { fetchCalendarRange } from '../../api/calendar'
import { useAsyncData } from '../../hooks/useAsyncData'
import { ChartFigure } from './charts'

const WIDTH = 640
const HEIGHT = 150
const PAD_X = 8
const PAD_Y = 12

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
  const x = (index: number) => PAD_X + (index / Math.max(points.length - 1, 1)) * (WIDTH - PAD_X * 2)
  const y = (value: number) =>
    HEIGHT - PAD_Y - ((value - min) / (max - min)) * (HEIGHT - PAD_Y * 2)

  let path = ''
  let previousIndex = -2
  for (const item of available) {
    path += `${item.index === previousIndex + 1 ? 'L' : 'M'} ${x(item.index).toFixed(1)} ${y(item.value).toFixed(1)} `
    previousIndex = item.index
  }
  return { path, available, x, y }
}

function TrendChart({
  title,
  summary,
  points,
  min,
  max,
  color,
  valueUnit = '%',
}: {
  title: string
  summary: string
  points: TrendPoint[]
  min: number
  max: number
  color?: string
  valueUnit?: string
}) {
  const chart = chartPath(points, min, max)
  return (
    <ChartFigure title={title} summary={summary} label={`${title}. ${summary}`}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="insight-chart__svg" aria-hidden="true" focusable="false">
        <line x1={PAD_X} y1={HEIGHT - PAD_Y} x2={WIDTH - PAD_X} y2={HEIGHT - PAD_Y} className="insight-chart__axis" />
        <path d={chart.path} className="insight-chart__line" style={color ? { stroke: color } : undefined} />
        {chart.available.map(({ point, index, value }) => (
          <circle key={point.date} className="insight-chart__dot"
            style={color ? { fill: color } : undefined}
            cx={chart.x(index)} cy={chart.y(value)} r={2}>
            <title>{`${point.date}: ${Math.round(value)} ${valueUnit}`}</title>
          </circle>
        ))}
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
    for (const area of day.area_scores) areas.set(area.area_id, { name: area.name, color: area.color })
    for (const habit of day.habit_scores) {
      habits.set(habit.habit_id, { name: habit.name, areaName: habit.area_name, color: habit.color })
    }
  }

  return (
    <section className="analytics-trends" aria-label="Графики активности">
      <header className="page__header">
        <h2 className="page__title">Графики за последние 90 дней</h2>
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
                      value: day.area_scores.find((score) => score.area_id === areaId)?.score ?? null,
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
                      value: day.habit_scores.find((score) => score.habit_id === habitId)?.score ?? null,
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

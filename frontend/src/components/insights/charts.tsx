/**
 * Stage 8 charts: plain SVG, no charting dependency.
 *
 * The frontend draws what the backend computed. Scaling a value to a pixel is
 * presentation; nothing here recomputes a coefficient, a rolling mean, a
 * coverage number or a confidence level. Gaps (`missing`) are never drawn as
 * zero, and colour is never the only channel: every chart also carries text.
 */

import type { ReactNode } from 'react'

import type {
  InsightAlternativeRead,
  InsightChartPointRead,
  InsightGroupRead,
  InsightSeriesRead,
} from '../../api/insights'
import {
  RELATION_TO_FULL_LABELS,
  SEGMENT_LABELS,
  VERDICT_LABELS,
  formatCoefficient,
  formatCount,
  formatNumber,
} from './labels'

const WIDTH = 320
const HEIGHT = 120
const PAD_X = 8
const PAD_Y = 14

function dayNumber(iso: string): number {
  return Math.floor(Date.parse(`${iso}T00:00:00Z`) / 86_400_000)
}

function drawable(points: InsightChartPointRead[]): InsightChartPointRead[] {
  return points.filter((point) => !point.missing && point.value !== null)
}

function extent(values: number[]): [number, number] {
  if (values.length === 0) return [0, 1]
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  if (minimum === maximum) return [minimum - 0.5, maximum + 0.5]
  return [minimum, maximum]
}

function xScale(points: InsightChartPointRead[], date: string): number {
  const first = dayNumber(points[0]?.date ?? date)
  const last = dayNumber(points.at(-1)?.date ?? date)
  const span = Math.max(last - first, 1)
  return PAD_X + ((dayNumber(date) - first) / span) * (WIDTH - 2 * PAD_X)
}

function yScale(value: number, minimum: number, maximum: number): number {
  const ratio = (value - minimum) / Math.max(maximum - minimum, Number.EPSILON)
  return HEIGHT - PAD_Y - ratio * (HEIGHT - 2 * PAD_Y)
}

interface FigureProps {
  title: string
  /** Accessible description; the backend's own chart summary is used when present. */
  summary: string
  label: string
  testId?: string
  children: ReactNode
}

export function ChartFigure({ title, summary, label, testId, children }: FigureProps) {
  return (
    <figure className="insight-chart" data-testid={testId}>
      <figcaption className="insight-chart__title">{title}</figcaption>
      <div className="insight-chart__plot" role="img" aria-label={label}>
        {children}
      </div>
      <p className="insight-chart__summary">{summary}</p>
    </figure>
  )
}

/** Numeric/ordinal time series: gaps break the line instead of becoming zero. */
export function SeriesChart({ series, title, summary }: {
  series: InsightSeriesRead
  title: string
  summary: string
}) {
  const points = series.points
  const observed = drawable(points)
  const [minimum, maximum] = extent(observed.map((point) => point.value as number))
  const runs: { date: string; value: number }[][] = []
  for (const point of points) {
    if (point.missing || point.value === null) {
      runs.push([])
      continue
    }
    if (runs.length === 0) runs.push([])
    runs.at(-1)?.push({ date: point.date, value: point.value })
  }
  const rollingPaths = [...new Set(series.rolling.map((item) => item.window))].map((window) => {
    let path = ''
    let penDown = false
    for (const item of series.rolling.filter((point) => point.window === window)) {
      if (item.mean === null) { penDown = false; continue }
      path += `${penDown ? 'L' : 'M'} ${xScale(points, item.date).toFixed(1)} ${yScale(item.mean, minimum, maximum).toFixed(1)} `
      penDown = true
    }
    return { window, path }
  })

  return (
    <ChartFigure title={title} summary={summary} testId={`chart-series-${series.variable.key}`}
      label={`${title}: ${series.variable.label}. ${summary}`}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="insight-chart__svg" aria-hidden="true" focusable="false">
        <line x1={PAD_X} y1={HEIGHT - PAD_Y} x2={WIDTH - PAD_X} y2={HEIGHT - PAD_Y} className="insight-chart__axis" />
        {runs.filter((run) => run.length > 0).map((run, index) => (
          <path key={`${run[0]?.date ?? 'run'}-${index}`} className="insight-chart__line"
            d={run.map((point, position) => `${position === 0 ? 'M' : 'L'} ${xScale(points, point.date).toFixed(1)} ${yScale(point.value, minimum, maximum).toFixed(1)}`).join(' ')} />
        ))}
        {observed.map((point) => (
          <circle key={point.date} className={point.incomplete ? 'insight-chart__dot insight-chart__dot--incomplete' : 'insight-chart__dot'}
            cx={xScale(points, point.date).toFixed(1)} cy={yScale(point.value as number, minimum, maximum).toFixed(1)} r={1.6}>
            <title>{`${point.date}: ${formatNumber(point.value as number)}${point.incomplete ? ' (неполный период)' : ''}`}</title>
          </circle>
        ))}
        {rollingPaths.filter((item) => item.path).map((item, index) => (
          <path key={item.window} className="insight-chart__rolling" d={item.path} strokeDasharray={index === 0 ? '4 3' : '1 3'}>
            <title>{`Скользящее среднее: ${item.window} ${series.variable.grain === 'weekly' ? 'недель' : 'дней'}`}</title>
          </path>
        ))}
      </svg>
      {rollingPaths.some((item) => item.path) ? <p className="insight-chart__legend">
        {`Пунктир: скользящие средние за ${rollingPaths.filter((item) => item.path).map((item) => item.window).join(' и ')} ${series.variable.grain === 'weekly' ? 'недель' : 'дней'}.`}
      </p> : null}
    </ChartFigure>
  )
}

/** Boolean series as day tokens: filled = «Да», empty = «Нет», dotted = нет записи. */
export function BooleanStrip({ series, title, summary }: {
  series: InsightSeriesRead
  title: string
  summary: string
}) {
  const points = series.points
  const size = Math.min(10, Math.max(2, Math.floor((WIDTH - 2) / Math.max(points.length, 1)) - 1))
  return (
    <ChartFigure title={title} summary={summary} testId={`chart-boolean-${series.variable.key}`}
      label={`${title}: ${series.variable.label}. ${summary}`}>
      <svg viewBox={`0 0 ${Math.max(WIDTH, points.length * (size + 1) + 2)} 30`} className="insight-chart__svg" aria-hidden="true" focusable="false">
        {points.map((point, index) => {
          const className = point.missing || point.value === null
            ? 'insight-chart__token insight-chart__token--missing'
            : point.value === 1
              ? 'insight-chart__token insight-chart__token--yes'
              : 'insight-chart__token insight-chart__token--no'
          const state = point.missing || point.value === null ? 'нет записи' : point.value === 1 ? 'Да' : 'Нет'
          return (
            <rect key={point.date} className={className} x={1 + index * (size + 1)} y={8} width={size} height={14} rx={1}>
              <title>{`${point.date}: ${state}`}</title>
            </rect>
          )
        })}
      </svg>
      <p className="insight-chart__legend">
        <span className="insight-chart__legend-item"><span className="insight-chart__token insight-chart__token--yes" aria-hidden="true" /> Да</span>
        <span className="insight-chart__legend-item"><span className="insight-chart__token insight-chart__token--no" aria-hidden="true" /> Нет</span>
        <span className="insight-chart__legend-item"><span className="insight-chart__token insight-chart__token--missing" aria-hidden="true" /> Нет записи</span>
      </p>
    </ChartFigure>
  )
}

/** Numeric ↔ numeric detail: aligned observations only, no regression line. */
export function ScatterChart({ pairs, xLabel, yLabel, title, summary }: {
  pairs: { x_date: string; y_date: string; x: number; y: number }[]
  xLabel: string
  yLabel: string
  title: string
  summary: string
}) {
  const [xMin, xMax] = extent(pairs.map((pair) => pair.x))
  const [yMin, yMax] = extent(pairs.map((pair) => pair.y))
  return (
    <ChartFigure title={title} summary={summary} testId="chart-scatter"
      label={`${title}: ${xLabel} и ${yLabel}. ${summary}`}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="insight-chart__svg" aria-hidden="true" focusable="false">
        <line x1={PAD_X} y1={HEIGHT - PAD_Y} x2={WIDTH - PAD_X} y2={HEIGHT - PAD_Y} className="insight-chart__axis" />
        <line x1={PAD_X} y1={PAD_Y} x2={PAD_X} y2={HEIGHT - PAD_Y} className="insight-chart__axis" />
        {pairs.map((pair) => {
          const cx = PAD_X + ((pair.x - xMin) / Math.max(xMax - xMin, Number.EPSILON)) * (WIDTH - 2 * PAD_X)
          const cy = yScale(pair.y, yMin, yMax)
          return (
            <circle key={`${pair.x_date}-${pair.y_date}`} className="insight-chart__dot" cx={cx.toFixed(1)} cy={cy.toFixed(1)} r={1.8}>
              <title>{`${xLabel} ${formatNumber(pair.x)} · ${yLabel} ${formatNumber(pair.y)}`}</title>
            </circle>
          )
        })}
        <text x={PAD_X} y={HEIGHT - 2} className="insight-chart__tick">{xLabel}</text>
      </svg>
    </ChartFigure>
  )
}

/** Boolean comparison: two groups, never a misleading continuous scatter. */
export function GroupBars({ group, exposureLabel, title, summary }: {
  group: InsightGroupRead
  exposureLabel: string
  title: string
  summary: string
}) {
  const yes = group.true_mean
  const no = group.false_mean
  const [, maximum] = extent([yes ?? 0, no ?? 0, 1])
  const bars = [
    { name: 'Да', value: yes, count: group.true_count },
    { name: 'Нет', value: no, count: group.false_count },
  ]
  return (
    <ChartFigure title={title} summary={summary} testId="chart-groups"
      label={`${title}: ${exposureLabel}. ${summary}`}>
      <svg viewBox={`0 0 ${WIDTH} 70`} className="insight-chart__svg" aria-hidden="true" focusable="false">
        {bars.map((bar, index) => {
          if (bar.value === null) return <text key={bar.name} x={30 + index * 120} y={40} className="insight-chart__value">{`${bar.name}: нет данных`}</text>
          const height = (bar.value / maximum) * 46
          return (
            <g key={bar.name}>
              <rect className="insight-chart__bar" x={30 + index * 120} y={52 - height} width={70} height={Math.max(height, 0.5)} rx={2}>
                <title>{`«${bar.name}»: среднее ${formatNumber(bar.value)}, наблюдений ${bar.count}`}</title>
              </rect>
              <text x={30 + index * 120 + 35} y={50 - height} textAnchor="middle" className="insight-chart__value">{formatNumber(bar.value)}</text>
              <text x={30 + index * 120 + 35} y={64} textAnchor="middle" className="insight-chart__tick">{`«${bar.name}» · ${formatCount(bar.count)}`}</text>
            </g>
          )
        })}
        <line x1={10} y1={52} x2={WIDTH - 10} y2={52} className="insight-chart__axis" />
      </svg>
    </ChartFigure>
  )
}

/** One relationship family: every lag, with its own verdict, never just one. */
export function LagProfileChart({ alternatives, title, summary }: {
  alternatives: InsightAlternativeRead[]
  title: string
  summary: string
}) {
  const magnitude = Math.max(...alternatives.map((item) => Math.abs(item.coefficient ?? 0)), 0.1)
  const ordered = [...alternatives].sort((first, second) => first.lag - second.lag)
  const slot = (WIDTH - 2 * PAD_X) / Math.max(ordered.length, 1)
  const baseline = HEIGHT / 2
  return (
    <ChartFigure title={title} summary={summary} testId="chart-lag-profile"
      label={`${title}. ${summary}`}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="insight-chart__svg" aria-hidden="true" focusable="false">
        <line x1={PAD_X} y1={baseline} x2={WIDTH - PAD_X} y2={baseline} className="insight-chart__axis" />
        {ordered.map((item, index) => {
          if (item.coefficient === null) return <text key={item.fingerprint} x={PAD_X + index * slot + slot / 2} y={baseline} className="insight-chart__tick">—</text>
          const ratio = Math.abs(item.coefficient ?? 0) / magnitude
          const height = Math.max(ratio * (HEIGHT / 2 - PAD_Y), 1)
          const coefficient = item.coefficient ?? 0
          const x = PAD_X + index * slot + slot / 2
          const y = coefficient >= 0 ? baseline - height : baseline
          const className = `insight-chart__bar insight-chart__bar--${item.guardrail}`
          return (
            <g key={`${item.lag}-${item.fingerprint}`}>
              <rect className={className} x={x - slot / 3} y={y} width={Math.max(slot * 0.66, 3)} height={height} rx={1}>
                <title>{`${item.timing}: ${VERDICT_LABELS[item.guardrail]}, величина ${formatCoefficient(coefficient)}, наблюдений ${item.n}`}</title>
              </rect>
              <text x={x} y={HEIGHT - 2} textAnchor="middle" className="insight-chart__tick">{item.lag}</text>
            </g>
          )
        })}
      </svg>
      <p className="insight-chart__legend">
        <span className="insight-chart__legend-item">Пройдено</span>
        <span className="insight-chart__legend-item">Есть ограничения</span>
        <span className="insight-chart__legend-item">Не прошло / не проверено</span>
      </p>
    </ChartFigure>
  )
}

/** Temporal evidence: the same coefficient on three chronological slices. */
export function SegmentChart({ segments, title, summary }: {
  segments: { index: number; name: string; coefficient: number | null; relation_to_full: string; period: { start: string; end: string } }[]
  title: string
  summary: string
}) {
  const magnitude = Math.max(...segments.map((item) => Math.abs(item.coefficient ?? 0)), 0.1)
  const baseline = 52
  return (
    <ChartFigure title={title} summary={summary} testId="chart-segments"
      label={`${title}. ${summary}`}>
      <svg viewBox={`0 0 ${WIDTH} 120`} className="insight-chart__svg" aria-hidden="true" focusable="false">
        <line x1={10} y1={baseline} x2={WIDTH - 10} y2={baseline} className="insight-chart__axis" />
        {segments.map((segment, index) => {
          if (segment.coefficient === null) return <text key={segment.name} x={20 + index * 100} y={baseline} className="insight-chart__value">нет данных</text>
          const coefficient = segment.coefficient ?? 0
          const height = Math.max((Math.abs(coefficient) / magnitude) * 38, 1)
          const x = 20 + index * 100
          return (
            <g key={segment.name}>
              <rect className={`insight-chart__bar insight-chart__bar--${segment.relation_to_full}`}
                x={x} y={coefficient >= 0 ? baseline - height : baseline} width={56} height={height} rx={2}>
                <title>{`${SEGMENT_LABELS[segment.name] ?? segment.name}: ${formatCoefficient(coefficient)} (${RELATION_TO_FULL_LABELS[segment.relation_to_full] ?? segment.relation_to_full})`}</title>
              </rect>
              <text x={x + 28} y={coefficient >= 0 ? baseline - height - 2 : baseline + height + 8} textAnchor="middle" className="insight-chart__value">{formatCoefficient(coefficient)}</text>
              <text x={x + 28} y={116} textAnchor="middle" className="insight-chart__tick">{SEGMENT_LABELS[segment.name] ?? segment.name}</text>
            </g>
          )
        })}
      </svg>
    </ChartFigure>
  )
}

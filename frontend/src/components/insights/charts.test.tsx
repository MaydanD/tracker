import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { candidate, chartFor, booleanCandidate } from '../../test/insightsFixture'
import { GroupBars, LagProfileChart, SegmentChart, SeriesChart } from './charts'

function missingAll(series: ReturnType<typeof chartFor>['x']) {
  series.points = series.points.map((point) => ({ ...point, value: null, missing: true }))
  series.rolling = []
  return series
}

it('breaks both observed and rolling lines at missing values', () => {
  const series = chartFor(candidate()).x
  series.rolling = series.points.map((point) => ({ date: point.date, mean: point.value, window: 7, status: 'ok' }))
  const { container } = render(<SeriesChart series={series} title="Ряд" summary="Пропуски" />)
  expect(container.querySelectorAll('.insight-chart__line')).toHaveLength(2)
  expect(container.querySelector('.insight-chart__rolling')?.getAttribute('d')?.match(/M/g)).toHaveLength(2)
})

it('does not draw null lag or segment coefficients as zero', () => {
  const item = candidate()
  const { container } = render(<>
    <LagProfileChart alternatives={item.alternatives.map((alt) => ({ ...alt, coefficient: null }))} title="Задержки" summary="Нет оценки" />
    <SegmentChart segments={item.evidence.segments.map((segment) => ({ ...segment, coefficient: null }))} title="Отрезки" summary="Нет оценки" />
  </>)
  expect(container.querySelectorAll('rect')).toHaveLength(0)
  expect(container.textContent).not.toContain('+0,00')
})

it('draws independent backend rolling windows without connecting them to each other', () => {
  const series = chartFor(candidate()).x
  series.rolling = series.points.flatMap((point) => [7, 28].map((window) => ({ date: point.date, mean: point.value, window, status: 'ok' })))
  const { container } = render(<SeriesChart series={series} title="Ряд" summary="Средние" />)
  const paths = container.querySelectorAll('.insight-chart__rolling')
  expect(paths).toHaveLength(2)
  for (const path of paths) expect(path.getAttribute('d')?.match(/M/g)).toHaveLength(2)
  // Every drawn line is named, and the two rolling windows are told apart.
  expect(screen.getByText('Энергия — значение по датам')).toBeInTheDocument()
  expect(screen.getByText('Скользящее среднее за 7 дней')).toBeInTheDocument()
  expect(screen.getByText('Скользящее среднее за 28 дней')).toBeInTheDocument()
})

it('keeps missing group means missing instead of substituting a median or zero', () => {
  const group = booleanCandidate().evidence.effect.group!
  const { container } = render(<GroupBars group={{ ...group, true_mean: null }} exposureLabel="Привычка" title="Группы" summary="Сравнение" />)
  expect(screen.getByText('Да: нет данных')).toBeInTheDocument()
  expect(container.querySelectorAll('rect')).toHaveLength(1)
})

it('states the covered period and puts the dates of the range on the time axis', () => {
  const series = chartFor(candidate()).x
  const { container } = render(<SeriesChart series={series} title="Ряд" summary="Даты" />)
  expect(screen.getByText('01.09.2026 — 06.09.2026')).toBeInTheDocument()
  const ticks = [...container.querySelectorAll('text.insight-chart__tick')].map((node) => node.textContent)
  // The ends of the range are always there; the middle ones are spread out.
  expect(ticks).toContain('01.09')
  expect(ticks).toContain('06.09')
  expect(ticks).not.toContain('02.09')
  // Values carry their own scale, so a level can be read off the chart.
  expect(ticks).toContain('6')
  expect(ticks).toContain('1')
})

it('never draws a missing observation, neither as a dot nor as a zero', () => {
  const series = chartFor(candidate()).x
  const { container } = render(<SeriesChart series={series} title="Ряд" summary="Пропуск" />)
  const missingDate = series.points[2]!.date
  const titles = [...container.querySelectorAll('title')].map((node) => node.textContent ?? '')
  expect(titles.some((title) => title.startsWith('03.09'))).toBe(false)
  expect(container.querySelectorAll('.insight-chart__dot')).toHaveLength(5)
  expect(missingDate).toBe('2026-09-03')
})

it('states the absence of data instead of drawing an empty chart', () => {
  const series = missingAll(chartFor(candidate()).x)
  const { container } = render(<SeriesChart series={series} title="Ряд" summary="Пусто" />)
  expect(screen.getByText('Нет данных за этот период.')).toBeInTheDocument()
  expect(container.querySelectorAll('.insight-chart__line')).toHaveLength(0)
  expect(container.querySelectorAll('.insight-chart__dot')).toHaveLength(0)
  expect(screen.queryByRole('img')).toBeNull()
})

it('explains the lag axis and keys its verdict colours', () => {
  const { container } = render(<LagProfileChart alternatives={candidate().alternatives} title="Задержки" summary="Все задержки" />)
  expect(screen.getByText('По горизонтали — задержка, по вертикали — величина связи.')).toBeInTheDocument()
  for (const verdict of ['pass', 'pass_with_warnings', 'blocked', 'not_evaluable']) {
    expect(container.querySelector(`.insight-chart__swatch--${verdict}`)).not.toBeNull()
  }
})

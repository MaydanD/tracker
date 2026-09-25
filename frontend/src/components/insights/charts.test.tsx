import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { candidate, chartFor, booleanCandidate } from '../../test/insightsFixture'
import { GroupBars, LagProfileChart, SegmentChart, SeriesChart } from './charts'

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
  expect(screen.getByText('Пунктир: скользящие средние за 7 и 28 дней.')).toBeInTheDocument()
})

it('keeps missing group means missing instead of substituting a median or zero', () => {
  const group = booleanCandidate().evidence.effect.group!
  const { container } = render(<GroupBars group={{ ...group, true_mean: null }} exposureLabel="Привычка" title="Группы" summary="Сравнение" />)
  expect(screen.getByText('Да: нет данных')).toBeInTheDocument()
  expect(container.querySelectorAll('rect')).toHaveLength(1)
})

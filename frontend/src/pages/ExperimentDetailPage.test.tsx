import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import {
  analysisFixture,
  createFakeExperiments,
  detailFixture,
  experimentFixture,
  stubExperimentsApi,
} from '../test/experimentsFixture'
import { ExperimentDetailPage } from './ExperimentDetailPage'

function renderDetail(id = 1) {
  return render(
    <MemoryRouter initialEntries={[`/experiments/${id}`]}>
      <Routes>
        <Route path="/experiments/:experimentId" element={<ExperimentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ExperimentDetailPage', () => {
  it('describes before, during and after without causal wording', async () => {
    stubExperimentsApi(
      createFakeExperiments({
        experiments: [experimentFixture({ id: 1 })],
        detail: detailFixture({ experiment: experimentFixture({ id: 1 }) }),
      }),
    )

    renderDetail()

    expect(await screen.findByRole('heading', { name: 'Без алкоголя 14 дней' })).toBeInTheDocument()
    // Windows and their timeline.
    expect(screen.getByTestId('experiment-timeline')).toBeInTheDocument()
    // Overall progress per window.
    expect(screen.getByText('62%')).toBeInTheDocument()
    expect(screen.getByText('76%')).toBeInTheDocument()
    // Habits and state comparisons.
    expect(screen.getByText('Чтение')).toBeInTheDocument()
    expect(screen.getByText('Энергия')).toBeInTheDocument()
    // Coverage per window.
    expect(screen.getByText(/До: 12 из 14 дней данных/)).toBeInTheDocument()
    expect(screen.getByText(/После: 4 из 14 дней данных/)).toBeInTheDocument()
    // Descriptive summary + explicit disclaimer.
    expect(screen.getByText(/средний дневной прогресс был выше/)).toBeInTheDocument()
    expect(screen.getByText(/а не доказательство причинности/)).toBeInTheDocument()

    // No causal claim may appear anywhere on the page.
    const text = document.body.textContent ?? ''
    for (const word of ['вызывает', 'привело', 'приводит', 'улучшил', 'ухудшил']) {
      expect(text).not.toContain(word)
    }
    // Raw enum identifiers stay out of the UI.
    expect(screen.queryByText('ordinal')).toBeNull()
    expect(screen.queryByText('during')).toBeNull()
  })

  it('shows an honest low-data summary instead of a confident difference', async () => {
    stubExperimentsApi(
      createFakeExperiments({
        experiments: [experimentFixture({ id: 1 })],
        detail: detailFixture({
          experiment: experimentFixture({ id: 1 }),
          analysis: analysisFixture({
            sufficient: false,
            summary:
              'Пока недостаточно данных для уверенного сравнения: отмеченных дней меньше, чем нужно для сопоставимых периодов.',
            overall: {
              ...analysisFixture().overall,
              after: {
                coverage: {
                  calendar_days: 14,
                  elapsed_days: 4,
                  observed_days: 2,
                  coverage: 2 / 14,
                },
                mean_score: null,
                scored_days: 0,
                completed_weight: 0,
                required_weight: 0,
              },
            },
          }),
        }),
      }),
    )

    renderDetail()

    expect(await screen.findByText(/недостаточно данных для уверенного сравнения/)).toBeInTheDocument()
  })

  it('warns when another experiment overlapped the period', async () => {
    stubExperimentsApi(
      createFakeExperiments({
        experiments: [experimentFixture({ id: 1 })],
        detail: detailFixture({
          experiment: experimentFixture({ id: 1 }),
          overlaps: [
            { id: 2, title: 'Ложиться до 00:00', start_date: '2026-09-05', end_date: '2026-09-18' },
          ],
        }),
      }),
    )

    renderDetail()

    expect(await screen.findByText(/пересекался ещё 1 эксперимент/)).toBeInTheDocument()
  })

  it('keeps a completed experiment window immutable', async () => {
    stubExperimentsApi(
      createFakeExperiments({
        experiments: [experimentFixture({ id: 1, status: 'completed' })],
        detail: detailFixture({ experiment: experimentFixture({ id: 1, status: 'completed' }) }),
      }),
    )

    renderDetail()

    expect(await screen.findByText(/Даты завершённого эксперимента не меняются/)).toBeInTheDocument()
  })

  it('renders missing days as gaps, never as zero, and missing metrics as a dash', async () => {
    const analysis = analysisFixture({
      state: [
        {
          key: 'state.mood',
          label: 'Настроение',
          kind: 'ordinal',
          before: { observed_days: 0, value: null },
          during: { observed_days: 0, value: null },
          after: { observed_days: 0, value: null },
          delta_during_vs_before: null,
        },
      ],
    })
    stubExperimentsApi(
      createFakeExperiments({
        experiments: [experimentFixture({ id: 1 })],
        detail: detailFixture({ experiment: experimentFixture({ id: 1 }), analysis }),
      }),
    )

    const { container } = renderDetail()
    await screen.findByRole('heading', { name: 'Без алкоголя 14 дней' })

    // The unobserved day is a gap, not a 0-height bar.
    const missingDay = container.querySelector('[data-date="2026-08-19"]')
    expect(missingDay).not.toBeNull()
    expect(missingDay).toHaveAttribute('data-observed', 'false')
    expect(missingDay?.querySelector('.experiment-chart__gap')).not.toBeNull()
    expect(missingDay?.querySelector('.experiment-chart__bar')).toBeNull()

    // An observed day still draws a bar (a real 0 would too — it is not "missing").
    const observedDay = container.querySelector('[data-date="2026-09-01"]')
    expect(observedDay).toHaveAttribute('data-observed', 'true')
    expect(observedDay?.querySelector('.experiment-chart__bar')).not.toBeNull()

    // A metric nobody filled shows a dash rather than 0.0.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('offers an edit form on the detail page', async () => {
    stubExperimentsApi(
      createFakeExperiments({
        experiments: [experimentFixture({ id: 1 })],
        detail: detailFixture({ experiment: experimentFixture({ id: 1 }) }),
      }),
    )

    renderDetail()
    fireEvent.click(await screen.findByRole('button', { name: 'Изменить' }))

    expect(screen.getByLabelText('Название')).toHaveValue('Без алкоголя 14 дней')
  })
})

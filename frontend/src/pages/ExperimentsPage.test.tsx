import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { jsonResponse, stubApi } from '../test/fetchStub'
import {
  createFakeExperiments,
  experimentFixture,
  stubExperimentsApi,
} from '../test/experimentsFixture'
import { ExperimentsPage } from './ExperimentsPage'

function renderPage() {
  return render(
    <MemoryRouter>
      <ExperimentsPage />
    </MemoryRouter>,
  )
}

describe('ExperimentsPage', () => {
  it('lists experiments with a human status and phase', async () => {
    stubExperimentsApi(
      createFakeExperiments({
        experiments: [
          experimentFixture({ id: 1, title: 'Без алкоголя 14 дней', status: 'active' }),
          experimentFixture({ id: 2, title: 'Ложиться до 00:00', status: 'completed' }),
        ],
      }),
    )

    renderPage()

    expect(await screen.findByText('Без алкоголя 14 дней')).toBeInTheDocument()
    expect(screen.getByText('Идёт')).toBeInTheDocument()
    expect(screen.getByText('Завершён')).toBeInTheDocument()
    expect(screen.getAllByText(/день 6 из 14|После|собрано/).length).toBeGreaterThan(0)
    // Raw backend enum values must never reach the UI.
    expect(screen.queryByText('active')).toBeNull()
    expect(screen.queryByText('completed')).toBeNull()
  })

  it('links a card to the experiment detail page', async () => {
    stubExperimentsApi(createFakeExperiments({ experiments: [experimentFixture({ id: 5 })] }))

    renderPage()

    const link = await screen.findByRole('link', { name: 'Без алкоголя 14 дней' })
    expect(link).toHaveAttribute('href', '/experiments/5')
  })

  it('shows an empty state when there are no experiments', async () => {
    stubExperimentsApi(createFakeExperiments())

    renderPage()

    expect(await screen.findByText(/Экспериментов пока нет/)).toBeInTheDocument()
  })

  it('creates an experiment from the form', async () => {
    const fake = createFakeExperiments()
    stubExperimentsApi(fake)

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Новый эксперимент' }))

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Без сахара' } })
    fireEvent.change(screen.getByLabelText('Гипотеза'), { target: { value: 'Больше энергии' } })
    fireEvent.change(screen.getByLabelText('Что меняем'), { target: { value: 'Не есть сладкое' } })
    fireEvent.change(screen.getByLabelText('Дата начала'), { target: { value: '2026-10-01' } })
    fireEvent.change(screen.getByLabelText('Дата окончания'), { target: { value: '2026-10-07' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать эксперимент' }))

    expect(await screen.findByText('Без сахара')).toBeInTheDocument()
    expect(fake.experiments.map((item) => item.title)).toContain('Без сахара')
  })

  it('refuses to submit without a title', async () => {
    const fake = createFakeExperiments()
    stubExperimentsApi(fake)

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Новый эксперимент' }))
    fireEvent.click(screen.getByRole('button', { name: 'Создать эксперимент' }))

    expect(await screen.findByText('Введите название эксперимента.')).toBeInTheDocument()
    expect(fake.experiments).toHaveLength(0)
  })

  it('rejects an end date before the start date without calling the API', async () => {
    const fake = createFakeExperiments()
    stubExperimentsApi(fake)

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Новый эксперимент' }))
    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'X' } })
    fireEvent.change(screen.getByLabelText('Гипотеза'), { target: { value: 'Y' } })
    fireEvent.change(screen.getByLabelText('Что меняем'), { target: { value: 'Z' } })
    fireEvent.change(screen.getByLabelText('Дата начала'), { target: { value: '2026-10-10' } })
    fireEvent.change(screen.getByLabelText('Дата окончания'), { target: { value: '2026-10-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать эксперимент' }))

    expect(
      await screen.findByText('Дата окончания не может быть раньше даты начала.'),
    ).toBeInTheDocument()
    expect(fake.experiments).toHaveLength(0)
  })

  it('cancels a scheduled experiment', async () => {
    const fake = createFakeExperiments({
      experiments: [experimentFixture({ id: 3, status: 'scheduled' })],
    })
    stubExperimentsApi(fake)

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Отменить' }))

    await waitFor(() => expect(screen.getByText('Отменён')).toBeInTheDocument())
    expect(fake.experiments[0]?.cancelled_on).toBe('2026-09-06')
  })

  it('shows the contextual owl banner when the backend provides one', async () => {
    stubApi({
      'GET /api/experiments': () =>
        jsonResponse({
          experiments: [experimentFixture({ id: 1, status: 'active' })],
          owl: {
            owl_id: 'experiment_active',
            asset_key: 'owl_insight',
            tone: 'supportive',
            priority: 10,
            caption_line1: 'Ну что, проверим.',
            caption_line2: 'Эксперимент «Без алкоголя 14 дней» идёт: день 6 из 14.',
            dismissible: true,
            fingerprint: 'experiments|experiment_active|Без алкоголя 14 дней',
            context: 'experiments',
            fallback_line1: null,
          },
        }),
    })

    renderPage()

    expect(await screen.findByTestId('owl-banner')).toBeInTheDocument()
    expect(screen.getByText('Ну что, проверим.')).toBeInTheDocument()
  })
})

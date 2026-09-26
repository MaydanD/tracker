import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { jsonResponse, stubApi } from '../test/fetchStub'
import { recordsFixture, stubRecords } from '../test/recordsFixture'
import { RecordsPage } from './RecordsPage'

function renderPage() {
  return render(
    <MemoryRouter>
      <RecordsPage />
    </MemoryRouter>,
  )
}

describe('RecordsPage', () => {
  it('renders the summary and record cards in Russian', async () => {
    stubRecords()
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Рекорды и достижения' })).toBeInTheDocument()
    expect(screen.getByText('Трекинг: 42 дня')).toBeInTheDocument()
    expect(screen.getByText('Выполнений привычек: 412')).toBeInTheDocument()
    expect(screen.getByText('Завершено экспериментов: 2')).toBeInTheDocument()

    // Longest streak keeps its habit and its real date range.
    const streakCard = screen.getByText('Самая длинная серия').closest('article') as HTMLElement
    expect(within(streakCard).getByText('28 дней')).toBeInTheDocument()
    expect(within(streakCard).getByText('Чтение')).toBeInTheDocument()
    expect(within(streakCard).getByText('12.08.2026 — 08.09.2026')).toBeInTheDocument()
    expect(screen.getByText('Сейчас идёт: 12 дней')).toBeInTheDocument()

    // Best day and week are descriptive, with their coverage context.
    expect(screen.getByText('Лучший день')).toBeInTheDocument()
    expect(screen.getByText('Таких же лучших дней: 3')).toBeInTheDocument()
    const weekCard = screen.getByText('Лучшая неделя').closest('article') as HTMLElement
    expect(within(weekCard).getByText('94%')).toBeInTheDocument()
    expect(within(weekCard).getByText('Покрытие: 100%')).toBeInTheDocument()
  })

  it('groups achievements into recently achieved, achieved and next goals', async () => {
    stubRecords()
    renderPage()

    // 4 achievements in the fixture, 2 achieved.
    expect(await screen.findByText('Получено 2 из 4')).toBeInTheDocument()
    expect(screen.getByText('Недавно получено')).toBeInTheDocument()
    expect(screen.getByText('Следующие цели')).toBeInTheDocument()

    // An achieved entry shows its real date rather than a progress bar.
    const recent = screen.getByText('Месяц без отрыва').closest('li') as HTMLElement
    expect(within(recent).getByText('Получено')).toBeInTheDocument()
    expect(within(recent).getByText('Достигнуто 18.09.2026')).toBeInTheDocument()
    expect(within(recent).queryByRole('progressbar')).toBeNull()

    // A locked entry shows honest progress toward its target.
    const locked = screen.getByText('100 выполнений').closest('li') as HTMLElement
    expect(within(locked).getByText('Цель')).toBeInTheDocument()
    expect(within(locked).getByText('73 / 100')).toBeInTheDocument()
    const bar = within(locked).getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '73')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
  })

  it('keeps the backend achievement order instead of re-sorting locally', async () => {
    stubRecords()
    renderPage()

    await screen.findByText('Получено 2 из 4')
    const lockedCards = screen.getAllByText('Цель').map(
      (node) => within(node.closest('li') as HTMLElement).getByText(/выполнений|трекинга/).textContent,
    )
    expect(lockedCards).toEqual(['100 выполнений', '100 дней трекинга'])
  })

  it('shows the consistency block and marks an archived habit', async () => {
    const fixture = recordsFixture()
    stubRecords(recordsFixture({
      records: {
        ...fixture.records,
        consistency: [
          { ...fixture.records.consistency[0]!, habit_id: 2, name: 'Зарядка', archived: true },
        ],
      },
    }))
    renderPage()

    expect(await screen.findByText('Самая стабильная привычка')).toBeInTheDocument()
    expect(screen.getByText('Зарядка · в архиве')).toBeInTheDocument()
    expect(screen.getByText('Август 2026 · 29 из 31 дней')).toBeInTheDocument()
  })

  it('still lists locked goals when there are no records yet', async () => {
    const fixture = recordsFixture()
    stubRecords(recordsFixture({
      summary: {
        first_tracked_day: null,
        tracked_days: 0,
        habit_completions: 0,
        experiments_created: 0,
        completed_experiments: 0,
        stable_insight_on: null,
        well_supported_insight_on: null,
      },
      records: {
        longest_streak: null,
        best_day: null,
        best_week: null,
        most_completed: null,
        consistency: [],
      },
      achievements: fixture.achievements.map((item) => ({
        ...item, achieved: false, achieved_on: null,
      })),
      recent_achievements: [],
      achieved_count: 0,
    }))
    renderPage()

    expect(await screen.findByText(/Рекордов пока нет/)).toBeInTheDocument()
    expect(screen.getByText('Трекинг: пока нет записей')).toBeInTheDocument()
    expect(screen.getByText('Получено 0 из 4')).toBeInTheDocument()
    expect(screen.getAllByText('Цель')).toHaveLength(4)
  })

  it('surfaces a backend failure instead of pretending there are no records', async () => {
    stubApi({
      'GET /api/records': () =>
        jsonResponse({ error: { code: 'internal_error', message: 'boom' } }, 500),
    })
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'На сервере произошла ошибка. Попробуйте ещё раз.',
    )
  })

  it('never prints raw enum keys or unit identifiers', async () => {
    stubRecords()
    const { container } = renderPage()

    await screen.findByText('Получено 2 из 4')
    const text = container.textContent ?? ''
    for (const raw of ['streak', 'consistency', 'tracking', 'days', 'weeks', 'achieved']) {
      expect(text).not.toContain(raw)
    }
  })
})

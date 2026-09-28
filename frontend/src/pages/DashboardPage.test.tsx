import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { jsonResponse, stubApi } from '../test/fetchStub'
import { DashboardPage } from './DashboardPage'

const TODAY = '2026-09-25'

function mockDashboardData(overrides: Record<string, unknown> = {}) {
  return {
    today: TODAY,
    today_progress: {
      score: 100,
      completed_weight: 2,
      required_weight: 2,
      entry_date: TODAY,
      obligations: [
        { habit_id: 1, name: 'Чтение', weight: 2, entry_status: 'done', satisfied: true },
      ],
    },
    week_progress: {
      score: 66.7,
      completed_weight: 2,
      required_weight: 3,
      week_start: '2026-09-21',
      week_end: '2026-09-27',
      habits: [
        {
          habit_id: 2,
          name: 'Тренировка',
          quota: 3,
          completed_count: 2,
          daily_required_count: 0,
          daily_completed_count: 0,
          weekly_quota: 3,
          weekly_completed_count: 2,
          weekly_weight: 1,
          weekly_effective_from: '2026-09-01',
          preferred_weekdays: [0, 2, 4],
          status: 'pending',
          score: 66.7,
          completed_weight: 2,
          required_weight: 3,
        },
      ],
    },
    streaks: [
      { habit_id: 1, current_streak: 12, unit: 'days', as_of: TODAY },
      { habit_id: 2, current_streak: 4, unit: 'weeks', as_of: TODAY },
    ],
    yesterday_state: null,
    today_items: [
      {
        habit_id: 1,
        name: 'Чтение',
        area: { id: 1, name: 'Здоровье', color: '#4a7cc7', is_archived: false },
        weight: 2,
        tracking_mode: 'binary',
        quantity_unit: null,
        quantity_allows_decimal: false,
        schedule: {
          type: 'daily',
          weekdays: [],
          times_per_week: null,
          weekly_required_count: 7,
          summary: 'Каждый день',
        },
        is_archived: false,
        entry: {
          id: 10,
          habit_id: 1,
          entry_date: TODAY,
          status: 'done',
          quantity_value: null,
          quantity_unit: null,
          skip_reason: null,
          note: null,
          created_at: '2026-09-25T10:00:00',
          updated_at: '2026-09-25T10:00:00',
        },
      },
    ],
    owl: null,
    records: null,
    ...overrides,
  }
}

function stubDashboard(overrides: Record<string, unknown> = {}) {
  stubApi({
    'GET /api/dashboard': () => jsonResponse(mockDashboardData(overrides)),
    'GET /api/calendar': () => jsonResponse([
      {
        entry_date: '2026-09-24',
        daily_score: 40,
        completed_weight: 2,
        required_weight: 5,
        has_obligations: true,
        has_daily_state: false,
        mood: null,
        is_future: false,
        area_scores: [{ area_id: 1, name: 'Здоровье', color: '#4a7cc7', score: 40 }],
        habit_scores: [],
      },
      {
        entry_date: TODAY,
        daily_score: 75,
        completed_weight: 3,
        required_weight: 4,
        has_obligations: true,
        has_daily_state: false,
        mood: null,
        is_future: false,
        area_scores: [{ area_id: 1, name: 'Здоровье', color: '#4a7cc7', score: 75 }],
        habit_scores: [],
      },
    ]),
  })
}

describe('DashboardPage', () => {
  it('shows the owl composition, a real colored area trend, week progress and compact streaks', async () => {
    stubDashboard()
    const { container } = render(<DashboardPage />)

    expect(await screen.findByText('Пока без особых новостей.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Главный обзор' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Обзор вашей активности:/)).not.toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Сова-помощник' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Заполнить' })).not.toBeInTheDocument()
    const page = container.querySelector('.dashboard-page')
    expect(page?.firstElementChild).toHaveClass('dashboard-character')
    expect(page?.querySelector('.dashboard-message--quiet')).toBeInTheDocument()
    expect(page?.querySelector('.dashboard-trends')).toBeInTheDocument()
    expect(page?.querySelector('.dashboard-week')).toBeInTheDocument()
    expect(page?.querySelector('.dashboard-streaks')).toBeInTheDocument()
    expect(page?.textContent).not.toMatch(/Вчера|Сегодня/)

    // The region renders before its calendar data arrives, so the chart, its
    // legend and its lines all have to be awaited, not queried synchronously.
    const trends = await screen.findByRole('region', { name: 'Динамика по сферам' })
    expect(await within(trends).findByRole('img', {
      name: 'Оценка выполнения привычек по сферам за последние 30 дней',
    })).toBeInTheDocument()
    expect(within(trends).getByRole('list')).toHaveTextContent('Здоровье')
    expect(trends.querySelector('path[data-area-id="1"]')).toHaveAttribute('stroke', '#4a7cc7')

    const week = screen.getByRole('region', { name: 'Прогресс недели' })
    expect(within(week).getByText('66,7%')).toBeInTheDocument()
    expect(within(week).getByText('2 / 3 по весу')).toBeInTheDocument()
    expect(within(week).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '66.7')

    const streaks = screen.getByRole('region', { name: 'Текущие серии' })
    expect(within(streaks).getByText('Чтение')).toBeInTheDocument()
    expect(within(streaks).getByText('🔥 12 дней')).toBeInTheDocument()
    expect(within(streaks).getByText('Тренировка')).toBeInTheDocument()
    expect(within(streaks).getByText('🔥 4 недели')).toBeInTheDocument()
  })

  it('does not draw a flame for a habit whose streak is over or never started', async () => {
    stubDashboard({
      streaks: [
        { habit_id: 1, current_streak: 0, unit: 'days', as_of: TODAY },
        { habit_id: 2, current_streak: 4, unit: 'weeks', as_of: TODAY },
      ],
    })
    render(<DashboardPage />)

    const streaks = await screen.findByRole('region', { name: 'Текущие серии' })
    const broken = within(streaks).getByText('Нет серии')
    expect(broken).toHaveClass('dashboard-streak__value--none')
    expect(streaks.textContent).not.toContain('🔥 0')
    // A real streak keeps its warm, active value.
    expect(within(streaks).getByText('🔥 4 недели')).toHaveClass('dashboard-streak__value')
    expect(within(streaks).getByText('🔥 4 недели')).not.toHaveClass('dashboard-streak__value--none')
  })

  it('shows the current owl message and no fill action for a fully marked day', async () => {
    stubDashboard({
      owl: {
        owl_id: 'all_completed',
        asset_key: 'owl_all_done',
        tone: 'celebratory',
        priority: 70,
        caption_line1: 'Ну вот. Можешь жить.',
        caption_line2: 'Все обязательные привычки на сегодня выполнены — 100%.',
        dismissible: false,
        fingerprint: 'abc123',
        context: 'dashboard',
        fallback_line1: null,
      },
    })
    render(<DashboardPage />)

    const message = await screen.findByTestId('owl-banner')
    expect(message).toHaveClass('owl-banner--dashboard')
    expect(within(message).getByText('Ну вот. Можешь жить.')).toBeInTheDocument()
    expect(within(message).getByText('Все обязательные привычки на сегодня выполнены — 100%.')).toBeInTheDocument()
    expect(within(message).queryByRole('link', { name: 'Заполнить' })).not.toBeInTheDocument()
  })

  it.each([
    ['не заполненном', null],
    ['частично заполненном', 'done'],
  ])('offers the check-in action for a %s day', async (_description, firstEntryStatus) => {
    stubDashboard({
      owl: {
        owl_id: 'pending',
        asset_key: 'owl_pending',
        tone: 'cautionary',
        priority: 20,
        caption_line1: 'Эй, отметь привычку!',
        caption_line2: 'Остались незаполненные отметки.',
        dismissible: false,
        fingerprint: 'pending-abc',
        context: 'dashboard',
        fallback_line1: null,
      },
      today_progress: {
        score: 50,
        completed_weight: 1,
        required_weight: 2,
        entry_date: TODAY,
        obligations: [
          { habit_id: 1, name: 'Чтение', weight: 1, entry_status: firstEntryStatus, satisfied: firstEntryStatus !== null },
          { habit_id: 2, name: 'Прогулка', weight: 1, entry_status: null, satisfied: false },
        ],
      },
    })
    render(<DashboardPage />)

    const message = await screen.findByTestId('owl-banner')
    expect(within(message).getByText('Эй, отметь привычку!')).toBeInTheDocument()
    expect(within(message).getByRole('link', { name: 'Заполнить' })).toHaveAttribute(
      'href',
      `#/check-in?date=${TODAY}`,
    )
    expect(within(message).queryByRole('button', { name: 'Скрыть' })).not.toBeInTheDocument()
  })
})

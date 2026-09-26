import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { jsonResponse, stubApi } from '../test/fetchStub'
import { recordsPreviewFixture } from '../test/recordsFixture'
import { DashboardPage } from './DashboardPage'

const TODAY = '2026-09-25'
const YESTERDAY = '2026-09-24'

function mockDashboardData(overrides: Record<string, unknown> = {}) {
  return {
    today: TODAY,
    today_progress: {
      score: 100.0,
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
    yesterday_state: {
      id: 1,
      state_date: YESTERDAY,
      created_at: '2026-09-24T20:00:00',
      updated_at: '2026-09-24T20:00:00',
      mood: 4,
      energy: 3,
      wellbeing: 4,
      sleep_status: 'underslept',
      sleep_minutes: 380,
      alcohol: false,
      alcohol_detail: null,
      gaming: null, // Tri-state: unspecified! Must NOT show "Нет"
      gaming_minutes: null,
      computer_overuse: true,
      computer_minutes: 480,
      note: 'Хороший вечер',
    },
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

describe('DashboardPage', () => {
  it('renders Dashboard with Today, Week, Streaks, and Yesterday State in Russian', async () => {
    stubApi({
      'GET /api/dashboard': () => jsonResponse(mockDashboardData()),
    })

    render(<DashboardPage />)

    expect(await screen.findByRole('heading', { name: 'Главный обзор' })).toBeInTheDocument()

    // Today section
    const todayRegion = screen.getByRole('region', { name: 'Сегодня' })
    expect(todayRegion).toBeInTheDocument()
    expect(within(todayRegion).getByText('Чтение')).toBeInTheDocument()
    expect(within(todayRegion).getByText('100%')).toBeInTheDocument()
    expect(within(todayRegion).getByRole('link', { name: 'Перейти в Итоги дня →' })).toHaveAttribute(
      'href',
      `#/check-in?date=${TODAY}`,
    )

    // Week section
    const weekRegion = screen.getByRole('region', { name: 'Эта неделя' })
    expect(weekRegion).toBeInTheDocument()
    expect(within(weekRegion).getByText('Тренировка')).toBeInTheDocument()
    expect(within(weekRegion).getByText(/Квота: 2 \/ 3/)).toBeInTheDocument()
    expect(within(weekRegion).getByText(/Предпочтительно: Пн, Ср, Пт/)).toBeInTheDocument()
    expect(within(weekRegion).getByText('В процессе')).toBeInTheDocument()

    // Streaks section
    const streaksRegion = screen.getByRole('region', { name: 'Текущие серии' })
    expect(streaksRegion).toBeInTheDocument()
    expect(within(streaksRegion).getByText('🔥 12 дней')).toBeInTheDocument()
    expect(within(streaksRegion).getByText('🔥 4 недели')).toBeInTheDocument()

    // Yesterday section
    const yesterdayRegion = screen.getByRole('region', { name: 'Вчерашнее состояние' })
    expect(yesterdayRegion).toBeInTheDocument()
    expect(within(yesterdayRegion).getAllByText('4 / 5')).toHaveLength(2) // mood and wellbeing
    expect(within(yesterdayRegion).getByText('Недосып · 6 ч 20 мин')).toBeInTheDocument()
    expect(within(yesterdayRegion).getByText('Нет')).toBeInTheDocument() // alcohol is false
    expect(within(yesterdayRegion).getByText('Слишком много · 8 ч')).toBeInTheDocument()
    expect(within(yesterdayRegion).getByText('Хороший вечер')).toBeInTheDocument()
  })

  it('renders "Состояние вчера не заполнено" when yesterday state is null', async () => {
    stubApi({
      'GET /api/dashboard': () => jsonResponse(mockDashboardData({ yesterday_state: null })),
    })

    render(<DashboardPage />)

    expect(await screen.findByText('Состояние вчера не заполнено')).toBeInTheDocument()
  })

  it('shows a compact records preview with a link to all records', async () => {
    stubApi({
      'GET /api/dashboard': () => jsonResponse(mockDashboardData({
        records: recordsPreviewFixture(),
      })),
    })

    render(<DashboardPage />)

    const region = await screen.findByRole('region', { name: 'Рекорды' })
    expect(within(region).getByText('Чтение — 28 дней')).toBeInTheDocument()
    expect(within(region).getByText(/Месяц без отрыва/)).toBeInTheDocument()
    expect(within(region).getByText('4 из 12')).toBeInTheDocument()
    expect(within(region).getByRole('link', { name: 'Все рекорды →' })).toHaveAttribute(
      'href', '#/records',
    )
  })

  it('hides the records preview when the backend sends none', async () => {
    stubApi({ 'GET /api/dashboard': () => jsonResponse(mockDashboardData()) })

    render(<DashboardPage />)

    expect(await screen.findByRole('heading', { name: 'Главный обзор' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Рекорды' })).toBeNull()
  })

  it('shows the contextual Owl banner above the cards', async () => {
    stubApi({
      'GET /api/dashboard': () =>
        jsonResponse(mockDashboardData({
          owl: {
            owl_id: 'all_completed',
            asset_key: 'owl_all_done',
            tone: 'celebratory',
            priority: 70,
            caption_line1: 'Ну вот. Можешь жить.',
            caption_line2: 'Все обязательные привычки на сегодня выполнены — 100%.',
            dismissible: true,
            fingerprint: 'abc123',
            context: 'dashboard',
            fallback_line1: null,
          },
        })),
    })

    render(<DashboardPage />)

    const banner = await screen.findByTestId('owl-banner')
    expect(within(banner).getByText('Ну вот. Можешь жить.')).toBeInTheDocument()
    expect(
      within(banner).getByText('Все обязательные привычки на сегодня выполнены — 100%.'),
    ).toBeInTheDocument()
    expect(within(banner).getByRole('img', { name: 'Сова-помощник' })).toBeInTheDocument()
  })
})

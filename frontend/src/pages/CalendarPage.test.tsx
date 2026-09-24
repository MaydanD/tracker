import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { jsonResponse, stubApi } from '../test/fetchStub'
import { CalendarPage } from './CalendarPage'

const TEST_DATE = '2026-09-25'

function mockCalendarRangeData() {
  return [
    {
      entry_date: '2026-09-24',
      daily_score: 100.0,
      completed_weight: 2,
      required_weight: 2,
      has_obligations: true,
      has_daily_state: true,
      mood: 4,
      is_future: false,
    },
    {
      entry_date: '2026-09-25',
      daily_score: 50.0,
      completed_weight: 1,
      required_weight: 2,
      has_obligations: true,
      has_daily_state: false,
      mood: null,
      is_future: false,
    },
    {
      entry_date: '2026-09-26',
      daily_score: null,
      completed_weight: 0,
      required_weight: 0,
      has_obligations: false,
      has_daily_state: false,
      mood: null,
      is_future: true,
    },
  ]
}

function mockDayOverviewData() {
  return {
    entry_date: TEST_DATE,
    today: TEST_DATE,
    is_future: false,
    progress: {
      score: 50.0,
      completed_weight: 1,
      required_weight: 2,
      entry_date: TEST_DATE,
      obligations: [
        { habit_id: 1, name: 'Зарядка', weight: 2, entry_status: 'done', satisfied: true },
      ],
    },
    items: [
      {
        habit_id: 1,
        name: 'Зарядка',
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
          entry_date: TEST_DATE,
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
    state: null,
  }
}

describe('CalendarPage', () => {
  it('renders Calendar and Heatmap with Monday-first weekday headers in Russian', async () => {
    stubApi({
      'GET /api/calendar': () => jsonResponse(mockCalendarRangeData()),
      [`GET /api/days/${TEST_DATE}/overview`]: () => jsonResponse(mockDayOverviewData()),
    })

    render(<CalendarPage />)

    expect(await screen.findByRole('heading', { name: 'Календарь и тепловая карта' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Месячный календарь' })).toBeInTheDocument()

    // Check Monday-first weekdays
    expect(screen.getByText('Пн')).toBeInTheDocument()
    expect(screen.getByText('Вс')).toBeInTheDocument()
  })

  it('selects a day in calendar and opens Day Card panel with "Открыть день" button', async () => {
    stubApi({
      'GET /api/calendar': () => jsonResponse(mockCalendarRangeData()),
      [`GET /api/days/${TEST_DATE}/overview`]: () => jsonResponse(mockDayOverviewData()),
    })

    render(<CalendarPage />)

    expect(await screen.findByRole('heading', { name: 'Календарь и тепловая карта' })).toBeInTheDocument()

    const dayCell = screen.getByRole('button', { name: 'Выбрать день 25.09.2026' })
    fireEvent.click(dayCell)

    expect(await screen.findByRole('region', { name: 'Карточка выбранного дня' })).toBeInTheDocument()
    expect(screen.getByText('Зарядка')).toBeInTheDocument()

    const openDayLink = screen.getByRole('link', { name: 'Открыть день →' })
    expect(openDayLink).toHaveAttribute('href', `#/check-in?date=${TEST_DATE}`)
  })
})

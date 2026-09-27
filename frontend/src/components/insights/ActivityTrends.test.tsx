import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { jsonResponse, stubApi } from '../../test/fetchStub'
import { ActivityTrends } from './ActivityTrends'

describe('ActivityTrends', () => {
  it('loads a 90-day range and immediately renders completion and mood charts', async () => {
    let requestedRange = ''
    let requestedTrends = false
    stubApi({
      'GET /api/calendar': (request) => {
        requestedRange = `${request.query.get('start')} — ${request.query.get('end')}`
        requestedTrends = request.query.get('include_trends') === 'true'
        return jsonResponse([
          {
            entry_date: '2026-09-24',
            daily_score: 75,
            completed_weight: 3,
            required_weight: 4,
            has_obligations: true,
            has_daily_state: true,
            mood: 4,
            is_future: false,
            area_scores: [{ area_id: 1, name: 'Здоровье', color: '#4a7cc7', score: 100 }],
            habit_scores: [{
              habit_id: 1, name: 'Зарядка', area_id: 1, area_name: 'Здоровье',
              color: '#4a7cc7', score: 100,
            }],
          },
          {
            entry_date: '2026-09-25',
            daily_score: 100,
            completed_weight: 4,
            required_weight: 4,
            has_obligations: true,
            has_daily_state: true,
            mood: 5,
            is_future: false,
            area_scores: [{ area_id: 1, name: 'Здоровье', color: '#4a7cc7', score: 0 }],
            habit_scores: [{
              habit_id: 1, name: 'Зарядка', area_id: 1, area_name: 'Здоровье',
              color: '#4a7cc7', score: 0,
            }],
          },
        ])
      },
    })

    render(<ActivityTrends today="2026-09-25" />)

    expect(await screen.findByText('Выполнение привычек')).toBeInTheDocument()
    expect(screen.getByText('Настроение')).toBeInTheDocument()
    expect(screen.getByText('Сфера: Здоровье')).toBeInTheDocument()
    expect(screen.getByText('Привычка: Зарядка')).toBeInTheDocument()
    await waitFor(() => expect(requestedRange).toBe('2026-06-28 — 2026-09-25'))
    expect(requestedTrends).toBe(true)
    expect(screen.getAllByRole('img')).toHaveLength(4)
  })

  it('accepts legacy calendar days without trend fields and null trend lists', async () => {
    stubApi({
      'GET /api/calendar': () => jsonResponse([
        {
          entry_date: '2026-09-24',
          daily_score: null,
          completed_weight: 0,
          required_weight: 0,
          has_obligations: false,
          has_daily_state: false,
          mood: null,
          is_future: false,
        },
        {
          entry_date: '2026-09-25',
          daily_score: null,
          completed_weight: 0,
          required_weight: 0,
          has_obligations: false,
          has_daily_state: false,
          mood: null,
          is_future: false,
          area_scores: null,
          habit_scores: null,
        },
      ]),
    })

    render(<ActivityTrends today="2026-09-25" />)

    expect(await screen.findByText('Выполнение привычек')).toBeInTheDocument()
    expect(screen.getByText('Настроение')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Графики по сферам' })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Графики по привычкам' })).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

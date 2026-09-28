import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ProgressState } from '../api/types'
import { HabitWeekLabel, ProgressSummary, StreakLabel } from '../components/daily/ProgressSummary'
import { localTodayIso } from '../components/daily/dates'
import { progressFixture, weekHabitFixture } from '../test/progressFixture'

const TODAY = localTodayIso()

function scored(): ProgressState {
  const value = progressFixture()
  value.day = { ...value.day, score: 40, completed_weight: 2, required_weight: 5 }
  value.week = { ...value.week, score: 100, completed_weight: 6, required_weight: 6, habits: [weekHabitFixture({ completed_count: 5, weekly_completed_count: 5 })] }
  return value
}

describe('Оценки и серии на итогах дня', () => {
  it('shows exact score, weights, capped weekly score and Russian text', () => {
    render(<ProgressSummary progress={scored()} />)
    expect(screen.getByText('40%')).toBeInTheDocument()
    expect(screen.getByText(/2 \/ 5 по весу/)).toBeInTheDocument()
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText(/Спорт: 5 \/ 3/)).toBeInTheDocument()
    expect(screen.getByText(/Нейтральные привычки учитываются только в заполнении/)).toBeInTheDocument()
    expect(screen.getByLabelText('Показатели выполнения').textContent).not.toMatch(/[A-Za-z]/)
  })

  it('explains null scores without manufacturing zero or full completion', () => {
    render(<ProgressSummary progress={progressFixture()} />)
    expect(screen.getAllByText('Нет обязательных привычек')).toHaveLength(2)
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it('shows preferred days and pending flexible progress without failure wording', () => {
    render(<HabitWeekLabel progress={weekHabitFixture({ status: 'pending', completed_count: 1 })} />)
    expect(screen.getByText(/1 \/ 3 за выбранную неделю · Ожидает выполнения/)).toBeInTheDocument()
    expect(screen.getByText('Предпочтительно: Пн, Ср, Пт')).toBeInTheDocument()
    expect(screen.getByText(/можно перенести внутри недели/)).toBeInTheDocument()
    expect(screen.queryByText(/не выполнена/)).not.toBeInTheDocument()
  })

  it.each([
    ['days', 1, '1 день'], ['days', 7, '7 дней'], ['days', 22, '22 дня'],
    ['weeks', 1, '1 неделя'], ['weeks', 4, '4 недели'], ['weeks', 11, '11 недель'],
  ] as const)('formats %s streak %i in Russian', (unit, count, label) => {
    render(<StreakLabel streak={{ habit_id: 1, current_streak: count, unit, as_of: TODAY }} />)
    expect(screen.getByText(new RegExp(`🔥 ${label}`))).toBeInTheDocument()
  })
})

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ProgressState } from '../api/types'
import { ProgressSummary, StreakLabel, HabitWeekLabel } from '../components/daily/ProgressSummary'
import { addDays, localTodayIso } from '../components/daily/dates'
import { createFakeApi } from '../test/fakeApi'
import { habitFixture } from '../test/fixtures'
import { jsonResponse, stubApi, stubFetch } from '../test/fetchStub'
import { progressFixture, weekHabitFixture } from '../test/progressFixture'
import { CheckInPage } from './CheckInPage'

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
    expect(screen.getByText(/Пропуск с причиной не повышает оценку/)).toBeInTheDocument()
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

  it('refreshes derived progress after an off-preferred-day completion and clearing', async () => {
    const habit = habitFixture({ id: 1, name: 'Спорт', current_version: { version_number: 1, effective_from: addDays(TODAY, -30), created_at: TODAY }, schedule: { type: 'weekdays', weekdays: [0, 2, 4], times_per_week: null, weekly_required_count: 3, summary: 'Mon, Wed, Fri' } })
    const api = createFakeApi({ habits: [habit] })
    const base = progressFixture()
    // Choose a Tuesday in the past; backend contract supplies the recalculation.
    const tuesday = addDays(base.week.week_start, -6)
    let reads = 0
    stubApi({}, { fallback: (request) => {
      if (request.path.startsWith('/api/progress/days/')) {
        reads += 1
        const result = progressFixture(request.path.split('/').at(-1))
        const saved = api.entries.some((entry) => entry.status === 'done')
        result.week.habits = [weekHabitFixture({ completed_count: saved ? 3 : 2, weekly_completed_count: saved ? 3 : 2, status: saved ? 'satisfied' : 'failed' })]
        result.week.score = saved ? 100 : 66.6667
        result.week.completed_weight = saved ? 6 : 4
        result.week.required_weight = 6
        result.streaks = [{ habit_id: 1, current_streak: saved ? 4 : 3, unit: 'weeks', as_of: TODAY }]
        return jsonResponse(result)
      }
      return api.handle(request)
    } })
    render(<CheckInPage />)
    await screen.findByText('Спорт')
    fireEvent.change(screen.getByLabelText('Дата'), { target: { value: tuesday } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Выполнено' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    expect(await screen.findByText(/3 \/ 3 за выбранную неделю/)).toBeInTheDocument()
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText(/🔥 4 недели/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Очистить' }))
    expect(await screen.findByText(/2 \/ 3 за выбранную неделю/)).toBeInTheDocument()
    expect(reads).toBeGreaterThanOrEqual(4)
  })

  it('keeps skipped entries visibly unsuccessful', async () => {
    const habit = habitFixture({ name: 'Чтение', current_version: { version_number: 1, effective_from: addDays(TODAY, -3), created_at: TODAY } })
    const api = createFakeApi({ habits: [habit] })
    const result = progressFixture()
    result.day = { ...result.day, score: 0, required_weight: 3 }
    stubApi({ [`GET /api/progress/days/${TODAY}`]: () => jsonResponse(result) }, { fallback: api.handle })
    render(<CheckInPage />)
    await screen.findByText('Чтение')
    fireEvent.click(screen.getByRole('button', { name: 'Осознанный пропуск' }))
    fireEvent.change(screen.getByLabelText(/Причина/), { target: { value: 'Болел' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(api.entries).toHaveLength(1))
    expect(await screen.findByText('0%')).toBeInTheDocument()
    expect(screen.getByText(/0 \/ 3 по весу/)).toBeInTheDocument()
    expect((await screen.findByText(/Причина: Болел/)).closest('[role="status"]')).toHaveClass('state--skipped')
  })

  it('does not show delayed progress for the previous date', async () => {
    let release: (() => void) | undefined
    const api = createFakeApi()
    const tomorrow = addDays(TODAY, 1)
    stubFetch(async (input) => {
      const path = new URL(String(input), 'http://localhost').pathname
      if (path === `/api/progress/days/${TODAY}`) {
        await new Promise<void>((resolve) => { release = resolve })
        return jsonResponse(scored())
      }
      if (path.startsWith('/api/progress/days/')) return jsonResponse(progressFixture(tomorrow))
      return api.handle({ method: 'GET', path, query: new URLSearchParams(), body: null })
    })
    render(<CheckInPage />)
    await screen.findByText(/На эту дату ещё нет привычек/)
    fireEvent.change(screen.getByLabelText('Дата'), { target: { value: tomorrow } })
    await screen.findAllByText('Нет обязательных привычек')
    release?.()
    await waitFor(() => expect(screen.queryByText('40%')).not.toBeInTheDocument())
  })

  it('offers a Russian retry when calculation fails', async () => {
    let fails = true
    const api = createFakeApi()
    stubApi({ [`GET /api/progress/days/${TODAY}`]: () => fails
      ? jsonResponse({ error: { code: 'internal_error', message: 'Internal error' } }, 500)
      : jsonResponse(scored()) }, { fallback: api.handle })
    render(<CheckInPage />)
    const retry = await screen.findByRole('button', { name: 'Повторить расчёт' })
    expect(screen.queryByText('Internal error')).not.toBeInTheDocument()
    fails = false
    fireEvent.click(retry)
    expect(await screen.findByText('40%')).toBeInTheDocument()
  })
})

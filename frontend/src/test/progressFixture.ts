import type { ProgressState, WeekHabitProgress } from '../api/types'
import { addDays, localTodayIso } from '../components/daily/dates'

/** Contract fixtures, deliberately not a second implementation of scoring. */
export function progressFixture(on = localTodayIso()): ProgressState {
  const day = new Date(`${on}T12:00:00`).getDay()
  const start = addDays(on, -((day + 6) % 7))
  return {
    today: localTodayIso(),
    day: { entry_date: on, score: null, completed_weight: 0, required_weight: 0, obligations: [] },
    week: { week_start: start, week_end: addDays(start, 6), score: null, completed_weight: 0, required_weight: 0, habits: [] },
    streaks: [],
  }
}

export function weekHabitFixture(overrides: Partial<WeekHabitProgress> = {}): WeekHabitProgress {
  return {
    habit_id: 1, name: 'Спорт', score: 100, completed_weight: 6, required_weight: 6,
    quota: 3, completed_count: 3, daily_required_count: 0, daily_completed_count: 0,
    weekly_quota: 3, weekly_completed_count: 3, weekly_weight: 2,
    weekly_effective_from: '2026-09-01', preferred_weekdays: [0, 2, 4], status: 'satisfied',
    ...overrides,
  }
}

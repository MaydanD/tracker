import { apiRequest } from './client'
import type { DayItem, HabitStreak, ProgressState } from './types'
import type { DailyStateRecord } from './dailyState'

export interface DashboardRead {
  today: string
  today_progress: ProgressState['day']
  week_progress: ProgressState['week']
  streaks: HabitStreak[]
  yesterday_state: DailyStateRecord | null
  today_items: DayItem[]
}

export function fetchDashboard(signal?: AbortSignal): Promise<DashboardRead> {
  return apiRequest<DashboardRead>('/api/dashboard', { signal })
}

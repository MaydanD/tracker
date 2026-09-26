import { apiRequest } from './client'
import type { DayItem, HabitStreak, ProgressState } from './types'
import type { DailyStateRecord } from './dailyState'
import type { OwlState } from './owl'
import type { RecordsPreview } from './records'

export interface DashboardRead {
  today: string
  today_progress: ProgressState['day']
  week_progress: ProgressState['week']
  streaks: HabitStreak[]
  yesterday_state: DailyStateRecord | null
  today_items: DayItem[]
  /** Stage 9: the single contextual Owl state, or null. */
  owl: OwlState | null
  /** Stage 11: a compact records preview, or null. */
  records: RecordsPreview | null
}

export function fetchDashboard(signal?: AbortSignal): Promise<DashboardRead> {
  return apiRequest<DashboardRead>('/api/dashboard', { signal })
}

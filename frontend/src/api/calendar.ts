import { apiRequest } from './client'
import type { DayItem, ProgressState } from './types'
import type { DailyStateRecord } from './dailyState'

export interface CalendarDaySummaryRead {
  entry_date: string
  daily_score: number | null
  completed_weight: number
  required_weight: number
  has_obligations: boolean
  has_daily_state: boolean
  mood: number | null
  is_future: boolean
}

export interface DayOverviewRead {
  entry_date: string
  today: string
  is_future: boolean
  progress: ProgressState['day']
  items: DayItem[]
  state: DailyStateRecord | null
}

export function fetchCalendarRange(
  start: string,
  end: string,
  signal?: AbortSignal,
): Promise<CalendarDaySummaryRead[]> {
  const query = new URLSearchParams({ start, end }).toString()
  return apiRequest<CalendarDaySummaryRead[]>(`/api/calendar?${query}`, { signal })
}

export function fetchDayOverview(
  date: string,
  signal?: AbortSignal,
): Promise<DayOverviewRead> {
  return apiRequest<DayOverviewRead>(`/api/days/${encodeURIComponent(date)}/overview`, { signal })
}

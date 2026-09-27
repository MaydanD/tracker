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
  area_scores: CalendarAreaScoreRead[]
  habit_scores: CalendarHabitScoreRead[]
}

interface CalendarDaySummaryApiRead extends Omit<CalendarDaySummaryRead, 'area_scores' | 'habit_scores'> {
  area_scores?: CalendarAreaScoreRead[] | null
  habit_scores?: CalendarHabitScoreRead[] | null
}

export interface CalendarAreaScoreRead {
  area_id: number
  name: string
  color: string
  score: number
}

export interface CalendarHabitScoreRead {
  habit_id: number
  name: string
  area_id: number
  area_name: string
  color: string
  score: number
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
  includeTrends = false,
): Promise<CalendarDaySummaryRead[]> {
  const params = new URLSearchParams({ start, end })
  if (includeTrends) params.set('include_trends', 'true')
  const query = params.toString()
  return apiRequest<CalendarDaySummaryApiRead[]>(`/api/calendar?${query}`, { signal }).then(
    (days) => days.map((day) => ({
      ...day,
      area_scores: day.area_scores ?? [],
      habit_scores: day.habit_scores ?? [],
    })),
  )
}

export function fetchDayOverview(
  date: string,
  signal?: AbortSignal,
): Promise<DayOverviewRead> {
  return apiRequest<DayOverviewRead>(`/api/days/${encodeURIComponent(date)}/overview`, { signal })
}

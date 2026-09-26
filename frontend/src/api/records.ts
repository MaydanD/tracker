/**
 * Stage 11 records & achievements contract.
 *
 * Every value is computed by the backend from the current history; the frontend
 * only formats and renders. There is no local counter: a record is a projection
 * of the data, not a stored score.
 */

import { apiRequest } from './client'

export type RecordUnit = 'days' | 'weeks'
export type AchievementCategory =
  | 'streak'
  | 'consistency'
  | 'tracking'
  | 'daily_state'
  | 'experiments'
  | 'insights'

export interface LongestStreak {
  habit_id: number
  name: string
  unit: RecordUnit
  current_streak: number
  best_streak: number
  best_start: string | null
  best_end: string | null
  archived: boolean
}

export interface BestDay {
  day: string
  score: number
  completed_weight: number
  required_weight: number
  ties: number
}

export interface BestWeek {
  week_start: string
  week_end: string
  score: number
  coverage: number | null
  observed_days: number
  obligation_days: number
  ties: number
}

export interface MostCompleted {
  day: string
  completed_count: number
  required_count: number
  ties: number
}

export interface Consistency {
  habit_id: number
  name: string
  archived: boolean
  period_start: string
  period_end: string
  done_days: number
  obligation_days: number
  ratio: number
}

export interface RecordsSummary {
  first_tracked_day: string | null
  tracked_days: number
  habit_completions: number
  experiments_created: number
  completed_experiments: number
  stable_insight_on: string | null
  well_supported_insight_on: string | null
}

export interface RecordSet {
  longest_streak: LongestStreak | null
  best_day: BestDay | null
  best_week: BestWeek | null
  most_completed: MostCompleted | null
  consistency: Consistency[]
}

export interface AchievementProgress {
  current: number
  target: number
}

export interface Achievement {
  key: string
  title: string
  description: string
  category: AchievementCategory
  achieved: boolean
  achieved_on: string | null
  progress: AchievementProgress
}

export interface RecordsRead {
  summary: RecordsSummary
  records: RecordSet
  achievements: Achievement[]
  recent_achievements: Achievement[]
  achieved_count: number
  total_count: number
}

/** The compact block embedded in the dashboard response. */
export interface RecordsPreview {
  longest_streak: LongestStreak | null
  latest_achievement: Achievement | null
  achieved_count: number
  total_count: number
}

export function fetchRecords(signal?: AbortSignal): Promise<RecordsRead> {
  return apiRequest<RecordsRead>('/api/records', { signal })
}

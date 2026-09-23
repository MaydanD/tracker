/** Habit endpoints, including configuration history. */

import { apiRequest } from './client'
import type { Habit, HabitInput, HabitVersion } from './types'

export interface FetchHabitsOptions {
  includeArchived?: boolean
  areaId?: number | null
  signal?: AbortSignal
}

export function fetchHabits(options: FetchHabitsOptions = {}): Promise<Habit[]> {
  const { includeArchived = false, areaId = null, signal } = options
  const query: string[] = []
  if (includeArchived) query.push('include_archived=true')
  if (areaId !== null) query.push(`area_id=${areaId}`)
  const suffix = query.length > 0 ? `?${query.join('&')}` : ''
  return apiRequest<Habit[]>(`/api/habits${suffix}`, { signal })
}

export function createHabit(input: HabitInput): Promise<Habit> {
  return apiRequest<Habit>('/api/habits', { method: 'POST', body: input })
}

/** Configuration edits replace the whole configuration: each save is versioned. */
export function updateHabit(habitId: number, input: HabitInput): Promise<Habit> {
  return apiRequest<Habit>(`/api/habits/${habitId}`, { method: 'PUT', body: input })
}

export function archiveHabit(habitId: number): Promise<Habit> {
  return apiRequest<Habit>(`/api/habits/${habitId}/archive`, { method: 'POST' })
}

export function unarchiveHabit(habitId: number): Promise<Habit> {
  return apiRequest<Habit>(`/api/habits/${habitId}/unarchive`, { method: 'POST' })
}

/** История настроек, newest first. */
export function fetchHabitVersions(
  habitId: number,
  signal?: AbortSignal,
): Promise<HabitVersion[]> {
  return apiRequest<HabitVersion[]>(`/api/habits/${habitId}/versions`, { signal })
}

/** The configuration that applied on a calendar date (YYYY-MM-DD). */
export function fetchHabitConfiguration(
  habitId: number,
  on: string,
  signal?: AbortSignal,
): Promise<HabitVersion> {
  return apiRequest<HabitVersion>(
    `/api/habits/${habitId}/configuration?on=${encodeURIComponent(on)}`,
    { signal },
  )
}

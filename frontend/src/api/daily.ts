/** Daily tracking endpoints: one calendar date, one habit's record on that date. */

import { ApiError, apiRequest } from './client'
import type { DailyEntry, DailyEntryInput, DayState } from './types'

/** The state of a calendar date: every habit that existed then, with its entry. */
export async function fetchDay(entryDate: string, signal?: AbortSignal): Promise<DayState> {
  const day = await apiRequest<DayState>(`/api/days/${encodeURIComponent(entryDate)}`, { signal })
  // A pre-scale server omits this metadata entirely. Treating that as null
  // would turn stored scales into completion controls and send invalid marks.
  if (day.items.some(item => item.value_type === undefined || item.value_labels === undefined)) {
    throw new ApiError('The running backend predates value scales.', {
      status: 409, code: 'outdated_tracking_api',
    })
  }
  return day
}

/**
 * Save (create or replace) one habit's record for a date.
 *
 * The request is a PUT because saving is idempotent: the same day is edited, not
 * duplicated. Fields that are left out (`null`) are cleared.
 */
export function saveDailyEntry(
  habitId: number,
  entryDate: string,
  input: DailyEntryInput,
): Promise<DailyEntry> {
  return apiRequest<DailyEntry>(
    `/api/habits/${habitId}/entries/${encodeURIComponent(entryDate)}`,
    { method: 'PUT', body: input },
  )
}

/**
 * Remove one habit's record for a date, returning the day to «нет отметки».
 *
 * This never marks the day as missed; it simply erases the observation.
 */
export function deleteDailyEntry(habitId: number, entryDate: string): Promise<void> {
  return apiRequest<void>(
    `/api/habits/${habitId}/entries/${encodeURIComponent(entryDate)}`,
    { method: 'DELETE' },
  )
}

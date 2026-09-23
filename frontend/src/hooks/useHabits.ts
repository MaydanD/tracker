import { useAsyncData } from './useAsyncData'
import { fetchHabits } from '../api/habits'
import type { Habit } from '../api/types'

export interface HabitsState {
  habits: Habit[]
  loading: boolean
  error: string | null
  reload: () => void
}

export interface HabitFilters {
  includeArchived: boolean
  areaId: number | null
}

/** Habits for the current filters (archive state and/or area). */
export function useHabits(filters: HabitFilters): HabitsState {
  const { includeArchived, areaId } = filters
  const { data, error, loading, reload } = useAsyncData(
    (signal) => fetchHabits({ includeArchived, areaId, signal }),
    [includeArchived, areaId],
  )

  return { habits: data ?? [], loading, error, reload }
}

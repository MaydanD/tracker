import { useAsyncData } from './useAsyncData'
import { fetchAreas } from '../api/areas'
import type { Area } from '../api/types'

export interface AreasState {
  areas: Area[]
  loading: boolean
  error: string | null
  reload: () => void
}

/** Active areas by default, archived ones on request. */
export function useAreas(includeArchived: boolean): AreasState {
  const { data, error, loading, reload } = useAsyncData(
    (signal) => fetchAreas({ includeArchived, signal }),
    [includeArchived],
  )

  return { areas: data ?? [], loading, error, reload }
}

import { apiRequest } from './client'
import type { ProgressState } from './types'

export function fetchProgress(on: string, signal?: AbortSignal): Promise<ProgressState> {
  return apiRequest<ProgressState>(`/api/progress/days/${encodeURIComponent(on)}`, { signal })
}

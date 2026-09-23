/** Area endpoints. */

import { apiRequest } from './client'
import type { Area, AreaInput, AreaUpdateInput } from './types'

export interface FetchAreasOptions {
  includeArchived?: boolean
  signal?: AbortSignal
}

export function fetchAreas(options: FetchAreasOptions = {}): Promise<Area[]> {
  const { includeArchived = false, signal } = options
  const query = includeArchived ? '?include_archived=true' : ''
  return apiRequest<Area[]>(`/api/areas${query}`, { signal })
}

export function createArea(input: AreaInput): Promise<Area> {
  return apiRequest<Area>('/api/areas', { method: 'POST', body: input })
}

export function updateArea(areaId: number, input: AreaUpdateInput): Promise<Area> {
  return apiRequest<Area>(`/api/areas/${areaId}`, { method: 'PATCH', body: input })
}

export function archiveArea(areaId: number): Promise<Area> {
  return apiRequest<Area>(`/api/areas/${areaId}/archive`, { method: 'POST' })
}

export function unarchiveArea(areaId: number): Promise<Area> {
  return apiRequest<Area>(`/api/areas/${areaId}/unarchive`, { method: 'POST' })
}

/** System endpoints: liveness and readiness. */

import { apiRequest } from './client'
import type { HealthResponse, ReadinessResponse } from './types'

/** `GET /api/health` — resolves whenever the backend process responds. */
export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest<HealthResponse>('/api/health', { signal })
}

/**
 * `GET /api/ready` — resolves for both outcomes: `status: 'ready'` or, when the
 * backend answers 503, `status: 'unavailable'` with `checks.database = 'error'`.
 * Only a transport failure rejects.
 */
export function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  return apiRequest<ReadinessResponse>('/api/ready', {
    signal,
    acceptStatuses: [503],
  })
}

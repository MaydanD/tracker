/** Response shapes returned by the Tracker API. */

/** `GET /api/health` — the backend process is alive. */
export interface HealthResponse {
  status: 'ok'
  app: string
  version: string
  environment: string
}

/** `GET /api/ready` — the backend can reach its database. */
export interface ReadinessResponse {
  status: 'ready' | 'unavailable'
  checks: Record<string, string>
}

/** Shared error envelope used by every failing API response. */
export interface ErrorResponse {
  error: {
    code: string
    message: string
    details?: Record<string, unknown> | null
  }
}

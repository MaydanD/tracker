import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiConnectionError, ApiError } from '../api/client'
import { fetchHealth, fetchReadiness } from '../api/system'
import type { HealthResponse, ReadinessResponse } from '../api/types'

export type BackendStatus =
  /** First check still in flight. */
  | 'checking'
  /** Backend answered and reported a working database. */
  | 'healthy'
  /** Backend answered but is not ready (database unavailable). */
  | 'degraded'
  /** Backend could not be reached at all. */
  | 'offline'

export interface BackendStatusState {
  status: BackendStatus
  health: HealthResponse | null
  readiness: ReadinessResponse | null
  error: string | null
  lastCheckedAt: Date | null
  refresh: () => void
}

export interface UseBackendStatusOptions {
  pollIntervalMs?: number
}

/**
 * When the backend is down, the Vite dev proxy answers 502/504 rather than
 * failing the fetch, so those statuses mean the same thing as an unreachable
 * backend to a user.
 */
const GATEWAY_UNAVAILABLE_STATUSES = new Set([502, 503, 504])

const UNREACHABLE_MESSAGE =
  'Cannot reach the Tracker backend. Start it with `python -m app` in backend/.'

/** Turn a failed check into a message a developer can act on. */
function describeFailure(cause: unknown): string {
  if (cause instanceof ApiConnectionError) return UNREACHABLE_MESSAGE
  if (cause instanceof ApiError) {
    return GATEWAY_UNAVAILABLE_STATUSES.has(cause.status)
      ? UNREACHABLE_MESSAGE
      : cause.message
  }
  return 'Unexpected error while checking the backend.'
}

/**
 * Poll `/api/health` and `/api/ready`.
 *
 * Plain React state is enough here: no cache, no server state library. A future
 * data-heavy screen can adopt one when it actually needs it.
 */
export function useBackendStatus(
  options: UseBackendStatusOptions = {},
): BackendStatusState {
  const { pollIntervalMs = 15000 } = options

  const [status, setStatus] = useState<BackendStatus>('checking')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastCheckedAt, setLastCheckedAt] = useState<Date | null>(null)
  const [refreshToken, setRefreshToken] = useState(0)

  const refresh = useCallback(() => setRefreshToken((token) => token + 1), [])

  // Keeps the latest check from being overwritten by a slower, older response.
  const checkId = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    let disposed = false

    async function check(): Promise<void> {
      const id = ++checkId.current
      try {
        const healthResponse = await fetchHealth(controller.signal)
        const readinessResponse = await fetchReadiness(controller.signal)
        if (disposed || id !== checkId.current) return

        setHealth(healthResponse)
        setReadiness(readinessResponse)
        setStatus(readinessResponse.status === 'ready' ? 'healthy' : 'degraded')
        setError(
          readinessResponse.status === 'ready'
            ? null
            : 'The backend is running but its database is unavailable.',
        )
        setLastCheckedAt(new Date())
      } catch (cause) {
        if (disposed || controller.signal.aborted) return
        const message = describeFailure(cause)
        setHealth(null)
        setReadiness(null)
        setStatus('offline')
        setError(message)
        setLastCheckedAt(new Date())
      }
    }

    void check()
    const interval = setInterval(() => void check(), pollIntervalMs)

    return () => {
      disposed = true
      controller.abort()
      clearInterval(interval)
    }
  }, [pollIntervalMs, refreshToken])

  return { status, health, readiness, error, lastCheckedAt, refresh }
}

import { vi } from 'vitest'

import type { HealthResponse, ReadinessResponse } from '../api/types'

/**
 * Minimal `Response` stand-in.
 *
 * jsdom does not implement fetch/Response, so tests stub the global and only
 * reproduce the parts the API client reads.
 */
export function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  } as unknown as Response
}

export function emptyResponse(status = 204): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => '',
  } as unknown as Response
}

export const HEALTHY_HEALTH: HealthResponse = {
  status: 'ok',
  app: 'Tracker',
  version: '0.1.0',
  environment: 'test',
}

export const READY: ReadinessResponse = {
  status: 'ready',
  checks: { database: 'ok' },
}

/** Stub the global fetch with a handler for every request. */
export function stubFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
) {
  const mock = vi.fn(handler)
  vi.stubGlobal('fetch', mock)
  return mock
}

/** Stub a healthy backend (health + readiness). */
export function stubHealthyBackend(options: {
  health?: HealthResponse
  readiness?: ReadinessResponse
} = {}) {
  const health = options.health ?? HEALTHY_HEALTH
  const readiness = options.readiness ?? READY

  return stubFetch(async (input) => {
    const url = String(input)
    if (url.endsWith('/api/health')) return jsonResponse(health)
    if (url.endsWith('/api/ready')) {
      return jsonResponse(readiness, readiness.status === 'ready' ? 200 : 503)
    }
    return jsonResponse({ error: { code: 'not_found', message: 'No route.' } }, 404)
  })
}

/** Stub a backend that cannot be reached at all. */
export function stubUnreachableBackend() {
  return stubFetch(async () => {
    throw new TypeError('Failed to fetch')
  })
}

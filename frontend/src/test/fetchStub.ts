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
  checks: { database: 'ok', migrations: 'ok' },
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

// ---------------------------------------------------------------------------
// Route-based stubbing
// ---------------------------------------------------------------------------

export interface StubRequest {
  method: string
  /** Path only, without query string: e.g. `/api/habits/3`. */
  path: string
  query: URLSearchParams
  /** Parsed JSON body, when the request sent one. */
  body: unknown
}

export type StubHandler = (request: StubRequest) => Response

function parseBody(body: unknown): unknown {
  if (typeof body !== 'string' || body === '') return null
  try {
    return JSON.parse(body)
  } catch {
    return null
  }
}

/**
 * Stub the API by route, keyed `"METHOD /path"` (query string excluded).
 * Unmatched requests answer 404 with the standard error envelope so a missing
 * stub fails loudly instead of looking like an empty list.
 */
export function stubApi(
  routes: Record<string, StubHandler>,
  options: { fallback?: StubHandler } = {},
) {
  return stubFetch(async (input, init) => {
    const url = new URL(String(input), 'http://localhost')
    const method = (init?.method ?? 'GET').toUpperCase()
    const request: StubRequest = {
      method,
      path: url.pathname,
      query: url.searchParams,
      body: parseBody(init?.body),
    }

    const handler = routes[`${method} ${url.pathname}`]
    if (handler) return handler(request)
    if (options.fallback) return options.fallback(request)

    return jsonResponse(
      { error: { code: 'not_found', message: `No stub for ${method} ${url.pathname}` } },
      404,
    )
  })
}

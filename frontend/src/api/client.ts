/**
 * The single place in the frontend that performs HTTP requests.
 * Components use the functions in `api/system.ts` (or future resource modules)
 * instead of calling `fetch` directly.
 */

import type { ErrorResponse } from './types'

const DEFAULT_TIMEOUT_MS = 5000

/**
 * Empty by default: in development Vite proxies `/api` to FastAPI, so relative
 * URLs keep the browser on a single origin. Set `VITE_API_BASE_URL` only when
 * the frontend and backend are served from different origins.
 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

/** A response arrived, but it reported a failure. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: Record<string, unknown> | null

  constructor(
    message: string,
    options: {
      status: number
      code: string
      details?: Record<string, unknown> | null
    },
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status
    this.code = options.code
    this.details = options.details
  }
}

/** No usable response arrived (backend down, DNS failure, timeout). */
export class ApiConnectionError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message)
    this.name = 'ApiConnectionError'
    this.cause = options?.cause
  }
}

export interface RequestOptions {
  signal?: AbortSignal
  timeoutMs?: number
  /**
   * Status codes that should resolve with the body instead of throwing.
   * Used for probes that report state through their status code (`/api/ready`
   * answers 503 when the database is unreachable).
   */
  acceptStatuses?: number[]
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as { error?: unknown }
  if (typeof candidate.error !== 'object' || candidate.error === null) return false
  const { code, message } = candidate.error as { code?: unknown; message?: unknown }
  return typeof code === 'string' && typeof message === 'string'
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text()
  if (text.length === 0) return null
  try {
    return JSON.parse(text)
  } catch {
    // A non-JSON body (proxy error page, HTML) is not an exception in itself.
    return null
  }
}

/** Perform an API request and parse the JSON response. */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { signal, timeoutMs = DEFAULT_TIMEOUT_MS, acceptStatuses = [] } = options
  const url = `${API_BASE_URL}${path}`

  const controller = new AbortController()
  const abortFromCaller = () => controller.abort()
  signal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

  try {
    let response: Response
    try {
      response = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      })
    } catch (cause) {
      if (signal?.aborted) throw cause
      throw new ApiConnectionError(`No response from ${url}.`, { cause })
    }

    const payload = await readJson(response)

    if (!response.ok && !acceptStatuses.includes(response.status)) {
      if (isErrorResponse(payload)) {
        throw new ApiError(payload.error.message, {
          status: response.status,
          code: payload.error.code,
          details: payload.error.details ?? null,
        })
      }
      throw new ApiError(
        `Request to ${path} failed with HTTP ${response.status}.`,
        { status: response.status, code: `http_${response.status}` },
      )
    }

    return payload as T
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', abortFromCaller)
  }
}

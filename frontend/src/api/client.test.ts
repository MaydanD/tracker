import { describe, expect, it, vi } from 'vitest'

import {
  jsonResponse,
  stubFetch,
  stubHealthyBackend,
} from '../test/fetchStub'
import { ApiConnectionError, ApiError, apiRequest } from './client'
import { fetchHealth, fetchReadiness } from './system'

describe('apiRequest', () => {
  it('returns the parsed JSON body of a successful request', async () => {
    stubHealthyBackend()

    const result = await fetchHealth()

    expect(result).toEqual({
      status: 'ok',
      app: 'Tracker',
      version: '0.1.0',
      environment: 'test',
    })
  })

  it('requests the API with the relative /api path', async () => {
    const fetchMock = stubHealthyBackend()

    await fetchHealth()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    )
  })

  it('raises ApiError with the code from the error envelope', async () => {
    stubFetch(async () =>
      jsonResponse(
        { error: { code: 'not_found', message: 'No route.' } },
        404,
      ),
    )

    const request = apiRequest('/api/missing')

    await expect(request).rejects.toBeInstanceOf(ApiError)
    await request.catch((error: ApiError) => {
      expect(error.status).toBe(404)
      expect(error.code).toBe('not_found')
      expect(error.message).toBe('No route.')
    })
  })

  it('falls back to an http_<status> code for non-envelope failures', async () => {
    stubFetch(async () => jsonResponse('<html>proxy error</html>', 502))

    await expect(apiRequest('/api/health')).rejects.toMatchObject({
      name: 'ApiError',
      status: 502,
      code: 'http_502',
    })
  })

  it('raises ApiConnectionError when nothing answers', async () => {
    stubFetch(async () => {
      throw new TypeError('Failed to fetch')
    })

    await expect(fetchHealth()).rejects.toBeInstanceOf(ApiConnectionError)
  })

  it('treats a 204 with no body as a successful empty response', async () => {
    const { emptyResponse } = await import('../test/fetchStub')
    stubFetch(async () => emptyResponse())

    await expect(apiRequest<null>('/api/thing')).resolves.toBeNull()
  })

  it('accepts listed statuses instead of throwing', async () => {
    stubFetch(async () =>
      jsonResponse({ status: 'unavailable', checks: { database: 'error' } }, 503),
    )

    await expect(fetchReadiness()).resolves.toEqual({
      status: 'unavailable',
      checks: { database: 'error' },
    })
  })

  it('propagates a caller abort without wrapping it', async () => {
    stubFetch(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          )
        }),
    )
    const controller = new AbortController()

    const request = fetchHealth(controller.signal)
    controller.abort()

    await expect(request).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('gives up on a slow request and reports a connection error', async () => {
    vi.useFakeTimers()
    try {
      stubFetch(
        (_input, init) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError')),
            )
          }),
      )

      const request = apiRequest('/api/ready', { timeoutMs: 100 })
      const assertion = expect(request).rejects.toBeInstanceOf(ApiConnectionError)
      await vi.advanceTimersByTimeAsync(200)

      await assertion
    } finally {
      vi.useRealTimers()
    }
  })
})

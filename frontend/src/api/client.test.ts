import { describe, expect, it, vi } from 'vitest'

import {
  jsonResponse,
  stubApi,
  stubFetch,
  stubHealthyBackend,
} from '../test/fetchStub'
import { createArea, fetchAreas } from './areas'
import { ApiConnectionError, ApiError, apiRequest, describeApiError } from './client'
import { createHabit } from './habits'
import { fetchHealth, fetchReadiness } from './system'

describe('apiRequest', () => {
  it('keeps English diagnostics but presents known errors in Russian', () => {
    const error = new ApiError('An active area with that name already exists.', {
      status: 409, code: 'area_name_conflict',
    })
    expect(describeApiError(error)).toBe('Активная сфера с таким названием уже существует.')
    expect(error.message).toBe('An active area with that name already exists.')
    expect(error.code).toBe('area_name_conflict')
  })

  it('does not expose unknown server or JavaScript messages', () => {
    expect(describeApiError(new ApiError('SQL failure: internal path', {
      status: 500, code: 'future_error',
    }))).toBe('Сервер не смог выполнить запрос. Попробуйте ещё раз.')
    expect(describeApiError(new Error('Failed to fetch')))
      .toBe('Произошла непредвиденная ошибка. Попробуйте ещё раз.')
  })

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

  it('sends a JSON body with the right method and content type', async () => {
    let seen: { method?: string; body?: unknown; contentType?: string } = {}
    stubApi({
      'POST /api/areas': (request) => {
        seen = { method: request.method, body: request.body }
        return jsonResponse({ id: 1, name: 'Health', color: '#4a7cc7' }, 201)
      },
    })

    await createArea({ name: 'Health', color: '#4a7cc7' })

    expect(seen.method).toBe('POST')
    expect(seen.body).toEqual({ name: 'Health', color: '#4a7cc7' })
  })

  it('builds list query strings from filters', async () => {
    const mock = stubFetch(async () => jsonResponse([]))

    await fetchAreas({ includeArchived: true })

    expect(mock).toHaveBeenCalledWith('/api/areas?include_archived=true', expect.anything())
  })

  it('surfaces domain errors from writes', async () => {
    stubApi({
      'POST /api/habits': () =>
        jsonResponse(
          {
            error: {
              code: 'invalid_quantity_unit',
              message: 'A quantity unit is required for habits that track quantities.',
            },
          },
          422,
        ),
    })

    await expect(
      createHabit({
        name: 'Reading',
        area_id: 1,
        weight: 1,
        tracking_mode: 'binary_quantity',
        schedule: { type: 'daily' },
      }),
    ).rejects.toMatchObject({
      name: 'ApiError',
      code: 'invalid_quantity_unit',
      status: 422,
    })
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

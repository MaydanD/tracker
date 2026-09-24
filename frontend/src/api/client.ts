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

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface RequestOptions {
  method?: HttpMethod
  /** JSON-serialised request body, when the method takes one. */
  body?: unknown
  signal?: AbortSignal
  timeoutMs?: number
  /**
   * Status codes that should resolve with the body instead of throwing.
   * Used for probes that report state through their status code (`/api/ready`
   * answers 503 when the database is unreachable).
   */
  acceptStatuses?: number[]
}

/** Shown whenever nothing answered at all (backend stopped, wrong port). */
export const CONNECTION_ERROR_MESSAGE =
  'Не удалось подключиться к серверу Tracker. Запустите его командой `python -m app` в папке backend/.'

/**
 * Turn any thrown value into a message worth showing a user.
 *
 * Keep the original error envelope for diagnostics. Only known codes and
 * structured field metadata are rendered; raw server messages may be English.
 */
export function describeApiError(error: unknown): string {
  if (error instanceof ApiConnectionError) return CONNECTION_ERROR_MESSAGE
  if (error instanceof ApiError) {
    const fields = fieldMessages(error)
    const message = ERROR_MESSAGES[error.code]
      ?? (error.status >= 500
        ? 'Сервер не смог выполнить запрос. Попробуйте ещё раз.'
        : 'Не удалось выполнить запрос. Проверьте данные и попробуйте ещё раз.')
    return fields.length > 0 ? `${message} ${fields.join(' ')}` : message
  }
  return 'Произошла непредвиденная ошибка. Попробуйте ещё раз.'
}

const ERROR_MESSAGES: Record<string, string> = {
  area_not_found: 'Сфера не найдена. Обновите страницу.',
  area_name_conflict: 'Активная сфера с таким названием уже существует.',
  area_has_active_habits: 'В этой сфере есть активные привычки. Сначала перенесите их в другую сферу или в архив.',
  area_archived: 'Эта сфера в архиве. Сначала восстановите сферу, затем сохраните или восстановите привычку.',
  invalid_area_name: 'Введите название сферы длиной от 1 до 80 символов.',
  invalid_area_color: 'Выберите цвет сферы в формате #4a7cc7.',
  habit_not_found: 'Привычка не найдена. Обновите страницу.',
  configuration_not_found: 'На выбранную дату у привычки ещё не было настроек.',
  invalid_habit_name: 'Введите название привычки длиной от 1 до 120 символов.',
  invalid_weight: 'Выберите важность: 1 — обычная, 2 — важная, 3 — ключевая.',
  invalid_tracking_mode: 'Выберите способ учёта: отметка выполнения или отметка и количество.',
  invalid_quantity_unit: 'Укажите единицу измерения длиной от 1 до 32 символов, например страницы, км или повторения.',
  invalid_schedule: 'Проверьте расписание: выберите дни недели или число выполнений от 1 до 7.',
  invalid_configuration_date: 'Изменение не может вступить в силу раньше текущей версии настроек.',
  invalid_configuration: 'Проверьте настройки привычки.',
  daily_entry_not_found: 'На эту дату отметки нет.',
  invalid_entry_status: 'Неизвестное состояние отметки. Обновите страницу.',
  future_entry_not_allowed: 'На будущую дату можно только запланировать пропуск.',
  skip_reason_required: 'Укажите причину пропуска.',
  skip_reason_not_allowed: 'Причину пропуска можно указать только для осознанного пропуска.',
  invalid_skip_reason: 'Причина пропуска слишком длинная (не более 200 символов).',
  invalid_note: 'Заметка слишком длинная (не более 500 символов).',
  invalid_quantity: 'Проверьте количество: число не может быть отрицательным, слишком большим или иметь слишком много знаков после запятой.',
  quantity_not_allowed: 'У этой привычки количество не ведётся.',
  quantity_decimal_not_allowed: 'Для этой привычки допустимы только целые значения.',
  validation_error: 'Проверьте заполненные поля.',
  database_unavailable: 'База данных недоступна. Попробуйте ещё раз.',
  service_unavailable: 'Сервис временно недоступен. Попробуйте ещё раз.',
  internal_error: 'На сервере произошла ошибка. Попробуйте ещё раз.',
  not_found: 'Запрошенные данные не найдены.',
  conflict: 'Данные изменились. Обновите страницу и попробуйте ещё раз.',
  bad_request: 'Не удалось обработать запрос. Проверьте введённые данные.',
  unauthorized: 'Доступ к серверу не разрешён.',
  forbidden: 'Недостаточно прав для этого действия.',
  method_not_allowed: 'Это действие недоступно.',
}

const FIELD_LABELS: Record<string, string> = {
  name: 'Название', description: 'Описание', color: 'Цвет', area_id: 'Сфера',
  weight: 'Важность', tracking_mode: 'Способ учёта', quantity_unit: 'Единица измерения',
  quantity_allows_decimal: 'Дробные значения', schedule: 'Расписание',
  type: 'Тип расписания', weekdays: 'Дни недели', times_per_week: 'Выполнений в неделю',
  on: 'Дата', include_archived: 'Показывать архивные',
  status: 'Состояние', quantity_value: 'Количество', skip_reason: 'Причина пропуска',
  note: 'Заметка', entry_date: 'Дата',
}

function fieldMessages(error: ApiError): string[] {
  const errors = error.details?.['errors']
  if (!Array.isArray(errors)) return []
  return errors
    .slice(0, 5)
    .map((entry) => {
      if (typeof entry !== 'object' || entry === null) return ''
      const { loc, type, ctx } = entry as { loc?: unknown; type?: string; ctx?: Record<string, unknown> }
      const field = Array.isArray(loc)
        ? loc.filter((part): part is string => typeof part === 'string' && part in FIELD_LABELS).at(-1)
        : undefined
      const label = field ? FIELD_LABELS[field] : 'Данные'
      if (type === 'missing') return `${label}: заполните поле.`
      if (type === 'string_too_long' && typeof ctx?.max_length === 'number') {
        return `${label}: не более ${ctx.max_length} символов.`
      }
      if (type === 'string_too_short' && typeof ctx?.min_length === 'number') {
        return `${label}: не менее ${ctx.min_length} символов.`
      }
      if (type === 'int_parsing' || type === 'int_type' || type === 'int_from_float') {
        return `${label}: введите целое число.`
      }
      return `${label}: проверьте значение.`
    })
    .filter((message) => message.length > 0)
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
  const {
    method = 'GET',
    body,
    signal,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    acceptStatuses = [],
  } = options
  const url = `${API_BASE_URL}${path}`

  const controller = new AbortController()
  const abortFromCaller = () => controller.abort()
  signal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

  try {
    // Content-Type is only sent with a body, so read-only requests stay simple.
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (body !== undefined) headers['Content-Type'] = 'application/json'

    let response: Response
    try {
      response = await fetch(url, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
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

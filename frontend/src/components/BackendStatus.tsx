import { API_BASE_URL } from '../api/client'
import type { ReadinessResponse } from '../api/types'
import type {
  BackendStatus as BackendStatusValue,
  BackendStatusState,
} from '../hooks/useBackendStatus'

const STATUS_LABELS: Record<BackendStatusValue, string> = {
  checking: 'Проверка…',
  healthy: 'Подключено',
  degraded: 'База данных недоступна',
  offline: 'Сервер недоступен',
}

function checkLabel(value: string | undefined): string {
  if (value === undefined) return '—'
  return ({ ok: 'В порядке', error: 'Ошибка', pending: 'Ожидает обновления' } as Record<string, string>)[value] ?? 'Неизвестно'
}

function environmentLabel(value: string): string {
  return ({ development: 'разработка', test: 'тестирование', production: 'рабочий режим' } as Record<string, string>)[value] ?? 'другой режим'
}

/** A pending migration is a distinct problem from an unreachable database. */
function statusLabel(
  status: BackendStatusValue,
  readiness: ReadinessResponse | null,
): string {
  if (status === 'degraded' && readiness?.checks.migrations === 'pending') {
    return 'Требуется обновление базы'
  }
  return STATUS_LABELS[status]
}

export interface BackendStatusProps {
  backend: BackendStatusState
}

/**
 * Always-visible development state: the shell must never look healthy while the
 * backend is down or its database is missing.
 */
export function BackendStatus({ backend }: BackendStatusProps) {
  const { status, health, readiness, error, lastCheckedAt, refresh } = backend

  return (
    <div className="status" data-status={status}>
      <div className="status__row">
        <span className={`status__dot status__dot--${status}`} aria-hidden="true" />
        <span className="status__label">{statusLabel(status, readiness)}</span>
        <button type="button" className="status__refresh" onClick={refresh}>
          Проверить снова
        </button>
      </div>

      <dl className="status__details">
        <div>
          <dt>API</dt>
          <dd>{API_BASE_URL === '' ? '/api (через прокси)' : API_BASE_URL}</dd>
        </div>
        <div>
          <dt>Приложение</dt>
          <dd>
            {health ? `${health.app} ${health.version} · ${environmentLabel(health.environment)}` : '—'}
          </dd>
        </div>
        <div>
          <dt>База данных</dt>
          <dd>{checkLabel(readiness?.checks.database)}</dd>
        </div>
        <div>
          <dt>Схема базы</dt>
          <dd>{checkLabel(readiness?.checks.migrations)}</dd>
        </div>
        <div>
          <dt>Проверено</dt>
          <dd>{lastCheckedAt ? lastCheckedAt.toLocaleTimeString('ru-RU') : '—'}</dd>
        </div>
      </dl>

      {error ? (
        <p className="status__error" role="status">
          {error}
        </p>
      ) : null}
    </div>
  )
}

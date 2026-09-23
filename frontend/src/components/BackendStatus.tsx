import { API_BASE_URL } from '../api/client'
import type {
  BackendStatus as BackendStatusValue,
  BackendStatusState,
} from '../hooks/useBackendStatus'

const STATUS_LABELS: Record<BackendStatusValue, string> = {
  checking: 'Checking…',
  healthy: 'Connected',
  degraded: 'Database unavailable',
  offline: 'Backend unreachable',
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
        <span className="status__label">{STATUS_LABELS[status]}</span>
        <button type="button" className="status__refresh" onClick={refresh}>
          Recheck
        </button>
      </div>

      <dl className="status__details">
        <div>
          <dt>API</dt>
          <dd>{API_BASE_URL === '' ? '/api (proxied)' : API_BASE_URL}</dd>
        </div>
        <div>
          <dt>App</dt>
          <dd>
            {health ? `${health.app} ${health.version} · ${health.environment}` : '—'}
          </dd>
        </div>
        <div>
          <dt>Database</dt>
          <dd>{readiness?.checks.database ?? '—'}</dd>
        </div>
        <div>
          <dt>Checked</dt>
          <dd>{lastCheckedAt ? lastCheckedAt.toLocaleTimeString() : '—'}</dd>
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

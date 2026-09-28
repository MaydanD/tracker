import { useEffect, useState } from 'react'
import { telegramAction, updateBackupSettings, type BackupStatus } from '../api/backup'
import { useTelegramAutoCheck } from '../hooks/useTelegramAutoCheck'

// ─── Status badge ────────────────────────────────────────────────────────────

type BadgeVariant = 'connected' | 'error' | 'unchecked' | 'unconfigured' | 'checking'

interface BadgeProps {
  variant: BadgeVariant
  label: string
  verifiedAt?: string | null
  /** Transient error from the last explicit action (check / send). */
  actionError?: string | null
  /** A background auto-check is running while the badge stays green. */
  backgroundChecking?: boolean
}

function StatusBadge({ variant, label, verifiedAt, actionError, backgroundChecking }: BadgeProps) {
  return (
    <div>
      <p className={`tg-status tg-status--${variant}`}>
        {/* Dot is decorative — the text label carries the meaning for screen readers. */}
        <span className="tg-status__dot" aria-hidden="true" />
        <span className="tg-status__label">{label}</span>
        {variant === 'connected' && verifiedAt && (
          <span className="tg-status__verified-at">
            · Проверено: {new Date(verifiedAt).toLocaleString('ru-RU', {
              day: '2-digit', month: '2-digit', year: 'numeric',
              hour: '2-digit', minute: '2-digit',
            })}
          </span>
        )}
        {/* Sits inline in the badge row, so the card cannot reflow when a
            background check starts or finishes. */}
        {backgroundChecking && <span className="tg-status__checking">· Проверяем…</span>}
      </p>
      {/* Show the transient action error only when the persistent state is still
          "connected" — so a temporary network hiccup doesn't look like the
          connection was lost entirely.  The wording stays operation-neutral:
          `last_error` can come from a check *or* from a backup send. */}
      {actionError && variant === 'connected' && (
        <p className="tg-status__action-error" role="alert">
          Последняя операция Telegram завершилась с ошибкой: {actionError}
        </p>
      )}
    </div>
  )
}

// ─── Derive badge props from BackupStatus ────────────────────────────────────

function resolveBadge(
  status: BackupStatus,
  checking: boolean,
  actionError: string | null,
  backgroundChecking: boolean,
): BadgeProps {
  if (!status.configured) {
    return { variant: 'unconfigured', label: 'Не настроено' }
  }
  if (checking) {
    return { variant: 'checking', label: 'Проверяем подключение…' }
  }
  if (backgroundChecking) {
    // A background check on a card that is already known-good keeps its green
    // badge; the running check is a small note next to it.
    return { variant: 'connected', label: 'Подключено', verifiedAt: status.telegram_verified_at,
             actionError: actionError ?? (status.last_error ?? null), backgroundChecking: true }
  }
  // An explicit last_error from the backend AND no verified history → real error.
  // If we have verified history, show "connected" with transient action error below.
  if (status.last_error && !status.verified) {
    return { variant: 'error', label: 'Ошибка подключения', actionError: status.last_error }
  }
  if (status.connected || status.verified) {
    // A transient actionError (frontend-local) is shown as a sub-note, not replacing the badge.
    return {
      variant: 'connected',
      label: 'Подключено',
      verifiedAt: status.telegram_verified_at,
      actionError: actionError ?? (status.last_error ?? null),
    }
  }
  return { variant: 'unchecked', label: 'Настроено, подключение не проверено' }
}

// ─── Main component ───────────────────────────────────────────────────────────

export function TelegramBackupSettings({ status, disabled, onBusy, onStatusUpdate }: {
  status: BackupStatus
  disabled: boolean
  onBusy: (busy: boolean) => void
  onStatusUpdate?: (updated: BackupStatus) => void
}) {
  const [token, setToken] = useState('')
  const [chat, setChat] = useState(status.chat_id)
  const [auto, setAuto] = useState(status.auto_enabled)
  const [busy, setBusy] = useState<'save' | 'check' | 'send' | null>(null)
  /** Transient error from the last explicit user action — NOT persisted. */
  const [actionError, setActionError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  /** A background auto-check is in flight (drives the neutral «Проверяем…»). */
  const [autoChecking, setAutoChecking] = useState(false)

  useEffect(() => {
    setChat(status.chat_id)
    setAuto(status.auto_enabled)
  }, [status.chat_id, status.auto_enabled])

  const dirty = Boolean(token) || chat !== status.chat_id || auto !== status.auto_enabled
  const blocked = disabled || Boolean(busy) || status.in_progress

  // Auto-check fires once on mount when credentials are configured but stale.
  useTelegramAutoCheck(status, (updated) => {
    onStatusUpdate?.(updated)
    // Clear any stale action error when auto-check succeeds silently.
    if (updated.verified) setActionError(null)
  }, setAutoChecking)

  const checking = busy === 'check' || status.in_progress
  // While a background check runs on an unverified card, the badge itself is the
  // neutral «Проверяем подключение…»; on a verified card the green badge stays
  // and the running check is only a note beside it.
  const badge = resolveBadge(status, checking || (autoChecking && !status.verified), actionError,
    autoChecking && !checking && (status.connected || status.verified))

  async function run(action: 'save' | 'check' | 'send') {
    setBusy(action)
    onBusy(true)
    setActionError(null)
    setSuccessMessage(null)
    try {
      if (action === 'save') {
        const updated = await updateBackupSettings({
          ...(token ? { token } : {}),
          chat_id: chat.trim(),
          auto_enabled: auto,
        })
        setToken('')
        setSuccessMessage('Настройки сохранены.')
        onStatusUpdate?.(updated)
        window.dispatchEvent(new Event('tracker:backup-updated'))
      } else {
        const updated = await telegramAction(action)
        onStatusUpdate?.(updated)
        setSuccessMessage(
          action === 'check'
            ? 'Подключено. Личный чат доступен.'
            : 'Резервная копия отправлена в Telegram.',
        )
      }
    } catch (cause) {
      // Store as transient action error — does NOT replace persistent verified state.
      setActionError(cause instanceof Error ? cause.message : 'Не удалось выполнить операцию.')
      window.dispatchEvent(new Event('tracker:backup-updated'))
    } finally {
      setBusy(null)
      onBusy(false)
    }
  }

  return (
    <section
      className="telegram-settings"
      aria-labelledby="telegram-title"
      aria-busy={Boolean(busy) || status.in_progress}
    >
      <h3 id="telegram-title">Telegram</h3>
      <p>
        Создайте бота через @BotFather, начните с ним личный диалог и укажите
        идентификатор своего чата.
      </p>

      <StatusBadge {...badge} />

      <label>
        Токен бота
        <input
          type="password"
          autoComplete="new-password"
          value={token}
          disabled={blocked}
          placeholder={status.token_saved ? 'Токен сохранён' : 'Введите токен бота'}
          onChange={event => setToken(event.target.value)}
        />
      </label>
      <label>
        Идентификатор чата
        <input
          inputMode="numeric"
          value={chat}
          disabled={blocked}
          onChange={event => setChat(event.target.value)}
        />
      </label>
      <label className="telegram-settings__toggle">
        <input
          type="checkbox"
          checked={auto}
          disabled={blocked}
          onChange={event => setAuto(event.target.checked)}
        />
        Автоматически отправлять ежемесячную резервную копию
      </label>
      <p>
        Автоматическая отправка проверяется при запуске и открытии приложения.
        После ошибки следующая попытка — не раньше чем через сутки.
      </p>

      <div className="toolbar">
        <button
          className="button"
          disabled={blocked || !dirty}
          onClick={() => void run('save')}
        >
          Сохранить настройки
        </button>
        <button
          className="button"
          disabled={blocked || dirty || !status.configured}
          onClick={() => void run('check')}
        >
          Проверить подключение
        </button>
        <button
          className="button"
          disabled={blocked || dirty || !status.configured}
          onClick={() => void run('send')}
        >
          Отправить резервную копию сейчас
        </button>
      </div>

      {dirty && <p>Сохраните изменения перед проверкой и отправкой.</p>}

      {(busy || status.in_progress) && (
        <p role="status">
          {busy === 'save'
            ? 'Сохраняем настройки…'
            : busy === 'check'
              ? 'Проверяем подключение…'
              : 'Создаём и отправляем резервную копию…'}
        </p>
      )}

      {/* Transient action error when there is NO persistent verified history — full alert. */}
      {actionError && !status.verified && (
        <p role="alert">{actionError}</p>
      )}

      {/* Backend-persisted error when never verified — full alert. */}
      {!actionError && status.last_error && !status.verified && (
        <p role="alert">{status.last_error}</p>
      )}

      {successMessage && <p role="status">{successMessage}</p>}

      {status.last_error && status.auto_enabled && status.next_auto_attempt_at && (
        <p>
          Следующая автоматическая попытка возможна после{' '}
          {new Date(status.next_auto_attempt_at).toLocaleString('ru-RU')} при
          открытии приложения. Можно повторить отправку вручную.
        </p>
      )}
    </section>
  )
}

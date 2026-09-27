import { useState } from 'react'

import { downloadData } from '../api/backup'
import { ErrorBanner } from './Feedback'

/** Remembers that a backup was already taken on a given local date. */
const DONE_KEY = 'tracker:backup-done'
/** Remembers that the offer was postponed for the current session/date. */
const POSTPONED_KEY = 'tracker:backup-postponed'

function read(storage: Storage, key: string): string | null {
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

function write(storage: Storage, key: string, value: string): void {
  try {
    storage.setItem(key, value)
  } catch {
    /* Storage may be unavailable; the reminder simply reappears. */
  }
}

export interface BackupReminderProps {
  /**
   * The server's local date (`YYYY-MM-DD`). Using the server date keeps the
   * "first of the month" rule consistent with every other screen and testable.
   */
  today: string
}

/**
 * A noticeable but non-blocking nudge on the 1st of the month to save a backup.
 *
 * It reuses the existing official export (`/api/backup`), so there is no second
 * mechanism. Once a backup succeeds it is remembered locally (keyed by date), so
 * it will not ask again that day or that month; if the user postpones it, it
 * stays quiet for the rest of the session. It reappears the next month.
 */
export function BackupReminder({ today }: BackupReminderProps) {
  const isFirstOfMonth = today.slice(8, 10) === '01'
  const [hidden, setHidden] = useState(() =>
    read(window.localStorage, DONE_KEY) === today
    || read(window.sessionStorage, POSTPONED_KEY) === today,
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isFirstOfMonth || hidden) return null

  async function handleBackup() {
    setBusy(true)
    setError(null)
    try {
      await downloadData('backup')
      write(window.localStorage, DONE_KEY, today)
      setHidden(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось сохранить резервную копию.')
    } finally {
      setBusy(false)
    }
  }

  function handleLater() {
    write(window.sessionStorage, POSTPONED_KEY, today)
    setHidden(true)
  }

  return (
    <>
      <section className="backup-reminder" aria-label="Резервная копия">
        <div className="backup-reminder__body">
          <p className="backup-reminder__title">
            Начало месяца — самое время сохранить резервную копию.
          </p>
          <p className="backup-reminder__text">
            Копия останется на вашем компьютере и сохранит многолетнюю историю.
          </p>
        </div>
        <div className="backup-reminder__actions">
          <button
            type="button"
            className="button button--primary"
            onClick={() => void handleBackup()}
            disabled={busy}
          >
            {busy ? 'Готовим файл…' : 'Сделать backup'}
          </button>
          <button type="button" className="button" onClick={handleLater} disabled={busy}>
            Позже
          </button>
        </div>
      </section>
      <ErrorBanner message={error} />
    </>
  )
}

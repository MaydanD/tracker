/**
 * Auto-check: fires a background `POST /api/backup/telegram/check` when
 * Telegram credentials are configured but the last verification is absent
 * or older than TTL_MS.
 *
 * Rules to prevent check storms:
 * - At most one attempt per mounted instance (`attempted`), so re-renders and
 *   changing props can never queue another request.
 * - At most one request in flight per page (`checkInFlight`, module state),
 *   so two mounted cards — or React's StrictMode double-mount — never fire in
 *   parallel.
 * - Skips if credentials are not configured, if the page is mid-operation, or
 *   if the last verification is still fresh.
 * - Never retries automatically on failure — the user can press the button.
 * - A result arriving after unmount is dropped, so a late response cannot
 *   write state into a page the user has already left.
 */
import { useEffect, useRef } from 'react'
import { telegramAction, type BackupStatus } from '../api/backup'

/** 4 hours — fresh enough to skip auto-check on a second page load. */
const TTL_MS = 4 * 60 * 60 * 1000

/** Module-level guard so that re-renders never start a second in-flight check. */
let checkInFlight = false

/**
 * Test-only escape hatch: the in-flight guard survives individual mounts, so
 * tests that exercise consecutive mounts must reset it explicitly.
 */
export function resetTelegramAutoCheck(): void {
  checkInFlight = false
}

export function useTelegramAutoCheck(
  status: BackupStatus | null,
  onResult: (updated: BackupStatus) => void,
  /** Lets the UI show that a background check is running, without polling. */
  onChecking?: (checking: boolean) => void,
): void {
  // Track whether a check was already attempted this component lifetime so
  // we never fire more than once per mount, even with React StrictMode.
  const attempted = useRef(false)
  const alive = useRef(true)
  // Keep the newest callbacks without re-running the effect that fires the check.
  const callback = useRef(onResult)
  callback.current = onResult
  const checkingCallback = useRef(onChecking)
  checkingCallback.current = onChecking

  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])

  useEffect(() => {
    if (attempted.current) return
    if (!status) return
    if (!status.configured) return
    if (status.in_progress) return
    // Skip if recently verified. A missing or unparsable timestamp counts as
    // stale; a future one (clock skew) counts as fresh.
    if (status.telegram_verified_at) {
      const age = Date.now() - new Date(status.telegram_verified_at).getTime()
      if (Number.isFinite(age) && age < TTL_MS) return
    }

    attempted.current = true
    // A parallel check is already running (another card, or StrictMode's
    // remount): let it report instead of duplicating the request.
    if (checkInFlight) return
    checkInFlight = true

    checkingCallback.current?.(true)
    telegramAction('check')
      .then(updated => { if (alive.current) callback.current(updated) })
      .catch(() => { /* silent — the persisted status stays, the user can retry */ })
      .finally(() => {
        checkInFlight = false
        // Never flip a state on a page the user has already left.
        if (alive.current) checkingCallback.current?.(false)
      })
  // We only want to run this once when status first arrives — the eslint rule
  // cannot see that `attempted`/`alive`/`callback` are refs, not state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.configured, status?.telegram_verified_at, status?.in_progress])
}

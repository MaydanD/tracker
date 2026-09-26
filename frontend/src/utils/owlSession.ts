/**
 * Stage 9 Owl anti-spam: local, session-scoped UX state. No database.
 *
 * * A dismissed banner stays dismissed for its stable `fingerprint` for the rest
 *   of the browser session, so navigation or a re-render cannot resurrect it.
 * * At most one aggressive message is shown per cooldown window; a second one is
 *   downgraded to its non-sarcastic caption by the caller.
 *
 * A `Storage`-shaped object is injected so this is testable without a browser.
 */

export interface KeyValueStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export const SARCASM_COOLDOWN_MS = 24 * 60 * 60 * 1000

const DISMISS_PREFIX = 'tracker.owl.dismissed.'
const SARCASM_UNTIL_KEY = 'tracker.owl.sarcasm.until'

function defaultStorage(): KeyValueStorage | null {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null
  } catch {
    return null
  }
}

export function isDismissed(
  fingerprint: string,
  storage: KeyValueStorage | null = defaultStorage(),
): boolean {
  if (storage === null || fingerprint === '') return false
  return storage.getItem(DISMISS_PREFIX + fingerprint) === '1'
}

export function dismiss(
  fingerprint: string,
  storage: KeyValueStorage | null = defaultStorage(),
): void {
  if (storage === null || fingerprint === '') return
  storage.setItem(DISMISS_PREFIX + fingerprint, '1')
}

export function sarcasmCoolingDown(
  now: number = Date.now(),
  storage: KeyValueStorage | null = defaultStorage(),
): boolean {
  if (storage === null) return false
  const raw = storage.getItem(SARCASM_UNTIL_KEY)
  if (raw === null) return false
  const until = Number(raw)
  return Number.isFinite(until) && now < until
}

export function recordSarcasm(
  now: number = Date.now(),
  storage: KeyValueStorage | null = defaultStorage(),
): void {
  if (storage === null) return
  storage.setItem(SARCASM_UNTIL_KEY, String(now + SARCASM_COOLDOWN_MS))
}

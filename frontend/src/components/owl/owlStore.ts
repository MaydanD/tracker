/**
 * A tiny, dependency-free store for the *current* Owl state.
 *
 * The contextual Owl already travels on the dashboard, insights and experiments
 * responses. The header logo needs one value that is available on every screen
 * without a second analytics engine: whichever page last loaded publishes its
 * Owl here, and the header reads it. The store owns no product logic — it only
 * keeps the latest backend-chosen state and lets the header refresh itself from
 * the dashboard when nothing has published a value yet.
 */

import { fetchDashboard } from '../../api/dashboard'
import type { OwlState } from '../../api/owl'

type Listener = () => void

const listeners = new Set<Listener>()
let current: OwlState | null = null
let loaded = false
let inflight = false

/** Snapshot for `useSyncExternalStore`: a stable reference per value. */
export function getOwlSnapshot(): OwlState | null {
  return current
}

export function subscribeOwl(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Publish the Owl a page just received. No-op when it is unchanged. */
export function setOwl(owl: OwlState | null): void {
  const unchanged = (current?.fingerprint ?? null) === (owl?.fingerprint ?? null)
  if (unchanged && loaded) return
  current = owl
  loaded = true
  for (const listener of listeners) listener()
}

/**
 * Fetch the dashboard's Owl in the background. Used when no page has published
 * a state yet (for example a screen that carries no Owl of its own).
 */
export function refreshOwl(): void {
  if (inflight) return
  inflight = true
  fetchDashboard()
    .then((data) => setOwl(data.owl))
    .catch(() => {
      /* A failed refresh must never surface as a page error. */
    })
    .finally(() => {
      inflight = false
    })
}

/** Test helper: forget any published state between cases. */
export function resetOwlStore(): void {
  current = null
  loaded = false
  inflight = false
  listeners.clear()
}

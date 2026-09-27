import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * 5-second "grace period" countdown for a filled check-in card.
 *
 * Lifecycle:
 *   idle → counting (after a successful save) → done (auto or by confirmNow())
 *
 * "done" means the card should move to the "already recorded" section.
 *
 * Key safety guarantees:
 * - No setState after unmount: all state mutations are gated by `mounted.current`.
 * - Stale-frame guard: every start/reset increments a generation counter.
 *   Save-response versions are guarded by the card persistence layer.
 * - Changing the value while counting resets the countdown (generation is
 *   incremented, old rAF loop drops itself on the next tick).
 * - Day change from outside: call `reset()` to return immediately to idle.
 * - Timer uses requestAnimationFrame + a start timestamp (not setInterval),
 *   so only one active loop exists per card at any time and it is always
 *   cleaned up on the next frame after the component unmounts or resets.
 */

export type CardTimerState = 'idle' | 'counting' | 'done'

export interface UseCardTimerResult {
  /** Current phase of the card. */
  timerState: CardTimerState
  /** 0 → 1 progress, only meaningful while `timerState === 'counting'`. */
  progress: number
  /**
   * Call after a successful API save.
   * Starts (or restarts) the 5-second countdown.
   */
  startCountdown: () => void
  /**
   * Immediately confirm — skip waiting; card moves to "done" at once.
   */
  confirmNow: () => void
  /**
   * Return to idle (e.g. day changed, value cleared).
   * Cancels any running countdown.
   */
  reset: () => void
}

const DURATION_MS = 5_000

export function useCardTimer(): UseCardTimerResult {
  const [timerState, setTimerState] = useState<CardTimerState>('idle')
  const [progress, setProgress] = useState(0)

  // Ref-based flags that are safe to read inside rAF callbacks.
  const mounted = useRef(true)
  const generation = useRef(0)   // incremented on every startCountdown / reset
  const rafId = useRef<number | null>(null)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      ++generation.current
      // Cancel any pending frame so the loop dies with the component.
      if (rafId.current !== null) {
        cancelAnimationFrame(rafId.current)
        rafId.current = null
      }
    }
  }, [])

  /** Cancel the current rAF loop without touching React state. */
  const cancelLoop = useCallback(() => {
    if (rafId.current !== null) {
      cancelAnimationFrame(rafId.current)
      rafId.current = null
    }
  }, [])

  const startCountdown = useCallback(() => {
    if (!mounted.current) return
    cancelLoop()

    // Bump generation so any stale rAF iteration self-terminates.
    const gen = ++generation.current
    const startAt = performance.now()

    if (mounted.current) {
      setTimerState('counting')
      setProgress(0)
    }

    function tick(now: number) {
      // Self-terminate if stale or unmounted.
      if (!mounted.current || generation.current !== gen) return

      const elapsed = now - startAt
      const frac = Math.min(elapsed / DURATION_MS, 1)

      setProgress(frac)

      if (frac >= 1) {
        rafId.current = null
        setTimerState('done')
        return
      }

      rafId.current = requestAnimationFrame(tick)
    }

    rafId.current = requestAnimationFrame(tick)
  }, [cancelLoop])

  const confirmNow = useCallback(() => {
    cancelLoop()
    ++generation.current
    if (mounted.current) {
      setProgress(1)
      setTimerState('done')
    }
  }, [cancelLoop])

  const reset = useCallback(() => {
    cancelLoop()
    ++generation.current
    if (mounted.current) {
      setProgress(0)
      setTimerState('idle')
    }
  }, [cancelLoop])

  return { timerState, progress, startCountdown, confirmNow, reset }
}

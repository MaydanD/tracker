import { useCallback, useEffect, useRef, useState, type FocusEvent } from 'react'
import { useCardTimer } from './useCardTimer'

/**
 * Readiness belongs to a card, independently of the shared persistence queue.
 *
 * The 5-second countdown means exactly one thing: the user has stopped
 * interacting with the card, the newest value is stored, and the user has left
 * the card. Clicking a control inside a card — a status button, a scale value,
 * a toggle, a field, the clear button, the lock or «ОК» — is *interaction*,
 * never departure, so it can neither arm nor disarm the countdown on its own.
 *
 * Engagement is tracked from the two sources a click cannot fake:
 *
 * - `pointerInside` — the pointer is over this card. It is set by a press on
 *   the card and cleared when the pointer actually leaves it (or when the user
 *   presses somewhere else), so pressing a status button keeps the card engaged
 *   until the pointer moves away.
 * - `typing` — a field of this card is in use by the user. It survives moving
 *   between the card's own controls and ends when focus leaves the card or the
 *   user presses somewhere else, exactly as before.
 *
 * Rendering, manual eligibility and countdown eligibility are three distinct
 * questions, answered by three distinct values:
 *
 * - `showOk` — *should the «ОК» control be on screen at all?* It depends only
 *   on the card holding a stored value (`stored`), still holding a value worth
 *   completing (`filled`) and not already being recorded (`completed`). It
 *   deliberately does NOT look at `revision === savedRevision`: a write being
 *   in flight must never unmount the button, or its geometry would flicker on
 *   every autosave.
 * - `canConfirm` — *may the user complete the card by hand right now?* This is
 *   the stricter condition: the newest revision must also be stored and there
 *   must be no error, so a click can never complete stale data. While false
 *   the button stays on screen, disabled.
 * - `canCountdown` — *should the 5-second auto-confirm run right now?* The
 *   strictest: additionally the user must have left the card (no pointer
 *   inside, no field in use) and the card must not be pinned by the lock.
 *
 * Interacting with a field therefore stops the countdown without ever hiding
 * or unmounting the button.
 *
 * A hand-confirm is terminal for the revision it was made on
 * ----------------------------------------------------------
 * The commit that puts an enabled «ОК» on screen happens *before* the readiness
 * effect below flushes, so a click can land in that window. That effect begins
 * with `reset()`, which would then undo a completion the user has already made
 * and can already see. `confirmed` records the revision that was completed by
 * hand, and the effect refuses to touch the timer for it: the user's click
 * always outranks the automatic countdown lifecycle. A new value (a new
 * revision) is the one thing that makes a fresh countdown meaningful again.
 */
export function useCardReadiness({ revision, savedRevision, stored, filled, error, completed, onDone }: {
  revision: number
  savedRevision: number
  /** A value has already been persisted for this card (a manual confirm is meaningful). */
  stored: boolean
  /** The card currently holds a value worth completing (may be ahead of what is stored). */
  filled: boolean
  error: string | null
  completed: boolean
  onDone: () => void
}) {
  const timer = useCardTimer()
  /** The user is still in this card: pointer over it, or typing in a field. */
  const [engaged, setEngaged] = useState(false)
  /** A field of this card is in use — the auto-countdown must wait, not the «ОК» button. */
  const [typing, setTyping] = useState(false)
  const [locked, setLocked] = useState(false)
  const card = useRef<HTMLDivElement>(null)
  const pointerInside = useRef(false)
  const textSession = useRef(false)
  const keyboardFocus = useRef(false)
  const keyboardInput = useRef(true)
  const callback = useRef(onDone)
  callback.current = onDone
  /** The revision the user completed by hand; terminal for the timer lifecycle. */
  const confirmed = useRef<number | null>(null)
  /** This completion was already reported, so it can never be reported twice. */
  const reported = useRef(false)
  // Three independent answers — see the module docstring.
  const settled = revision > 0 && revision === savedRevision
  const showOk = stored && filled && !completed
  const canConfirm = showOk && settled && !error
  const canCountdown = canConfirm && !engaged && !locked && !typing
  const { reset, startCountdown, timerState, confirmNow: confirmTimerNow } = timer
  /** Complete by hand — only ever with the newest value stored. */
  const confirmNow = useCallback(() => {
    if (!canConfirm) return
    // Terminal for this revision: see the "hand-confirm is terminal" note.
    confirmed.current = revision
    confirmTimerNow()
  }, [canConfirm, confirmTimerNow, revision])

  /** Re-derive engagement from the two sources a click cannot fake. */
  const syncEngagement = useCallback(() => {
    setEngaged(pointerInside.current || textSession.current || keyboardFocus.current)
  }, [])

  useEffect(() => {
    function pointerDown(event: PointerEvent) {
      keyboardInput.current = false
      keyboardFocus.current = false
      if (card.current?.contains(event.target as Node)) {
        // A press on the card is interaction; the user is still here.
        pointerInside.current = true
        setEngaged(true)
        return
      }
      // A press anywhere else is a real departure from this card.
      pointerInside.current = false
      textSession.current = false
      setTyping(false)
      setEngaged(false)
    }
    function keyDown() {
      keyboardInput.current = true
      if (card.current?.contains(document.activeElement)) {
        keyboardFocus.current = true
        reset()
        setEngaged(true)
      }
    }
    document.addEventListener('pointerdown', pointerDown, true)
    document.addEventListener('keydown', keyDown, true)
    return () => {
      document.removeEventListener('pointerdown', pointerDown, true)
      document.removeEventListener('keydown', keyDown, true)
    }
  }, [reset])

  useEffect(() => {
    // The user already completed this revision by hand: arming or resetting now
    // would cancel that completion (this effect can flush after the click).
    if (confirmed.current === revision) return
    reset()
    // Only a card that is stored, filled and left alone counts down.
    if (canCountdown) startCountdown()
  }, [revision, canCountdown, reset, startCountdown])

  useEffect(() => {
    // Leaving `done` — a reset or a fresh countdown — makes the next `done` a
    // new completion rather than a repeat of this one.
    if (timerState !== 'done') {
      reported.current = false
      return
    }
    if (!canConfirm || reported.current) return
    reported.current = true
    callback.current()
  }, [timerState, canConfirm])

  return {
    ...timer,
    confirmNow,
    locked,
    /** The manual «ОК» control is on screen whenever the card holds a stored value. */
    showOk,
    /** A manual confirmation is safe only with the newest value stored and no error. */
    canConfirm,
    /** The auto-countdown may run only once the user has left the card. */
    canCountdown,
    toggleLock: () => setLocked(value => !value),
    focusProps: {
      ref: card,
      onPointerEnter: () => {
        pointerInside.current = true
        reset()
        setEngaged(true)
      },
      // Leaving the card ends the engagement — unless the user is mid-typing,
      // in which case the field still holds their attention.
      onPointerLeave: () => {
        pointerInside.current = false
        syncEngagement()
      },
      onChangeCapture: () => {
        textSession.current = true
        setTyping(true)
        reset()
        setEngaged(true)
      },
      onFocusCapture: (event: FocusEvent<HTMLElement>) => {
        const target = event.target as HTMLElement
        keyboardFocus.current = keyboardInput.current
        if (target.matches('input, textarea')) {
          textSession.current = true
          setTyping(true)
          reset()
          setEngaged(true)
          return
        }
        // Entering the card cancels a running countdown; it starts fresh once
        // the user leaves again.
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          reset()
          setEngaged(true)
        }
      },
      onBlurCapture: (event: FocusEvent<HTMLElement>) => {
        // A click on the card's non-focusable header also blurs an input.
        // It must not be treated as leaving the card.
        if (event.relatedTarget === null && pointerInside.current) return
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          textSession.current = false
          keyboardFocus.current = false
          setTyping(false)
          syncEngagement()
        }
      },
    },
  }
}

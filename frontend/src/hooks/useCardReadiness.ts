import { useEffect, useRef, useState, type FocusEvent } from 'react'
import { useCardTimer } from './useCardTimer'

/** Readiness belongs to a card, independently of the shared persistence queue. */
export function useCardReadiness({ revision, savedRevision, filled, error, completed, onDone }: {
  revision: number
  savedRevision: number
  filled: boolean
  error: string | null
  completed: boolean
  onDone: () => void
}) {
  const timer = useCardTimer()
  const [editing, setEditing] = useState(false)
  const [locked, setLocked] = useState(false)
  const card = useRef<HTMLDivElement>(null)
  const pointerInside = useRef(false)
  const textSession = useRef(false)
  const callback = useRef(onDone)
  callback.current = onDone
  const ready = revision > 0 && revision === savedRevision && filled && !error && !completed
  const { reset, startCountdown } = timer

  useEffect(() => {
    function pointerDown(event: PointerEvent) {
      pointerInside.current = card.current?.contains(event.target as Node) ?? false
      if (!pointerInside.current) { textSession.current = false; setEditing(false) }
    }
    document.addEventListener('pointerdown', pointerDown, true)
    return () => document.removeEventListener('pointerdown', pointerDown, true)
  }, [])

  useEffect(() => {
    reset()
    if (ready && !editing && !locked) startCountdown()
  }, [revision, ready, editing, locked, reset, startCountdown])

  useEffect(() => {
    if (timer.timerState === 'done' && ready) callback.current()
  }, [timer.timerState, ready])

  return {
    ...timer,
    locked,
    showActions: ready && (!editing || locked),
    toggleLock: () => setLocked(value => !value),
    focusProps: {
      ref: card,
      onChangeCapture: () => { textSession.current = true; reset(); setEditing(true) },
      onClickCapture: (event: React.MouseEvent<HTMLElement>) => {
        const target = event.target as HTMLElement
        if (!textSession.current && target.closest('button') && !target.closest('[data-readiness-actions]')) {
          setEditing(false)
        }
      },
      onFocusCapture: (event: FocusEvent<HTMLElement>) => {
        const target = event.target as HTMLElement
        if (target.closest('[data-readiness-actions]')) return
        if (target.matches('input, textarea')) textSession.current = true
        if (textSession.current || (timer.timerState === 'counting' && !event.currentTarget.contains(event.relatedTarget as Node | null))) {
          reset()
          setEditing(true)
        }
      },
      onBlurCapture: (event: FocusEvent<HTMLElement>) => {
        // A click on the card's non-focusable header also blurs an input.
        // It must not be treated as leaving the card.
        if (event.relatedTarget === null && pointerInside.current) return
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          textSession.current = false
          setEditing(false)
        }
      },
    },
  }
}

/**
 * useCardReadiness — the hand-confirm / countdown lifecycle.
 *
 * The card's commit (button on screen, enabled) happens *before* the readiness
 * effect that arms the countdown flushes. These tests pin down that a hand
 * confirm made in that window is terminal: nothing the pending effect does may
 * undo it, and a completion is never reported twice.
 *
 * The countdown is driven by a fake rAF clock, exactly like useCardTimer.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { useCardReadiness } from './useCardReadiness'

// ---------------------------------------------------------------------------
// Fake rAF — synchronous, deterministic
// ---------------------------------------------------------------------------

let rafCallbacks: Array<(t: number) => void> = []
let fakeTime = 0

function installFakeRaf() {
  rafCallbacks = []
  fakeTime = 0
  vi.stubGlobal('requestAnimationFrame', (cb: (t: number) => void) => {
    rafCallbacks.push(cb)
    return rafCallbacks.length
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    rafCallbacks[id - 1] = () => {}
  })
  vi.stubGlobal('performance', { now: () => fakeTime })
}

function tickRaf(time: number) {
  fakeTime = time
  const pending = [...rafCallbacks]
  rafCallbacks = []
  for (const cb of pending) cb(time)
}

beforeEach(installFakeRaf)
afterEach(() => vi.unstubAllGlobals())

// ---------------------------------------------------------------------------

type Props = Parameters<typeof useCardReadiness>[0]

function props(overrides: Partial<Props> = {}): Props {
  return {
    revision: 1,
    savedRevision: 1,
    stored: true,
    filled: true,
    error: null,
    completed: false,
    onDone: vi.fn(),
    ...overrides,
  }
}

function render(initial: Props) {
  return renderHook((current: Props) => useCardReadiness(current), { initialProps: initial })
}

it('counts down and reports the completion exactly once', () => {
  const initial = props()
  const { result } = render(initial)

  expect(result.current.showOk).toBe(true)
  expect(result.current.timerState).toBe('counting')

  act(() => tickRaf(5_000))

  expect(result.current.timerState).toBe('done')
  expect(initial.onDone).toHaveBeenCalledTimes(1)
})

it('completes immediately when «ОК» is pressed during a running countdown', () => {
  const initial = props()
  const { result } = render(initial)
  act(() => tickRaf(1_000))            // partway through

  act(() => result.current.confirmNow())

  expect(result.current.timerState).toBe('done')
  expect(initial.onDone).toHaveBeenCalledTimes(1)

  // Pressing again cannot report the same completion twice.
  act(() => result.current.confirmNow())
  act(() => tickRaf(10_000))
  expect(initial.onDone).toHaveBeenCalledTimes(1)
})

it('keeps a hand-confirm when the arming effect runs after it (race window)', () => {
  const initial = props()
  const { result } = render(initial)
  expect(result.current.timerState).toBe('counting')

  // A field of the card is in use, so the countdown is paused — the button
  // stays on screen and enabled.
  act(() => result.current.focusProps.onPointerEnter())
  expect(result.current.timerState).toBe('idle')
  expect(result.current.canConfirm).toBe(true)

  // The window: the click and the update that will re-run the arming effect
  // land in the same batch, so the effect flushes *after* the confirm.
  act(() => {
    result.current.focusProps.onPointerLeave()
    result.current.confirmNow()
  })

  expect(result.current.timerState).toBe('done')
  expect(initial.onDone).toHaveBeenCalledTimes(1)

  // Nothing re-arms afterwards: no second countdown, no second completion.
  act(() => tickRaf(10_000))
  expect(result.current.timerState).toBe('done')
  expect(initial.onDone).toHaveBeenCalledTimes(1)
})

it('never reports a second completion when the card is re-entered after a hand-confirm', () => {
  const initial = props()
  const { result } = render(initial)

  act(() => result.current.focusProps.onPointerEnter())
  act(() => result.current.confirmNow())
  expect(initial.onDone).toHaveBeenCalledTimes(1)

  // Coming and going after the confirm must not arm a second countdown for the
  // same revision, however long the card stays on screen. (Re-entering the card
  // still pauses the countdown phase — that is an explicit user interaction,
  // not a pending effect — but it must not complete anything again.)
  act(() => result.current.focusProps.onPointerLeave())
  act(() => result.current.focusProps.onPointerEnter())
  act(() => result.current.focusProps.onPointerLeave())
  act(() => tickRaf(20_000))

  expect(result.current.timerState).not.toBe('counting')
  expect(initial.onDone).toHaveBeenCalledTimes(1)
})

it('arms a fresh countdown for a new value after a hand-confirm', () => {
  const initial = props()
  const { result, rerender } = render(initial)

  act(() => result.current.confirmNow())
  expect(initial.onDone).toHaveBeenCalledTimes(1)

  // The user edits the card: a new revision is a new countdown.
  rerender(props({ revision: 2, savedRevision: 1, onDone: initial.onDone }))
  expect(result.current.timerState).toBe('idle')

  rerender(props({ revision: 2, savedRevision: 2, onDone: initial.onDone }))
  expect(result.current.timerState).toBe('counting')

  act(() => tickRaf(15_000))
  expect(initial.onDone).toHaveBeenCalledTimes(2)
})

it('does not count down while the value is still being saved', () => {
  const initial = props({ revision: 2, savedRevision: 1 })
  const { result } = render(initial)

  expect(result.current.timerState).toBe('idle')
  act(() => tickRaf(10_000))
  expect(initial.onDone).not.toHaveBeenCalled()
})

it('refuses a hand-confirm while an error is showing', () => {
  const initial = props({ error: 'Ошибка' })
  const { result } = render(initial)

  expect(result.current.canConfirm).toBe(false)
  act(() => result.current.confirmNow())
  expect(initial.onDone).not.toHaveBeenCalled()
})

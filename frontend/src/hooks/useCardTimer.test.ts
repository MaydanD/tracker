import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCardTimer } from './useCardTimer'

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
    return rafCallbacks.length  // fake id
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    rafCallbacks[id - 1] = () => {}  // noop the specific slot
  })
  vi.stubGlobal('performance', { now: () => fakeTime })
}

/** Flush all pending rAF callbacks at the given simulated timestamp. */
function tickRaf(time: number) {
  fakeTime = time
  const pending = [...rafCallbacks]
  rafCallbacks = []
  for (const cb of pending) cb(time)
}

afterEach(() => {
  vi.unstubAllGlobals()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useCardTimer', () => {
  beforeEach(installFakeRaf)

  it('starts idle with zero progress', () => {
    const { result } = renderHook(() => useCardTimer())
    expect(result.current.timerState).toBe('idle')
    expect(result.current.progress).toBe(0)
  })

  it('transitions to counting on startCountdown', () => {
    const { result } = renderHook(() => useCardTimer())
    act(() => result.current.startCountdown())
    expect(result.current.timerState).toBe('counting')
  })

  it('increases progress as rAF ticks advance', () => {
    const { result } = renderHook(() => useCardTimer())
    act(() => result.current.startCountdown())
    act(() => tickRaf(2_500))   // halfway
    expect(result.current.progress).toBeCloseTo(0.5, 1)
    expect(result.current.timerState).toBe('counting')
  })

  it('reaches done when the full 5 seconds elapse', () => {
    const { result } = renderHook(() => useCardTimer())
    act(() => result.current.startCountdown())
    act(() => tickRaf(5_000))
    expect(result.current.timerState).toBe('done')
    expect(result.current.progress).toBe(1)
  })

  it('confirmNow skips to done immediately', () => {
    const { result } = renderHook(() => useCardTimer())
    act(() => result.current.startCountdown())
    act(() => tickRaf(1_000))  // partway through
    act(() => result.current.confirmNow())
    expect(result.current.timerState).toBe('done')
    expect(result.current.progress).toBe(1)
  })

  it('reset returns to idle and cancels the countdown', () => {
    const { result } = renderHook(() => useCardTimer())
    act(() => result.current.startCountdown())
    act(() => tickRaf(2_000))
    act(() => result.current.reset())
    expect(result.current.timerState).toBe('idle')
    expect(result.current.progress).toBe(0)
    // Further ticks should not change state (old loop was cancelled)
    act(() => tickRaf(5_000))
    expect(result.current.timerState).toBe('idle')
  })

  it('startCountdown a second time resets the clock', () => {
    const { result } = renderHook(() => useCardTimer())
    act(() => result.current.startCountdown())
    act(() => tickRaf(3_000))   // 60% through
    // Restart
    act(() => result.current.startCountdown())
    act(() => tickRaf(3_000))   // still 3 s from the new start (0.6)
    // The first loop must not advance to done — only the new one runs
    expect(result.current.timerState).toBe('counting')
    act(() => tickRaf(8_000))   // 5 s from restart
    expect(result.current.timerState).toBe('done')
  })

  it('does not call setState after unmount', () => {
    const { result, unmount } = renderHook(() => useCardTimer())
    act(() => result.current.startCountdown())
    unmount()
    // ticking after unmount should not throw
    expect(() => act(() => tickRaf(10_000))).not.toThrow()
    // state stays as it was at unmount time
    expect(result.current.timerState).toBe('counting')
  })
})

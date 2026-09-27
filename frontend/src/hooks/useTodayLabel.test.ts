import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { formatDayMonthLabel } from '../utils/dateUtils'
import { useTodayLabel } from './useTodayLabel'

describe('useTodayLabel', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the local day and month without a year or leading zero', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 8, 27, 12, 0))

    const { result } = renderHook(() => useTodayLabel())

    expect(result.current).toBe('27 сентября')
    // A single-digit day is never padded.
    expect(formatDayMonthLabel(new Date(2026, 0, 5))).toBe('5 января')
  })

  it('rolls over to the next date after local midnight without a reload', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 8, 27, 23, 59, 30))

    const { result } = renderHook(() => useTodayLabel())
    expect(result.current).toBe('27 сентября')

    act(() => {
      vi.advanceTimersByTime(31_000)
    })

    expect(result.current).toBe('28 сентября')
  })
})

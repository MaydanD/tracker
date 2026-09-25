import { describe, expect, it } from 'vitest'
import {
  daysInMonth,
  formatFullDateLabel,
  formatIsoDate,
  formatMonthTitle,
  formatShortDateLabel,
  getMonthGridDays,
  getYearGridWeeks,
  isLeapYear,
  nextMonth,
  parseIsoParts,
  prevMonth,
  weekdayMondayFirst,
} from './dateUtils'

describe('dateUtils', () => {
  it('parses and formats ISO dates without timezone shift', () => {
    const parsed = parseIsoParts('2026-09-25')
    expect(parsed).toEqual({ year: 2026, month: 9, day: 25 })
    expect(formatIsoDate(2026, 9, 25)).toBe('2026-09-25')
  })

  it('correctly identifies leap years', () => {
    expect(isLeapYear(2024)).toBe(true)
    expect(isLeapYear(2025)).toBe(false)
    expect(isLeapYear(2000)).toBe(true)
    expect(isLeapYear(1900)).toBe(false)
  })

  it('returns correct days in month', () => {
    expect(daysInMonth(2024, 2)).toBe(29)
    expect(daysInMonth(2025, 2)).toBe(28)
    expect(daysInMonth(2026, 9)).toBe(30)
    expect(daysInMonth(2026, 12)).toBe(31)
  })

  it('calculates Monday-first weekday indices correctly', () => {
    // 2026-09-21 is Monday (0)
    expect(weekdayMondayFirst(2026, 9, 21)).toBe(0)
    // 2026-09-25 is Friday (4)
    expect(weekdayMondayFirst(2026, 9, 25)).toBe(4)
    // 2026-09-27 is Sunday (6)
    expect(weekdayMondayFirst(2026, 9, 27)).toBe(6)
  })

  it('navigates previous and next months across year boundaries', () => {
    expect(prevMonth(2026, 1)).toEqual({ year: 2025, month: 12 })
    expect(prevMonth(2026, 5)).toEqual({ year: 2026, month: 4 })
    expect(nextMonth(2026, 12)).toEqual({ year: 2027, month: 1 })
    expect(nextMonth(2026, 5)).toEqual({ year: 2026, month: 6 })
  })

  it('generates a valid Monday-first month grid', () => {
    const days = getMonthGridDays(2026, 9) // Sept 2026 starts on Tuesday (Sept 1)
    expect(days.length % 7).toBe(0)
    // First cell in grid should be Monday Aug 31, 2026
    expect(days[0]).toBe('2026-08-31')
    // Contains Sept 1 to Sept 30
    expect(days).toContain('2026-09-01')
    expect(days).toContain('2026-09-30')
  })

  it('generates valid year grid weeks for ordinary and leap years', () => {
    const weeks2024 = getYearGridWeeks(2024) // Leap year
    const dates2024 = weeks2024.flat().filter((d) => d.startsWith('2024-'))
    expect(dates2024.length).toBe(366)
    expect(dates2024).toContain('2024-02-29')

    const weeks2025 = getYearGridWeeks(2025) // Ordinary year
    const dates2025 = weeks2025.flat().filter((d) => d.startsWith('2025-'))
    expect(dates2025.length).toBe(365)
    expect(dates2025).not.toContain('2025-02-29')
  })

  it('formats human labels in Russian', () => {
    expect(formatMonthTitle(2026, 9)).toBe('Сентябрь 2026')
    expect(formatFullDateLabel('2026-09-25')).toBe('25 сентября 2026, пятница')
    expect(formatShortDateLabel('2026-09-25')).toBe('25.09.2026')
  })
})

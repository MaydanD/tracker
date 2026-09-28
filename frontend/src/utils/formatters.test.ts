import { describe, expect, it } from 'vitest'

import { formatStreakText } from './formatters'

describe('formatStreakText', () => {
  it.each([
    ['days', 1, '🔥 1 день'],
    ['days', 7, '🔥 7 дней'],
    ['days', 22, '🔥 22 дня'],
    ['weeks', 1, '🔥 1 неделя'],
    ['weeks', 4, '🔥 4 недели'],
    ['weeks', 11, '🔥 11 недель'],
  ] as const)('formats an ongoing %s streak of %i', (unit, count, label) => {
    expect(formatStreakText(count, unit)).toBe(label)
  })

  it.each([['days', 0], ['weeks', 0], ['days', -3]] as const)(
    'states the absence of a %s streak of %i without a flame',
    (unit, count) => {
      expect(formatStreakText(count, unit)).toBe('Нет серии')
      expect(formatStreakText(count, unit)).not.toContain('🔥')
    },
  )
})

import { afterEach, describe, expect, it, vi } from 'vitest'

import { AREA_COLOR_PALETTE, pickAreaColor } from './areaColors'

describe('pickAreaColor', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('always returns a colour from the curated palette', () => {
    for (let i = 0; i < 50; i += 1) {
      expect(AREA_COLOR_PALETTE).toContain(pickAreaColor())
    }
  })

  it('never repeats the most recently used colour', () => {
    for (const last of AREA_COLOR_PALETTE) {
      for (let i = 0; i < 20; i += 1) {
        expect(pickAreaColor([last]).toLowerCase()).not.toBe(last.toLowerCase())
      }
    }
  })

  it('does not depend on the order of older colours', () => {
    vi.spyOn(Math, 'random').mockReturnValue(0)
    const a = pickAreaColor(['#2f9e5f', '#3f6fd8'])
    const b = pickAreaColor(['#c2540a', '#3f6fd8'])
    expect(a).toBe(b)
    expect(a.toLowerCase()).not.toBe('#3f6fd8')
  })
})

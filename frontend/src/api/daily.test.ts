import { describe, expect, it } from 'vitest'
import { fetchDay } from './daily'
import { describeApiError } from './client'
import { dayItemFixture, dayStateFixture } from '../test/fixtures'
import { jsonResponse, stubApi } from '../test/fetchStub'

describe('day tracking metadata', () => {
  it('rejects the stale API instead of silently turning scales into completion habits', async () => {
    const { value_type, value_labels, ...oldItem } = dayItemFixture()
    stubApi({ 'GET /api/days/2026-09-29': () => jsonResponse({ items: [oldItem] }) })
    const error = await fetchDay('2026-09-29').catch(error => error)
    expect(error.code).toBe('outdated_tracking_api')
    expect(describeApiError(error)).toContain('Перезапустите Tracker')
  })

  it('preserves explicit completion, custom scale, canonical scale and quantity metadata', async () => {
    const day = dayStateFixture([
      dayItemFixture(),
      dayItemFixture({ value_type: 'ordinal_4', value_labels: ['Мало', 'Средне', 'Много', 'Очень много'] }),
      dayItemFixture({ value_type: 'binary', value_labels: ['нет', 'да'] }),
      dayItemFixture({ tracking_mode: 'binary_quantity', quantity_unit: 'страниц' }),
    ])
    stubApi({ 'GET /api/days/2026-09-29': () => jsonResponse(day) })
    expect(await fetchDay('2026-09-29')).toEqual(day)
  })
})

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DailyEntry, DayItem } from '../../api/types'
import { HabitDayList } from './HabitDayList'

function item(overrides: Partial<DayItem> = {}): DayItem {
  return {
    habit_id: 1,
    name: 'Чтение',
    area: { id: 1, name: 'Здоровье', color: '#2f9e5f', is_archived: false },
    importance: 'normal',
    weight: 1,
    tracking_mode: 'binary',
    quantity_unit: null,
    quantity_allows_decimal: false,
    value_type: null,
    value_labels: null,
    direction: null,
    schedule: {
      type: 'daily',
      weekdays: [],
      times_per_week: null,
      weekly_required_count: 7,
      summary: 'Каждый день',
    },
    is_archived: false,
    entry: null,
    ...overrides,
  }
}

function entry(status: DailyEntry['status']): DailyEntry {
  return {
    id: 1,
    habit_id: 1,
    entry_date: '2026-09-25',
    status,
    value: null,
    quantity_value: null,
    quantity_unit: null,
    skip_reason: status === 'skipped' ? 'Отпуск' : null,
    note: null,
    created_at: '2026-09-25T10:00:00',
    updated_at: '2026-09-25T10:00:00',
  }
}

function renderList(items: DayItem[]) {
  return render(
    <HabitDayList
      items={items}
      entryDate="2026-09-25"
      isFuture={false}
      onChanged={() => {}}
    />,
  )
}

describe('HabitDayList', () => {
  it('keeps unrecorded habits visible and collapses the recorded ones', () => {
    renderList([
      item({ habit_id: 1, name: 'Чтение', entry: entry('done') }),
      item({ habit_id: 2, name: 'Спорт', entry: null }),
    ])

    // The habit still needing a mark is visible without expanding anything.
    expect(screen.getByText('Спорт')).toBeInTheDocument()
    expect(screen.getByText('Осталось отметить')).toBeInTheDocument()

    const recorded = screen.getByText('Уже отмечено · 1').closest('details')
    expect(recorded).not.toBeNull()
    expect(recorded).not.toHaveAttribute('open')
    // The recorded habit is still present and editable, just behind the disclosure.
    expect(within(recorded as HTMLElement).getByText('Чтение')).toBeInTheDocument()
    expect(within(recorded as HTMLElement).getByRole('button', { name: 'Очистить' })).toBeInTheDocument()
  })

  it('shows a finished day instead of an empty screen when everything is marked', () => {
    renderList([
      item({ habit_id: 1, name: 'Чтение', entry: entry('done') }),
      item({ habit_id: 2, name: 'Спорт', entry: entry('done') }),
    ])

    expect(screen.getByText('День завершён')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Сова Tracker' })).toBeInTheDocument()
    expect(screen.queryByText('Осталось отметить')).not.toBeInTheDocument()
    expect(screen.getByText('Уже отмечено · 2').closest('details')).not.toBeNull()
  })

  it('does not claim a finished, all-done day when something was missed', () => {
    renderList([
      item({ habit_id: 1, name: 'Чтение', entry: entry('missed') }),
    ])

    expect(screen.getByText('Все привычки отмечены')).toBeInTheDocument()
    expect(screen.queryByText('День завершён')).not.toBeInTheDocument()
  })
})

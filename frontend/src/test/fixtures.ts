import type {
  Area,
  AreaSummary,
  DailyEntry,
  DayItem,
  DayState,
  Habit,
  HabitVersion,
  ScheduleRead,
} from '../api/types'
import { localTodayIso } from '../components/daily/dates'

export function areaFixture(overrides: Partial<Area> = {}): Area {
  return {
    id: 1,
    name: 'Health',
    color: '#2f9e5f',
    is_archived: false,
    archived_at: null,
    created_at: '2026-09-01T10:00:00',
    updated_at: '2026-09-01T10:00:00',
    ...overrides,
  }
}

export function areaSummary(area: Area): AreaSummary {
  return {
    id: area.id,
    name: area.name,
    color: area.color,
    is_archived: area.is_archived,
  }
}

export function dailySchedule(): ScheduleRead {
  return {
    type: 'daily',
    weekdays: [],
    times_per_week: null,
    weekly_required_count: 7,
    summary: 'Every day',
  }
}

export function weekdaySchedule(weekdays: number[] = [0, 2, 4]): ScheduleRead {
  return {
    type: 'weekdays',
    weekdays,
    times_per_week: null,
    weekly_required_count: weekdays.length,
    summary: `${weekdays.length} days`,
  }
}

export function habitFixture(overrides: Partial<Habit> = {}): Habit {
  const area = overrides.area ?? areaSummary(areaFixture())
  return {
    id: 1,
    key: null,
    name: 'Reading',
    description: null,
    area_id: area.id,
    area,
    importance: 'normal',
    weight: 1,
    tracking_mode: 'binary',
    quantity_unit: null,
    quantity_allows_decimal: false,
    value_type: null,
    value_labels: null,
    direction: null,
    schedule: dailySchedule(),
    is_archived: false,
    archived_at: null,
    created_at: '2026-09-01T10:00:00',
    updated_at: '2026-09-01T10:00:00',
    current_version: {
      version_number: 1,
      effective_from: '2026-09-01',
      created_at: '2026-09-01T10:00:00',
    },
    ...overrides,
  }
}

export function dailyEntryFixture(overrides: Partial<DailyEntry> = {}): DailyEntry {
  return {
    id: 1,
    habit_id: 1,
    entry_date: localTodayIso(),
    status: 'done',
    value: null,
    quantity_value: null,
    quantity_unit: null,
    skip_reason: null,
    note: null,
    created_at: '2026-09-24T18:00:00',
    updated_at: '2026-09-24T18:00:00',
    ...overrides,
  }
}

/** One habit on a date, as the day endpoint returns it. */
export function dayItemFixture(overrides: Partial<DayItem> = {}): DayItem {
  return {
    habit_id: 1,
    name: 'Reading',
    area: areaSummary(areaFixture()),
    importance: 'normal',
    weight: 1,
    tracking_mode: 'binary',
    quantity_unit: null,
    quantity_allows_decimal: false,
    value_type: null,
    value_labels: null,
    direction: null,
    schedule: dailySchedule(),
    is_archived: false,
    entry: null,
    ...overrides,
  }
}

export function dayStateFixture(
  items: DayItem[],
  overrides: Partial<DayState> = {},
): DayState {
  const today = localTodayIso()
  return {
    entry_date: today,
    today,
    is_future: false,
    items,
    ...overrides,
  }
}

export function versionFixture(overrides: Partial<HabitVersion> = {}): HabitVersion {
  return {
    habit_id: 1,
    version_number: 1,
    effective_from: '2026-09-01',
    created_at: '2026-09-01T10:00:00',
    name: 'Reading',
    description: null,
    area_id: 1,
    area: areaSummary(areaFixture()),
    importance: 'normal',
    weight: 1,
    tracking_mode: 'binary',
    quantity_unit: null,
    quantity_allows_decimal: false,
    value_type: null,
    value_labels: null,
    direction: null,
    schedule: dailySchedule(),
    ...overrides,
  }
}

/**
 * A habit answered on a value scale, the kind the canonical set ships.
 *
 * Its words and its direction are configuration, so a test states them here
 * rather than hardcoding them in a component.
 */
export function valueHabitFixture(overrides: Partial<Habit> = {}): Habit {
  return habitFixture({
    name: 'Настроение',
    value_type: 'ordinal_4',
    value_labels: ['ужас', 'плохо', 'норм', 'хорошо'],
    direction: 'positive',
    ...overrides,
  })
}

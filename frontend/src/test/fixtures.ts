import type {
  Area,
  AreaSummary,
  Habit,
  HabitVersion,
  ScheduleRead,
} from '../api/types'

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
    name: 'Reading',
    description: null,
    area_id: area.id,
    area,
    weight: 1,
    tracking_mode: 'binary',
    quantity_unit: null,
    quantity_allows_decimal: false,
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
    weight: 1,
    tracking_mode: 'binary',
    quantity_unit: null,
    quantity_allows_decimal: false,
    schedule: dailySchedule(),
    ...overrides,
  }
}

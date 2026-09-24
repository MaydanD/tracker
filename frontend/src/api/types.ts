/** Response shapes returned by the Tracker API. */

/** `GET /api/health` — the backend process is alive. */
export interface HealthResponse {
  status: 'ok'
  app: string
  version: string
  environment: string
}

/** `GET /api/ready` — the backend can reach its database. */
export interface ReadinessResponse {
  status: 'ready' | 'unavailable'
  checks: Record<string, string>
}

/** Shared error envelope used by every failing API response. */
export interface ErrorResponse {
  error: {
    code: string
    message: string
    details?: Record<string, unknown> | null
  }
}

// ---------------------------------------------------------------------------
// Areas
// ---------------------------------------------------------------------------

export interface Area {
  id: number
  name: string
  color: string
  is_archived: boolean
  archived_at: string | null
  created_at: string
  updated_at: string
}

/** Compact area reference embedded in habit responses. */
export interface AreaSummary {
  id: number
  name: string
  color: string
  is_archived: boolean
}

export interface AreaInput {
  name: string
  color?: string
}

export interface AreaUpdateInput {
  name?: string
  color?: string
}

// ---------------------------------------------------------------------------
// Habits
// ---------------------------------------------------------------------------

export type TrackingMode = 'binary' | 'binary_quantity'

export type ScheduleType = 'daily' | 'weekdays' | 'times_per_week'

/** Weekdays are ISO numbers: 0 = Monday … 6 = Sunday. */
export type Weekday = 0 | 1 | 2 | 3 | 4 | 5 | 6

/** Schedule as submitted to the API. Which fields are required depends on `type`. */
export interface ScheduleInput {
  type: ScheduleType
  weekdays?: number[] | null
  times_per_week?: number | null
}

/** Stored schedule plus server-computed quota and summary. */
export interface ScheduleRead {
  type: ScheduleType
  weekdays: number[]
  times_per_week: number | null
  /** Completions the canonical Monday–Sunday week expects. */
  weekly_required_count: number
  summary: string
}

/** The configuration shared by a habit and each of its history versions. */
export interface HabitConfig {
  name: string
  description: string | null
  area_id: number
  area: AreaSummary
  weight: number
  tracking_mode: TrackingMode
  quantity_unit: string | null
  quantity_allows_decimal: boolean
  schedule: ScheduleRead
}

/** Identifies the configuration version currently in effect. */
export interface VersionSummary {
  version_number: number
  effective_from: string
  created_at: string
}

export interface Habit extends HabitConfig {
  id: number
  is_archived: boolean
  archived_at: string | null
  created_at: string
  updated_at: string
  current_version: VersionSummary
}

export interface HabitVersion extends HabitConfig {
  habit_id: number
  version_number: number
  effective_from: string
  created_at: string
}

// ---------------------------------------------------------------------------
// Daily tracking
// ---------------------------------------------------------------------------

/**
 * What the user recorded for a habit on one date.
 *
 * `done` and `missed` describe a day that has already happened; `skipped` is a
 * deliberate/planned skip and is the only status a future date accepts.
 */
export type EntryStatus = 'done' | 'missed' | 'skipped'

/** One recorded day, as returned by the API. */
export interface DailyEntry {
  id: number
  habit_id: number
  entry_date: string
  status: EntryStatus
  /** Exact stored value; null when no quantity was recorded. */
  quantity_value: number | null
  /** Unit of the configuration effective on `entry_date` (derived, not stored). */
  quantity_unit: string | null
  skip_reason: string | null
  note: string | null
  created_at: string
  updated_at: string
}

/** Body for saving an entry. Saving is a replace: omitted fields are cleared. */
export interface DailyEntryInput {
  status: EntryStatus
  quantity_value?: number | null
  skip_reason?: string | null
  note?: string | null
}

/** One habit as it appears on a chosen date, with that date's configuration. */
export interface DayItem {
  habit_id: number
  name: string
  area: AreaSummary
  weight: number
  tracking_mode: TrackingMode
  quantity_unit: string | null
  quantity_allows_decimal: boolean
  schedule: ScheduleRead
  is_archived: boolean
  /** `null` means "нет отметки" — it is not the same as `missed`. */
  entry: DailyEntry | null
}

/** `GET /api/days/{date}` — the state of one calendar date. */
export interface DayState {
  entry_date: string
  /** The server's current date; the authority for "is this the future?". */
  today: string
  is_future: boolean
  items: DayItem[]
}

/** Full configuration payload for creating or replacing a habit. */
export interface HabitInput {
  name: string
  description?: string | null
  area_id: number
  weight: number
  tracking_mode: TrackingMode
  quantity_unit?: string | null
  quantity_allows_decimal?: boolean
  schedule: ScheduleInput
}
export interface Score {
  score: number | null
  completed_weight: number
  required_weight: number
}

export interface WeekHabitProgress extends Score {
  habit_id: number
  name: string
  quota: number
  completed_count: number
  daily_required_count: number
  daily_completed_count: number
  weekly_quota: number
  weekly_completed_count: number
  weekly_weight: number | null
  weekly_effective_from: string | null
  preferred_weekdays: number[]
  status: 'satisfied' | 'pending' | 'failed'
}

export interface HabitStreak {
  habit_id: number
  current_streak: number
  unit: 'days' | 'weeks'
  as_of: string
}

export interface ProgressState {
  today: string
  day: Score & {
    entry_date: string
    obligations: { habit_id: number; name: string; weight: number; entry_status: EntryStatus | null; satisfied: boolean }[]
  }
  week: Score & { week_start: string; week_end: string; habits: WeekHabitProgress[] }
  streaks: HabitStreak[]
}

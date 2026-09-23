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

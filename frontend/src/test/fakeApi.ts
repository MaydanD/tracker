import type { Area, Habit, HabitInput, HabitVersion } from '../api/types'
import { jsonResponse, stubApi, type StubHandler, type StubRequest } from './fetchStub'
import { areaFixture, habitFixture } from './fixtures'

/**
 * A deliberately small in-memory stand-in for the Tracker API.
 *
 * It covers the happy paths the pages drive (list with filters, create, update,
 * archive, unarchive, history). It does *not* re-implement backend rules: tests
 * that need the UI to handle a rejection stub that response explicitly, so the
 * fake stays small and cannot drift into a second server.
 */
export interface FakeApi {
  areas: Area[]
  habits: Habit[]
  handle: StubHandler
}

export interface FakeApiOptions {
  areas?: Area[]
  habits?: Habit[]
}

function conflict(code: string, message: string): Response {
  return jsonResponse({ error: { code, message } }, 409)
}

function notFound(code: string, message: string): Response {
  return jsonResponse({ error: { code, message } }, 404)
}

export function createFakeApi(options: FakeApiOptions = {}): FakeApi {
  const state = {
    areas: [...(options.areas ?? [])],
    habits: [...(options.habits ?? [])],
    nextAreaId: 100,
    nextHabitId: 100,
  }

  const findArea = (id: number): Area | undefined =>
    state.areas.find((area) => area.id === id)
  const findHabit = (id: number): Habit | undefined =>
    state.habits.find((habit) => habit.id === id)

  const replaceArea = (area: Area): void => {
    state.areas = state.areas.map((entry) => (entry.id === area.id ? area : entry))
  }
  const replaceHabit = (habit: Habit): void => {
    state.habits = state.habits.map((entry) => (entry.id === habit.id ? habit : entry))
  }

  function areaRoutes(
    method: string,
    id: number | null,
    action: string | null,
    request: StubRequest,
  ): Response | null {
    if (method === 'GET' && id === null) {
      const includeArchived = request.query.get('include_archived') === 'true'
      return jsonResponse(
        state.areas
          .filter((area) => includeArchived || !area.is_archived)
          .sort((a, b) => a.name.localeCompare(b.name)),
      )
    }

    if (method === 'POST' && id === null) {
      const body = (request.body ?? {}) as { name?: string; color?: string }
      const name = (body.name ?? '').trim()
      if (state.areas.some((area) => !area.is_archived && area.name === name)) {
        return conflict(
          'area_name_conflict',
          'An active area with that name already exists.',
        )
      }
      const area = areaFixture({
        id: state.nextAreaId++,
        name,
        color: body.color ?? '#4a7cc7',
      })
      state.areas = [...state.areas, area]
      return jsonResponse(area, 201)
    }

    if (id === null) return null
    const area = findArea(id)
    if (!area) return notFound('area_not_found', 'That area does not exist.')

    if (method === 'PATCH' && action === null) {
      const body = (request.body ?? {}) as { name?: string; color?: string }
      const updated = { ...area, name: body.name ?? area.name, color: body.color ?? area.color }
      replaceArea(updated)
      return jsonResponse(updated)
    }

    if (method === 'POST' && action === 'archive') {
      const hasActiveHabits = state.habits.some(
        (habit) => !habit.is_archived && habit.area_id === area.id,
      )
      if (hasActiveHabits) {
        return conflict(
          'area_has_active_habits',
          'This area still has active habits. Archive or move them first.',
        )
      }
      const archived = { ...area, is_archived: true, archived_at: '2026-09-20T10:00:00' }
      replaceArea(archived)
      return jsonResponse(archived)
    }

    if (method === 'POST' && action === 'unarchive') {
      const restored = { ...area, is_archived: false, archived_at: null }
      replaceArea(restored)
      return jsonResponse(restored)
    }

    return null
  }

  function habitRoutes(
    method: string,
    id: number | null,
    action: string | null,
    request: StubRequest,
  ): Response | null {
    if (method === 'GET' && id === null) {
      const includeArchived = request.query.get('include_archived') === 'true'
      const areaId = request.query.get('area_id')
      return jsonResponse(
        state.habits
          .filter((habit) => includeArchived || !habit.is_archived)
          .filter((habit) => areaId === null || habit.area_id === Number(areaId))
          .sort(
            (a, b) =>
              a.area.name.localeCompare(b.area.name) || a.name.localeCompare(b.name),
          ),
      )
    }

    if (method === 'POST' && id === null) {
      const input = request.body as HabitInput
      const area = findArea(input.area_id)
      if (!area) return notFound('area_not_found', 'That area does not exist.')
      const habit = habitFixture({
        id: state.nextHabitId++,
        ...configFromInput(input, area),
      })
      state.habits = [...state.habits, habit]
      return jsonResponse(habit, 201)
    }

    if (id === null) return null
    const habit = findHabit(id)
    if (!habit) return notFound('habit_not_found', 'That habit does not exist.')

    if (method === 'PUT' && action === null) {
      const input = request.body as HabitInput
      const area = findArea(input.area_id)
      if (!area) return notFound('area_not_found', 'That area does not exist.')
      const updated = habitFixture({
        ...habit,
        ...configFromInput(input, area),
        current_version: {
          version_number: habit.current_version.version_number + 1,
          effective_from: '2026-09-20',
          created_at: '2026-09-20T10:00:00',
        },
      })
      replaceHabit(updated)
      return jsonResponse(updated)
    }

    if (method === 'POST' && action === 'archive') {
      const archived = { ...habit, is_archived: true, archived_at: '2026-09-20T10:00:00' }
      replaceHabit(archived)
      return jsonResponse(archived)
    }

    if (method === 'POST' && action === 'unarchive') {
      const restored = { ...habit, is_archived: false, archived_at: null }
      replaceHabit(restored)
      return jsonResponse(restored)
    }

    if (method === 'GET' && action === 'versions') {
      return jsonResponse(versionsOf(habit))
    }

    return null
  }

  function handle(request: StubRequest): Response {
    const segments = request.path.split('/').filter((part) => part.length > 0)
    const [, resource, rawId, action = null] = segments
    const id = rawId !== undefined && /^\d+$/.test(rawId) ? Number(rawId) : null
    // A path like /api/habits/archive has no numeric id, so treat the segment as
    // the action instead of an id.
    const resolvedAction = rawId !== undefined && id === null ? rawId : action

    if (resource === 'areas') {
      const response = areaRoutes(request.method, id, resolvedAction, request)
      if (response) return response
    }
    if (resource === 'habits') {
      const response = habitRoutes(request.method, id, resolvedAction, request)
      if (response) return response
    }

    return notFound(
      'not_found',
      `The fake API has no route for ${request.method} ${request.path}`,
    )
  }

  return {
    get areas() {
      return state.areas
    },
    get habits() {
      return state.habits
    },
    handle,
  }
}

/** Stub the global fetch with a fake API. */
export function stubFakeApi(api: FakeApi) {
  return stubApi({}, { fallback: api.handle })
}

function configFromInput(
  input: HabitInput,
  area: Area,
): Partial<Habit> & { area_id: number } {
  const quantity = input.tracking_mode === 'binary_quantity'
  return {
    name: input.name,
    description: input.description ?? null,
    area_id: area.id,
    area: {
      id: area.id,
      name: area.name,
      color: area.color,
      is_archived: area.is_archived,
    },
    weight: input.weight,
    tracking_mode: input.tracking_mode,
    quantity_unit: quantity ? (input.quantity_unit ?? null) : null,
    quantity_allows_decimal: quantity ? (input.quantity_allows_decimal ?? false) : false,
    schedule: scheduleReadFromInput(input),
  }
}

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** Mirrors the backend's derived quota and summary so the UI shows real text. */
function scheduleReadFromInput(input: HabitInput): Habit['schedule'] {
  const { type, weekdays, times_per_week: times } = input.schedule
  const selected = [...(weekdays ?? [])].sort((a, b) => a - b)

  if (type === 'daily') {
    return {
      type,
      weekdays: [],
      times_per_week: null,
      weekly_required_count: 7,
      summary: 'Every day',
    }
  }

  if (type === 'weekdays') {
    return {
      type,
      weekdays: selected,
      times_per_week: null,
      weekly_required_count: selected.length,
      summary: `${selected.map((day) => WEEKDAY_LABELS[day] ?? '?').join(', ')} (${selected.length} per week)`,
    }
  }

  return {
    type,
    weekdays: [],
    times_per_week: times ?? null,
    weekly_required_count: times ?? 0,
    summary: `${times ?? 0} per week`,
  }
}

/** Two plausible history entries so the history panel has something to show. */
function versionsOf(habit: Habit): HabitVersion[] {
  return [
    {
      habit_id: habit.id,
      version_number: 2,
      effective_from: '2026-09-20',
      created_at: '2026-09-20T10:00:00',
      name: habit.name,
      description: habit.description,
      area_id: habit.area_id,
      area: habit.area,
      weight: habit.weight,
      tracking_mode: habit.tracking_mode,
      quantity_unit: habit.quantity_unit,
      quantity_allows_decimal: habit.quantity_allows_decimal,
      schedule: habit.schedule,
    },
    {
      habit_id: habit.id,
      version_number: 1,
      effective_from: '2026-09-01',
      created_at: '2026-09-01T10:00:00',
      name: 'Original name',
      description: null,
      area_id: habit.area_id,
      area: habit.area,
      weight: 1,
      tracking_mode: 'binary',
      quantity_unit: null,
      quantity_allows_decimal: false,
      schedule: habit.schedule,
    },
  ]
}

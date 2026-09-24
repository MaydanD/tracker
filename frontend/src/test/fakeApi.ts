import type {
  Area,
  DailyEntry,
  DailyEntryInput,
  DayItem,
  DayState,
  Habit,
  HabitInput,
  HabitVersion,
} from '../api/types'
import { localTodayIso } from '../components/daily/dates'
import { jsonResponse, stubApi, type StubHandler, type StubRequest } from './fetchStub'
import { areaFixture, habitFixture } from './fixtures'
import { progressFixture } from './progressFixture'

/**
 * A deliberately small in-memory stand-in for the Tracker API.
 *
 * It covers the happy paths the pages drive (list with filters, create, update,
 * archive, unarchive, history, and the day screen). It does *not* try to be a
 * second server: only the rules the screens genuinely depend on are mirrored —
 * one record per habit and date, the future-date rule, and the skip-reason and
 * quantity rules. Tests that need the UI to handle a specific rejection stub that
 * response explicitly instead.
 */
export interface FakeApi {
  areas: Area[]
  habits: Habit[]
  entries: DailyEntry[]
  handle: StubHandler
}

export interface FakeApiOptions {
  areas?: Area[]
  habits?: Habit[]
  entries?: DailyEntry[]
}

function conflict(code: string, message: string): Response {
  return jsonResponse({ error: { code, message } }, 409)
}

function notFound(code: string, message: string): Response {
  return jsonResponse({ error: { code, message } }, 404)
}

function unprocessable(code: string, message: string): Response {
  return jsonResponse({ error: { code, message } }, 422)
}

function stamp(): string {
  return new Date().toISOString().slice(0, 19)
}

export function createFakeApi(options: FakeApiOptions = {}): FakeApi {
  const state = {
    areas: [...(options.areas ?? [])],
    habits: [...(options.habits ?? [])],
    entries: [...(options.entries ?? [])],
    nextAreaId: 100,
    nextHabitId: 100,
    nextEntryId: 100,
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

  function findEntry(habitId: number, entryDate: string): DailyEntry | undefined {
    return state.entries.find(
      (entry) => entry.habit_id === habitId && entry.entry_date === entryDate,
    )
  }

  /** The day screen: habits that existed then, with that date's record. */
  function readDay(entryDate: string): Response {
    const today = localTodayIso()
    const items: DayItem[] = state.habits
      .filter((habit) => habit.current_version.effective_from <= entryDate)
      .filter(
        (habit) =>
          !habit.is_archived ||
          findEntry(habit.id, entryDate) !== undefined,
      )
      .map((habit) => ({
        habit_id: habit.id,
        name: habit.name,
        area: habit.area,
        weight: habit.weight,
        tracking_mode: habit.tracking_mode,
        quantity_unit: habit.quantity_unit,
        quantity_allows_decimal: habit.quantity_allows_decimal,
        schedule: habit.schedule,
        is_archived: habit.is_archived,
        entry: findEntry(habit.id, entryDate) ?? null,
      }))
      .sort(
        (a, b) =>
          a.area.name.localeCompare(b.area.name) || a.name.localeCompare(b.name),
      )

    const day: DayState = {
      entry_date: entryDate,
      today,
      is_future: entryDate > today,
      items,
    }
    return jsonResponse(day)
  }

  function saveEntry(
    habitId: number,
    entryDate: string,
    input: DailyEntryInput,
  ): Response {
    const habit = findHabit(habitId)
    if (!habit) return notFound('habit_not_found', 'That habit does not exist.')
    if (habit.current_version.effective_from > entryDate) {
      return notFound(
        'configuration_not_found',
        'No configuration was effective for that habit on that date.',
      )
    }

    const today = localTodayIso()
    const status = input.status

    if (entryDate > today && status !== 'skipped') {
      return unprocessable(
        'future_entry_not_allowed',
        'Only a planned skip can be recorded for a future date.',
      )
    }

    const reason = (input.skip_reason ?? '').trim()
    if (status === 'skipped' && reason === '') {
      return unprocessable('skip_reason_required', 'Enter why the habit was skipped.')
    }
    if (status !== 'skipped' && reason !== '') {
      return unprocessable(
        'skip_reason_not_allowed',
        'A skip reason only applies to a deliberately skipped entry.',
      )
    }

    const quantity = input.quantity_value ?? null
    if (quantity !== null) {
      if (habit.tracking_mode !== 'binary_quantity') {
        return unprocessable('quantity_not_allowed', 'This habit does not track a quantity.')
      }
      if (!habit.quantity_allows_decimal && !Number.isInteger(quantity)) {
        return unprocessable(
          'quantity_decimal_not_allowed',
          'This habit is configured for whole numbers only.',
        )
      }
    }

    const note = (input.note ?? '').trim()
    const existing = findEntry(habitId, entryDate)
    const entry: DailyEntry = {
      id: existing?.id ?? state.nextEntryId++,
      habit_id: habitId,
      entry_date: entryDate,
      status,
      quantity_value: quantity,
      quantity_unit: habit.quantity_unit,
      skip_reason: status === 'skipped' ? reason : null,
      note: note === '' ? null : note,
      created_at: existing?.created_at ?? stamp(),
      updated_at: stamp(),
    }
    state.entries = [
      ...state.entries.filter(
        (candidate) =>
          candidate.habit_id !== habitId || candidate.entry_date !== entryDate,
      ),
      entry,
    ]
    return jsonResponse(entry)
  }

  function entryRoutes(
    method: string,
    habitId: number | null,
    entryDate: string | null,
    request: StubRequest,
  ): Response | null {
    if (habitId === null || entryDate === null) return null
    const habit = findHabit(habitId)
    if (!habit) return notFound('habit_not_found', 'That habit does not exist.')

    if (method === 'GET') {
      const entry = findEntry(habitId, entryDate)
      if (!entry) {
        return notFound('daily_entry_not_found', 'There is no entry for that habit on that date.')
      }
      return jsonResponse(entry)
    }

    if (method === 'PUT') {
      return saveEntry(habitId, entryDate, request.body as DailyEntryInput)
    }

    if (method === 'DELETE') {
      state.entries = state.entries.filter(
        (entry) => entry.habit_id !== habitId || entry.entry_date !== entryDate,
      )
      return {
        ok: true,
        status: 204,
        text: async () => '',
      } as unknown as Response
    }

    return null
  }

  function handle(request: StubRequest): Response {
    if (request.path.startsWith('/api/progress/days/')) {
      return jsonResponse(progressFixture(request.path.split('/').at(-1)))
    }
    const segments = request.path.split('/').filter((part) => part.length > 0)
    const [, resource, rawId, action = null, extra = null] = segments
    const id = rawId !== undefined && /^\d+$/.test(rawId) ? Number(rawId) : null
    // A path like /api/habits/archive has no numeric id, so treat the segment as
    // the action instead of an id.
    const resolvedAction = rawId !== undefined && id === null ? rawId : action

    if (resource === 'days') {
      if (rawId === undefined) {
        return notFound('not_found', 'A day request needs a date.')
      }
      if (action === 'state') {
        return jsonResponse({ state_date: rawId, today: localTodayIso(), state: null })
      }
      return readDay(rawId)
    }
    if (resource === 'areas') {
      const response = areaRoutes(request.method, id, resolvedAction, request)
      if (response) return response
    }
    if (resource === 'habits') {
      if (action === 'entries') {
        const response = entryRoutes(request.method, id, extra, request)
        if (response) return response
      } else {
        const response = habitRoutes(request.method, id, resolvedAction, request)
        if (response) return response
      }
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
    get entries() {
      return state.entries
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

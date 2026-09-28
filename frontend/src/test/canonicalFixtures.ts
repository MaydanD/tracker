import type { Area, Direction, Habit, ValueType } from '../api/types'
import { areaSummary, dailySchedule } from './fixtures'

/**
 * The shipped habit set, as the backend creates and returns it.
 *
 * Mirrors `backend/app/domain/canonical.py`: four spheres and 24 daily habits,
 * each with its own value scale, words, direction and importance. Screens must
 * read all of that from the API, so tests drive them with these fixtures instead
 * of hardcoding a scale somewhere in a component.
 */

const AREA_ROWS: Array<[string, string]> = [
  ['Тело', '#2f9e5f'],
  ['Развитие', '#4a7cc7'],
  ['Досуг', '#b5891b'],
  ['Питание и вещества', '#c2540a'],
]

/** Fresh copies, so a test that edits a sphere cannot leak into the next one. */
export function canonicalAreas(): Area[] {
  return AREA_ROWS.map(([name, color], index) => ({
    id: index + 1,
    name,
    color,
    is_archived: false,
    archived_at: null,
    created_at: '2026-09-01T10:00:00',
    updated_at: '2026-09-01T10:00:00',
  }))
}

const AREA_ID: Record<string, number> = {
  body: 1,
  development: 2,
  leisure: 3,
  nutrition: 4,
}

const ZERO_MUCH = ['0', 'мало', 'нормально', 'много']
const NO_YES = ['нет', 'да']

/** A compact (key, area, name, type, direction, labels) row per habit. */
const DEFINITIONS: Array<
  [string, string, string, ValueType, Direction, string[]]
> = [
  ['body.exercise', 'body', 'Зарядка', 'binary', 'positive', NO_YES],
  ['body.workout', 'body', 'Тренировка', 'binary', 'positive', NO_YES],
  ['body.walk', 'body', 'Прогулка', 'ordinal_4', 'positive', ZERO_MUCH],
  ['body.bicycle', 'body', 'Велосипед', 'ordinal_4', 'positive', ZERO_MUCH],
  ['body.mood', 'body', 'Настроение', 'ordinal_4', 'positive', ['ужас', 'плохо', 'норм', 'хорошо']],
  ['body.energy', 'body', 'Энергия', 'ordinal_4', 'positive', ['нет сил', 'мало', 'норм', 'много']],
  ['body.sleep_quality', 'body', 'Качество сна', 'ordinal_4', 'positive', ['ужас', 'плохо', 'норм', 'хорошо']],
  ['body.symptoms', 'body', 'Симптомы заболевания', 'ordinal_4', 'negative', ['нет', 'слабые', 'заметные', 'сильные']],
  ['body.sex', 'body', 'Секс', 'binary', 'neutral', NO_YES],
  ['body.masturbation', 'body', 'Мастурбация', 'binary', 'neutral', NO_YES],
  ['development.reading', 'development', 'Чтение', 'ordinal_4', 'positive', ZERO_MUCH],
  ['development.study', 'development', 'Учёба', 'ordinal_4', 'positive', ZERO_MUCH],
  ['development.projects', 'development', 'Вайбкодинг / свои проекты', 'ordinal_4', 'positive', ZERO_MUCH],
  ['development.work', 'development', 'Работа', 'ordinal_4', 'neutral', ZERO_MUCH],
  ['development.tasks', 'development', 'Дела', 'ordinal_4', 'positive', ZERO_MUCH],
  ['leisure.friends', 'leisure', 'Общение с друзьями', 'ordinal_4', 'positive', ZERO_MUCH],
  ['leisure.games', 'leisure', 'Игры', 'ordinal_4', 'negative', ZERO_MUCH],
  ['leisure.movies', 'leisure', 'Кино / сериалы', 'ordinal_4', 'neutral', ZERO_MUCH],
  ['leisure.computer', 'leisure', 'Просто сидел за компом', 'ordinal_4', 'neutral', ZERO_MUCH],
  ['nutrition.normal_food', 'nutrition', 'Нормальное питание', 'ordinal_4', 'positive', ['0', 'мало', 'нормально', 'хорошо']],
  ['nutrition.junk_food', 'nutrition', 'Вредная еда', 'ordinal_4', 'negative', ['0', 'немного', 'нормально', 'много']],
  ['nutrition.overeating', 'nutrition', 'Переедание', 'ordinal_4', 'negative', ['0', 'немного', 'заметно', 'сильно']],
  ['nutrition.coffee', 'nutrition', 'Кофе', 'ordinal_4', 'neutral', ['0', '1 кофе', '2 кофе', '3+ кофе']],
  ['nutrition.alcohol', 'nutrition', 'Алкоголь', 'ordinal_4', 'negative', ['0', 'немного', 'нормально', 'много']],
]

/** The 24 shipped habits, in their fixed display order. */
export function canonicalHabits(): Habit[] {
  return DEFINITIONS.map(([key, areaKey, name, valueType, direction, labels], index) => ({
    id: index + 1,
    key,
    name,
    description: null,
    area_id: AREA_ID[areaKey]!,
    area: areaSummary(canonicalAreas()[AREA_ID[areaKey]! - 1]!),
    // Tracker never decides what matters to the user: everything ships ordinary.
    importance: 'normal' as const,
    weight: 1,
    tracking_mode: 'binary' as const,
    quantity_unit: null,
    quantity_allows_decimal: false,
    value_type: valueType,
    value_labels: labels,
    direction,
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
  }))
}

/** The id of a shipped habit, so a test can record an answer for it. */
export function canonicalHabitId(key: string): number {
  const index = DEFINITIONS.findIndex((row) => row[0] === key)
  if (index === -1) throw new Error(`No canonical habit ${key}`)
  return index + 1
}

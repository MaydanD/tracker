/**
 * Presentation vocabulary for habit configuration.
 *
 * Weekday numbers must match the API contract: ISO days, 0 = Monday … 6 = Sunday.
 * The importance, mark-kind and direction labels are product wording
 * (PROJECT-SPEC.md §4.2, §4.3); the underlying rules stay enforced by the
 * backend domain layer.
 */

import type { Direction, Importance, ScheduleRead, ValueType } from '../../api/types'

export interface Option<T> {
  value: T
  label: string
  hint?: string
}

export const WEEKDAY_OPTIONS: Option<number>[] = [
  { value: 0, label: 'Пн' },
  { value: 1, label: 'Вт' },
  { value: 2, label: 'Ср' },
  { value: 3, label: 'Чт' },
  { value: 4, label: 'Пт' },
  { value: 5, label: 'Сб' },
  { value: 6, label: 'Вс' },
]

/**
 * Importance: how much the habit matters to the user.
 *
 * Not to be confused with direction, which says which end of a value scale is
 * good. Importance is independent of the historical score weight.
 */
export const IMPORTANCE_OPTIONS: Option<Importance>[] = [
  { value: 'low', label: 'Низкая' },
  { value: 'normal', label: 'Обычная' },
  { value: 'high', label: 'Высокая' },
]

/** Historical score coefficients, unchanged. */
export const WEIGHT_OPTIONS: Option<number>[] = [
  { value: 1, label: 'Обычная' },
  { value: 2, label: 'Важная' },
  { value: 3, label: 'Ключевая' },
]

/**
 * How a day is answered.
 *
 * Completion answers *whether* the habit happened; a value scale answers *how
 * much*, on a scale of two (да/нет) or four (0…3) positions.
 */
export type MarkKind = 'completion' | 'quantity' | 'binary' | 'ordinal_4'

export const MARK_KIND_OPTIONS: Option<MarkKind>[] = [
  { value: 'completion', label: 'Выполнено / пропущено' },
  {
    value: 'quantity',
    label: 'Выполнено и количество',
    hint: 'Можно просто отметить выполнение или дополнительно указать количество.',
  },
  {
    value: 'binary',
    label: 'Да / нет',
    hint: 'Два варианта ответа, например «нет» и «да».',
  },
  {
    value: 'ordinal_4',
    label: 'Шкала из четырёх значений',
    hint: 'Например «0 / мало / нормально / много».',
  },
]

/** The value scale a mark kind is answered on, or null for a completion. */
export function valueTypeOf(kind: MarkKind): ValueType | null {
  return kind === 'binary' || kind === 'ordinal_4' ? kind : null
}

/** How many positions a scale has (2 or 4). */
export function scaleLengthOf(kind: MarkKind): number {
  return kind === 'binary' ? 2 : 4
}

/** Words a scale starts with; every one of them is editable in the editor. */
export const DEFAULT_SCALE_LABELS: Record<ValueType, string[]> = {
  binary: ['нет', 'да'],
  ordinal_4: ['0', 'мало', 'нормально', 'много'],
}

/**
 * Which end of a scale is good.
 *
 * Analytic metadata: it says nothing about how much the habit matters (that is
 * importance). There is deliberately no default that flatters the habit — a new
 * value habit starts at «без оценки лучше/хуже», because guessing «больше —
 * лучше» would quietly bias a future score.
 */
export const DIRECTION_OPTIONS: Option<Direction>[] = [
  { value: 'neutral', label: 'Без оценки лучше/хуже' },
  { value: 'positive', label: 'Чем больше, тем лучше' },
  { value: 'negative', label: 'Чем больше, тем хуже' },
]

/** The completion side of a mark, as the daily-state cards still use it. */
export const TRACKING_MODE_OPTIONS: Option<string>[] = [
  { value: 'binary', label: 'Отметка выполнения' },
  {
    value: 'binary_quantity',
    label: 'Отметка и количество',
    hint: 'Можно просто отметить выполнение или дополнительно указать количество.',
  },
]

export const SCHEDULE_TYPE_OPTIONS: Option<string>[] = [
  { value: 'daily', label: 'Каждый день' },
  { value: 'weekdays', label: 'По дням недели', hint: 'Выберите удобные дни.' },
  {
    value: 'times_per_week',
    label: 'Несколько раз в неделю',
    hint: 'Без фиксированных дней. Неделя — с понедельника по воскресенье.',
  },
]

export function weightLabel(weight: number): string {
  return WEIGHT_OPTIONS.find((option) => option.value === weight)?.label ?? String(weight)
}

export function importanceLabel(importance: Importance): string {
  return (
    IMPORTANCE_OPTIONS.find((option) => option.value === importance)?.label ?? importance
  )
}

export function markKindLabel(kind: MarkKind): string {
  return MARK_KIND_OPTIONS.find((option) => option.value === kind)?.label ?? kind
}

export function markKindOf(
  trackingMode: string,
  valueType: ValueType | null | undefined,
): MarkKind {
  if (valueType === 'binary' || valueType === 'ordinal_4') return valueType
  return trackingMode === 'binary_quantity' ? 'quantity' : 'completion'
}

export function trackingModeLabel(
  mode: string,
  unit: string | null,
  valueType: ValueType | null = null,
): string {
  if (valueType === 'binary') return 'Ответ: да / нет'
  if (valueType === 'ordinal_4') return 'Ответ: шкала 0–3'
  if (mode === 'binary_quantity') {
    return unit ? `Количество${unitLabel(unit)}` : 'Количество'
  }
  return 'Отметка выполнения'
}

export function unitLabel(unit: string): string {
  return ` (${unit})`
}

/** Local wording only; the backend remains the authority for weekly quotas. */
export function scheduleLabel(schedule: ScheduleRead): string {
  if (schedule.type === 'daily') return 'Каждый день'
  const count = schedule.weekly_required_count
  const quota = `${count} ${count >= 2 && count <= 4 ? 'раза' : 'раз'} в неделю`
  if (schedule.type === 'weekdays') {
    const days = schedule.weekdays.map((day) => WEEKDAY_OPTIONS[day]?.label).join(', ')
    return `${days} (${quota})`
  }
  return quota
}

export function configurationDateLabel(date: string): string {
  // These are calendar dates: no UTC/local conversion may shift their day.
  return date.split('-').reverse().join('.')
}

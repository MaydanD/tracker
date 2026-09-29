/**
 * Presentation vocabulary for habit configuration.
 *
 * Weekday numbers must match the API contract: ISO days, 0 = Monday … 6 = Sunday.
 * The weight, mark-kind and direction labels are product wording
 * (PROJECT-SPEC.md §4.2, §4.3); the underlying rules stay enforced by the
 * backend domain layer.
 */

import type { Direction, ScheduleRead, ValueType } from '../../api/types'

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
 * Важность — the one user-facing "how much does this habit matter" control.
 *
 * It is the historical score coefficient (1 ordinary, 2 important, 3 key), and
 * it is the only such control the user is asked to set. The model's separate
 * `importance` column is kept for backwards compatibility and for the analytics
 * catalogue, but it is not a second regulator the user has to choose.
 */
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
 *
 * `quantity` is legacy: it is only offered while editing a habit that already
 * tracks a quantity, so existing data stays editable without new habits ever
 * choosing it. A plain 0 / 1 / 2 / 3 scale covers what it used to express.
 */
export type MarkKind = 'completion' | 'quantity' | 'binary' | 'ordinal_4'

/** Offered for a new habit: completion, да/нет, or a four-value scale. */
export const MARK_KIND_OPTIONS: Option<MarkKind>[] = [
  { value: 'completion', label: 'Выполнено / пропущено' },
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

/**
 * The mark kinds a habit may be given.
 *
 * «Выполнено и количество» is a legacy configuration: it stays offered for a
 * habit that already uses it (so its unit and decimal rule remain editable)
 * and is never offered for a new one.
 */
export function markKindOptions(kind: MarkKind): Option<MarkKind>[] {
  if (kind !== 'quantity') return MARK_KIND_OPTIONS
  return [
    MARK_KIND_OPTIONS[0]!,
    {
      value: 'quantity',
      label: 'Выполнено и количество (устаревший тип)',
      hint: 'Оставлен для привычек, созданных раньше. Новая привычка вместо него использует шкалу.',
    },
    ...MARK_KIND_OPTIONS.slice(1),
  ]
}

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
 * Which end of a scale is good — «Полезная / Вредная / Нейтральная».
 *
 * Analytic metadata: it says nothing about how much the habit matters (that is
 * importance/weight). There is deliberately no default that flatters the habit —
 * a new value habit starts neutral, because guessing «больше — лучше» would
 * quietly bias a future score.
 */
export const DIRECTION_OPTIONS: Option<Direction>[] = [
  { value: 'positive', label: 'Полезная — больше значит лучше' },
  { value: 'negative', label: 'Вредная — меньше значит лучше' },
  { value: 'neutral', label: 'Нейтральная — просто отслеживание' },
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

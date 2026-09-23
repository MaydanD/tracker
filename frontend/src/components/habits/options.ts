/**
 * Presentation vocabulary for habit configuration.
 *
 * Weekday numbers must match the API contract: ISO days, 0 = Monday … 6 = Sunday.
 * The weight and tracking-mode labels are product wording (PROJECT-SPEC.md §4.2,
 * §4.3); the underlying rules stay enforced by the backend domain layer.
 */

import type { ScheduleRead } from '../../api/types'

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

export const WEIGHT_OPTIONS: Option<number>[] = [
  { value: 1, label: 'Обычная' },
  { value: 2, label: 'Важная' },
  { value: 3, label: 'Ключевая' },
]

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

export function trackingModeLabel(mode: string, unit: string | null): string {
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

/**
 * Russian presentation vocabulary for Stage 11 records.
 *
 * Formatting only. No statistic is recomputed here: the numbers arrive ready from
 * the backend, and a missing value is always shown as a dash rather than a zero.
 */

import type { AchievementCategory, RecordUnit, RecordsSummary } from '../../api/records'
import { formatShortDateLabel } from '../../utils/dateUtils'

export const CATEGORY_LABELS: Record<AchievementCategory, string> = {
  streak: 'Серии',
  consistency: 'Стабильность',
  tracking: 'Трекинг',
  daily_state: 'Состояние дня',
  experiments: 'Эксперименты',
  insights: 'Инсайты',
}

/** Category display order, so grouped lists never jump around. */
export const CATEGORY_ORDER: AchievementCategory[] = [
  'streak',
  'consistency',
  'tracking',
  'daily_state',
  'experiments',
  'insights',
]

const DAY_WORDS = { one: 'день', few: 'дня', many: 'дней', other: 'дней' }
const WEEK_WORDS = { one: 'неделя', few: 'недели', many: 'недель', other: 'недель' }

/** Pluralised streak value without any emoji, e.g. `28 дней`. */
export function streakValue(count: number, unit: RecordUnit): string {
  const plural = new Intl.PluralRules('ru-RU').select(count)
  const words = unit === 'days' ? DAY_WORDS : WEEK_WORDS
  const word = words[plural as keyof typeof words] ?? words.other
  return `${count} ${word}`
}

export function pluralDays(count: number): string {
  return streakValue(count, 'days')
}

/** `71%`, or a dash when nothing was recorded. */
export function formatPercent(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)}%`
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}

/** `12.09.2026 — 18.09.2026`. */
export function formatRange(start: string, end: string): string {
  return `${formatShortDateLabel(start)} — ${formatShortDateLabel(end)}`
}

/** `Сентябрь 2026` for a month range that starts on the first day. */
export function formatMonth(iso: string): string {
  const [year, month] = iso.split('-').map(Number)
  const names = [
    'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
    'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
  ]
  const name = names[(month ?? 1) - 1] ?? ''
  return `${name.charAt(0).toUpperCase()}${name.slice(1)} ${year}`
}

/** Coverage like `7 из 7 дней данных`. */
export function formatCoverage(observed: number, calendar: number): string {
  return `${formatCount(observed)} из ${formatCount(calendar)} дней данных`
}

/**
 * Honest summary lines: only the numbers that genuinely exist are shown, and an
 * empty account reads as "no records yet", never as a failure.
 */
export function summaryLines(summary: RecordsSummary): string[] {
  const lines: string[] = []
  lines.push(
    summary.tracked_days === 0
      ? 'Трекинг: пока нет записей'
      : `Трекинг: ${streakValue(summary.tracked_days, 'days')}`,
  )
  lines.push(`Выполнений привычек: ${formatCount(summary.habit_completions)}`)
  lines.push(`Завершено экспериментов: ${formatCount(summary.completed_experiments)}`)
  return lines
}

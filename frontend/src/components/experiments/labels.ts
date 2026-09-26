/**
 * Russian presentation vocabulary for Stage 10 experiments.
 *
 * Formatting only: every number (coverage, deltas, ratios) is computed by the
 * backend, and the wording deliberately stays descriptive — never causal.
 */

import { formatDayLabel } from '../daily/dates'
import type {
  Experiment,
  ExperimentPhase,
  ExperimentStatus,
  HabitPeriod,
  PeriodCoverage,
  StateComparison,
  StatePeriod,
} from '../../api/experiments'

export const STATUS_LABELS: Record<ExperimentStatus, string> = {
  scheduled: 'Запланирован',
  active: 'Идёт',
  completed: 'Завершён',
  cancelled: 'Отменён',
}

export const STAGE_LABELS: Record<'before' | 'during' | 'after', string> = {
  before: 'До',
  during: 'Эксперимент',
  after: 'После',
}

/** Short human date, e.g. `1 октября 2026`. */
export function formatDate(iso: string): string {
  return formatDayLabel(iso).replace(/,\s*\S+$/, '')
}

export function formatRange(start: string, end: string): string {
  return `${formatDate(start)} — ${formatDate(end)}`
}

/** Whole percentage points, e.g. `71%`. */
export function formatPercent(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)}%`
}

/** Signed percentage-point change, e.g. `+14 п.п.`. */
export function formatPoints(value: number | null): string {
  if (value === null) return '—'
  const rounded = Math.round(value)
  const sign = rounded > 0 ? '+' : ''
  return `${sign}${rounded} п.п.`
}

/** Signed average value with one decimal, e.g. `+0.6`. */
export function formatAverage(value: number | null): string {
  if (value === null) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}`
}

export function formatValue(value: number | null): string {
  return value === null ? '—' : value.toFixed(1)
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}

/** `12 из 14 дней данных`, with the same honest wording everywhere. */
export function formatCoverage(coverage: PeriodCoverage): string {
  return `${formatCount(coverage.observed_days)} из ${formatCount(coverage.calendar_days)} дней данных`
}

export function coverageRatio(coverage: PeriodCoverage): number | null {
  return coverage.coverage
}

/** Phase sentence shown on list and detail, driven by the backend phase. */
export function formatPhase(experiment: Experiment): string {
  const { phase } = experiment
  if (phase.status === 'scheduled') {
    const days = phase.days_until_start ?? 0
    return `До начала — ${pluralDays(days)}`
  }
  if (phase.status === 'active') {
    return `Идёт — день ${phase.day_index ?? 1} из ${phase.days_total ?? 0}`
  }
  if (phase.status === 'cancelled') {
    return `Остановлен — ${phase.after_collected_days} из ${phase.after_total_days} дней после`
  }
  return `Завершён — собрано ${phase.after_collected_days} из ${phase.after_total_days} дней после`
}

/** Russian day pluralisation: 1 день, 2 дня, 5 дней. */
export function pluralDays(count: number): string {
  const absolute = Math.abs(count)
  const mod10 = absolute % 10
  const mod100 = absolute % 100
  if (mod10 === 1 && mod100 !== 11) return `${count} день`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return `${count} дня`
  return `${count} дней`
}

/** Habit ratio cell: `—` when there was nothing required to compare. */
export function formatHabitRatio(period: HabitPeriod): string {
  return formatPercent(period.completion_ratio)
}

export function statePeriodText(period: StatePeriod, kind: string): string {
  if (period.value === null) return '—'
  if (kind === 'boolean') return `${Math.round(period.value * 100)}%`
  return period.value.toFixed(1)
}

export function stateDeltaText(comparison: StateComparison): string {
  if (comparison.delta_during_vs_before === null) return '—'
  if (comparison.kind === 'boolean') {
    const points = comparison.delta_during_vs_before * 100
    return formatPoints(points)
  }
  return formatAverage(comparison.delta_during_vs_before)
}

/** Experiment durations the UI offers, matching the backend window rule. */
export function durationDays(experiment: Experiment): number {
  const start = Date.parse(`${experiment.start_date}T00:00:00Z`)
  const end = Date.parse(`${experiment.end_date}T00:00:00Z`)
  return Math.round((end - start) / 86_400_000) + 1
}

export function phaseDescription(phase: ExperimentPhase): string {
  if (phase.status === 'scheduled') return 'Эксперимент ещё не начался.'
  if (phase.status === 'active') return 'Эксперимент идёт прямо сейчас.'
  if (phase.status === 'cancelled') return 'Эксперимент остановлен раньше срока.'
  return 'Эксперимент завершён, период «после» набирается.'
}

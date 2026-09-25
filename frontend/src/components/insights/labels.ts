/**
 * Russian presentation vocabulary for Stage 8.
 *
 * Every label is a translation of a *backend* code. The UI never invents a
 * verdict, a confidence level or a caveat; it only names the one it received.
 */

import type {
  ConfidenceLevel,
  GuardrailVerdict,
  InsightStatus,
} from '../../api/insights'

export const STATUS_LABELS: Record<InsightStatus, string> = {
  preliminary: 'Предварительно',
  stable: 'Стабильно',
  well_supported: 'Хорошо подтверждено',
  warning: 'Есть ограничения',
  hidden: 'Не прошло проверки',
  not_evaluable: 'Недостаточно данных',
}

export const CONFIDENCE_LABELS: Record<ConfidenceLevel, string> = {
  preliminary: 'Предварительно',
  stable: 'Стабильно',
  well_supported: 'Хорошо подтверждено',
}

export const CONFIDENCE_EXPLANATIONS: Record<ConfidenceLevel, string> = {
  preliminary: 'Предварительно: связи достаточно для первого сигнала, но данных пока мало.',
  stable: 'Стабильно: связь повторяется минимум на двух участках вашей истории.',
  well_supported:
    'Хорошо подтверждено: данных достаточно, покрытие высокое, а направление связи сохраняется на всей истории.',
}

export const CONFIDENCE_NONE_EXPLANATION =
  'Уровень подтверждённости не определён: для расчёта не хватило данных.'

export const VERDICT_LABELS: Record<GuardrailVerdict, string> = {
  pass: 'Проверки пройдены',
  pass_with_warnings: 'Есть ограничения',
  blocked: 'Не прошло проверки',
  not_evaluable: 'Недостаточно данных для проверки',
}

export const DIRECTION_LABELS: Record<string, string> = {
  positive: 'положительное',
  negative: 'отрицательное',
  near_zero: 'слабое',
}

export const STRENGTH_LABELS: Record<string, string> = {
  negligible: 'пренебрежимо малая',
  weak: 'слабая',
  moderate: 'умеренная',
  strong: 'сильная',
}

export const METHOD_LABELS: Record<string, string> = {
  spearman: 'ранговая корреляция (Спирмен)',
  pearson: 'корреляция (Пирсон)',
  point_biserial: 'связь отметки и значения',
  phi: 'связь двух отметок',
}

export const VARIABLE_TYPE_LABELS: Record<string, string> = {
  numeric: 'число',
  ordinal: 'оценка',
  boolean: 'отметка',
  categorical: 'категория',
}

export const SEGMENT_LABELS: Record<string, string> = {
  early: 'Ранний период',
  middle: 'Средний период',
  recent: 'Недавний период',
}

export const RELATION_TO_FULL_LABELS: Record<string, string> = {
  same: 'как во всей истории',
  near_zero: 'слабее',
  opposite: 'другое направление',
  insufficient: 'недостаточно данных',
}

export const CHECK_LABELS: Record<string, string> = {
  sample_size: 'Число наблюдений',
  coverage: 'Покрытие',
  group_balance: 'Баланс групп',
  effect_size: 'Величина связи',
  weekday_control: 'Контроль дня недели',
  temporal_stability: 'Устойчивость во времени',
  multiple_comparisons: 'Контроль ложных открытий',
}

export const CHECK_STATUS_LABELS: Record<string, string> = {
  passed: 'пройдено',
  failed: 'не пройдено',
  not_applicable: 'не применяется',
  not_evaluable: 'не проверено',
}

export const WEEKDAY_STATUS_LABELS: Record<string, string> = {
  passed: 'связь сохраняется',
  failed: 'связь не сохраняется',
  not_applicable: 'не применяется',
  not_evaluable: 'не проверено',
}

export const METHOD_AGREEMENT_LABELS: Record<string, string> = {
  single_method: 'один метод расчёта',
  agree: 'методы согласны',
  disagree: 'методы расходятся',
  partial: 'методы согласны частично',
  unavailable: 'сопоставление недоступно',
}

export const AVAILABILITY_HINTS: Record<string, string> = {
  no_data:
    'Для этих дат нет заполненных показателей. Отметьте привычки или заполните состояние дня в разделе «Итоги дня».',
  insufficient_data:
    'Как только появится больше совместных наблюдений, здесь появятся первые сигналы.',
  no_guardrails_passed:
    'Можно посмотреть, какие связи не прошли проверки, выбрав «Скрытые проверками».',
  preliminary_only: 'Это только первые сигналы: они могут измениться, когда данных станет больше.',
  ok: '',
}

/** `0.42` → `+0,42`; sign is part of the reading, never only the colour. */
export function formatCoefficient(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const fixed = value.toFixed(2).replace('-0.00', '0.00')
  return (value > 0 ? '+' : '') + fixed.replace('.', ',')
}

export function formatRatio(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toLocaleString('ru-RU', { maximumFractionDigits: 0 })}%`
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString('ru-RU')
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  })
}

/** Lag chip and sentence timing come from the backend; only the unit is named here. */
export function formatLag(lag: number, unit: 'day' | 'week' | null): string {
  if (lag === 0) return unit === 'week' ? 'та же неделя' : 'те же дни'
  const amount = Math.abs(lag)
  const dayWord = amount === 1 ? 'день' : amount < 5 ? 'дня' : 'дней'
  const weekWord = amount === 1 ? 'неделю' : amount < 5 ? 'недели' : 'недель'
  const distance = unit === 'week' ? `${amount} ${weekWord}` : `${amount} ${dayWord}`
  return lag > 0 ? `через ${distance}` : `обратный порядок: ${distance}`
}

/**
 * Stage 8 fixtures: shapes copied from real backend responses.
 *
 * They are typed with the API contract, so a contract change fails the build
 * instead of silently drifting away from the server.
 */

import type {
  InsightAnalyticsRead,
  InsightCandidateRead,
  InsightCatalogueRead,
  InsightChartRead,
  InsightDetailRead,
  InsightSnapshotRead,
  InsightVariableRead,
} from '../api/insights'

export const TODAY = '2026-09-25'
export const PERIOD = { start: '2026-06-28', end: '2026-09-25' }

export function variable(
  key: string,
  label: string,
  type = 'ordinal',
  extra: Partial<InsightVariableRead> = {},
): InsightVariableRead {
  return {
    key,
    label,
    type,
    grain: 'daily',
    source: 'daily_states',
    missing_semantics: 'source_missing: нет записи.',
    categories: [],
    minimum: type === 'boolean' ? null : 1,
    maximum: type === 'boolean' ? null : 5,
    habit_id: null,
    ...extra,
  }
}

const ENERGY = variable('state.energy', 'Энергия')
const MOOD = variable('state.mood', 'Настроение')
const SCORE = variable('daily.score', 'Процент выполнения', 'numeric')
const TRAINING = variable('habit.1.daily.completion', 'Тренировка', 'boolean', { habit_id: 1 })

function alternatives(count = 15) {
  return Array.from({ length: count }, (_, index) => {
    const lag = index < 8 ? index : index - 7
    return {
      fingerprint: String(index).padStart(64, 'a'),
      timing: `${index < 8 ? 'Энергия — Настроение' : 'Настроение — Энергия'}: ${lag === 0 ? 'В те же дни' : `Через ${lag} дн.`}`,
      lag,
      is_representative: index === 0,
      orientation: (lag === 0 ? 'same_period' : 'x_earlier') as 'same_period' | 'x_earlier' | 'x_later',
      guardrail: (index % 5 === 4 ? 'blocked' : 'pass') as 'pass' | 'blocked',
      status: (index % 5 === 4 ? 'hidden' : 'well_supported') as 'hidden' | 'well_supported',
      confidence: (index % 5 === 4 ? 'stable' : 'well_supported') as 'stable' | 'well_supported',
      coefficient: index % 5 === 4 ? 0.02 : 0.6 - index * 0.02,
      absolute_coefficient: index % 5 === 4 ? 0.02 : 0.6 - index * 0.02,
      direction: 'positive',
      n: 90,
      pair_coverage: 0.98,
      blocking_reasons: index % 5 === 4 ? ['below_effect_threshold'] : [],
      warnings: [],
    }
  })
}

export function candidate(overrides: Partial<InsightCandidateRead> = {}): InsightCandidateRead {
  const base: InsightCandidateRead = {
    fingerprint: 'a'.repeat(64),
    kind: 'association',
    status: 'well_supported',
    orientation: 'same_period',
    x: ENERGY,
    y: MOOD,
    grain: 'daily',
    lag: 0,
    lag_unit: 'day',
    target_period: PERIOD,
    text: {
      statement: 'Чем выше был показатель «Энергия», тем обычно выше было значение «Настроение».',
      timing: 'В те же дни',
      prefix: 'Эта связь устойчиво повторяется в вашей истории: ',
      full:
        'Эта связь устойчиво повторяется в вашей истории: чем выше был показатель «Энергия», ' +
        'тем обычно выше было значение «Настроение».',
      template_version: '1',
    },
    relationship: {
      method: 'spearman',
      coefficient: 0.62,
      absolute_coefficient: 0.62,
      direction: 'positive',
      strength: 'strong',
      n: 90,
      status: 'ok',
      reason: null,
      limitations: [],
      method_agreement: 'single_method',
    },
    guardrail: {
      verdict: 'pass',
      policy_version: '1',
      family_mode: 'discovery',
      family_size: 225,
      tested_size: 225,
      family_rank: 2,
      threshold: 0.1,
      raw_p_value: 0.0001,
      adjusted_q_value: 0.002,
      blocking_reasons: [],
      warnings: [],
      confidence_capped: false,
    },
    confidence: { status: 'evaluated', level: 'well_supported', policy_version: '1', reason: null },
    evidence: {
      sample: {
        n: 90,
        requested_count: 92,
        eligible_count: 92,
        excluded_count: 0,
        missing_count: 2,
        unavailable_count: 2,
        pair_coverage: 0.98,
        minimum_n_met: true,
        stable_n_met: true,
        well_supported_n_met: true,
      },
      coverage: {
        pair_coverage: 0.98,
        eligible_count: 92,
        stable_coverage_met: true,
        well_supported_coverage_met: true,
        segment_pair_coverage: [1, 1, 0.93],
        minimum_segment_coverage: 0.93,
        maximum_segment_coverage: 1,
        coverage_imbalance: 0.07,
        low_coverage: false,
        segment_instability: false,
      },
      stability: {
        segment_count: 3,
        analyzable_segment_count: 3,
        insufficient_segment_count: 0,
        same_direction_count: 3,
        near_zero_count: 0,
        opposite_direction_count: 0,
        coefficients: [0.61, 0.63, 0.6],
        median_coefficient: 0.61,
        median_absolute_coefficient: 0.61,
        coefficient_range: 0.03,
        maximum_deviation_from_full: 0.02,
        direction_consistent: true,
        meaningful_reversal: false,
        magnitude_stable: true,
        magnitude_well_supported: true,
      },
      methods: {
        primary_method: 'spearman',
        methods: ['spearman'],
        coefficients: [0.62],
        directions: ['positive'],
        agreement: 'single_method',
      },
      effect: {
        method: 'spearman',
        coefficient: 0.62,
        absolute_coefficient: 0.62,
        minimum_absolute_effect: 0.15,
        meets_minimum: true,
        group: null,
      },
      weekday: {
        status: 'passed',
        outcome: 'retained',
        weekday_basis: 'y_target_date',
        strata_count: 7,
        usable_strata_count: 7,
        observations: 90,
        raw_coefficient: 0.62,
        adjusted_coefficient: 0.61,
        absolute_difference: 0.01,
        relative_attenuation: 0.02,
        direction_change: false,
      },
      checks: [
        { name: 'sample_size', status: 'passed', blocking: false, detail: 'sufficient_sample', observed: 90, threshold: 10 },
        { name: 'coverage', status: 'passed', blocking: false, detail: 'sufficient_coverage', observed: 0.98, threshold: 0.4 },
        { name: 'effect_size', status: 'passed', blocking: false, detail: 'meaningful_effect', observed: 0.62, threshold: 0.15 },
        { name: 'weekday_control', status: 'passed', blocking: false, detail: 'weekday_control_passed', observed: null, threshold: null },
        { name: 'temporal_stability', status: 'passed', blocking: false, detail: 'temporally_consistent', observed: 3, threshold: 3 },
        { name: 'multiple_comparisons', status: 'passed', blocking: false, detail: 'passes_fdr', observed: 0.002, threshold: 0.1 },
      ],
      segments: [
        { index: 0, name: 'early', period: { start: '2026-06-28', end: '2026-07-27' }, coefficient: 0.61, direction: 'positive', strength: 'strong', relation_to_full: 'same' },
        { index: 1, name: 'middle', period: { start: '2026-07-28', end: '2026-08-26' }, coefficient: 0.63, direction: 'positive', strength: 'strong', relation_to_full: 'same' },
        { index: 2, name: 'recent', period: { start: '2026-08-27', end: '2026-09-25' }, coefficient: 0.6, direction: 'positive', strength: 'strong', relation_to_full: 'same' },
      ],
    },
    caveats: [
      { code: 'autocorrelation_possible', label: 'Соседние дни могут быть статистически зависимы', message: 'Объём независимой информации может быть меньше числа дней.', detail: 'Возможна автокорреляция.', severity: 'info' },
      { code: 'association_not_causation', label: 'Связь не означает причинность', message: 'Наблюдаемая связь не доказывает, что один показатель вызывает другой.', detail: 'Связь не причинность.', severity: 'info' },
      { code: 'representative_lag_only', label: 'Показана одна задержка', message: 'Для этой пары проверялись несколько задержек.', detail: 'Для этой пары проверялись несколько задержек.', severity: 'info' },
    ],
    alternatives: alternatives(),
    in_default_feed: true,
    first_seen: null,
  }
  return { ...base, ...overrides }
}

/** A boolean habit pair: group comparison instead of a scatter. */
export function booleanCandidate(): InsightCandidateRead {
  return candidate({
    fingerprint: 'b'.repeat(64),
    status: 'warning',
    x: SCORE,
    y: TRAINING,
    lag: 3,
    lag_unit: 'day',
    text: {
      statement: 'После дней с более высоким показателем «Процент выполнения», через три дня «Тренировка» отмечалось чаще.',
      timing: 'Через три дня',
      prefix: 'Пока есть предварительный сигнал: ',
      full:
        'Пока есть предварительный сигнал: после дней с более высоким показателем «Процент выполнения», ' +
        'через три дня «Тренировка» отмечалось чаще.',
      template_version: '1',
    },
    guardrail: {
      verdict: 'pass_with_warnings',
      policy_version: '1',
      family_mode: 'discovery',
      family_size: 420,
      tested_size: 420,
      family_rank: 12,
      threshold: 0.1,
      raw_p_value: 0.01,
      adjusted_q_value: 0.03,
      blocking_reasons: [],
      warnings: [{ code: 'moderate_coverage', label: 'Умеренное покрытие', message: 'Часть подходящих дней не имеет обоих показателей.' }],
      confidence_capped: false,
    },
    confidence: { status: 'evaluated', level: 'preliminary', policy_version: '1', reason: null },
    relationship: {
      method: 'point_biserial',
      coefficient: -0.31,
      absolute_coefficient: 0.31,
      direction: 'negative',
      strength: 'moderate',
      n: 88,
      status: 'ok',
      reason: null,
      limitations: [],
      method_agreement: 'single_method',
    },
    evidence: {
      ...candidate().evidence,
      sample: { ...candidate().evidence.sample, n: 88, pair_coverage: 0.55 },
      coverage: { ...candidate().evidence.coverage, pair_coverage: 0.55, minimum_segment_coverage: 0.4 },
      effect: {
        method: 'point_biserial',
        coefficient: -0.31,
        absolute_coefficient: 0.31,
        minimum_absolute_effect: 0.15,
        meets_minimum: true,
        group: {
          boolean_side: 'y',
          true_count: 54,
          false_count: 34,
          minority_count: 34,
          minority_share: 0.39,
          true_mean: 61.1,
          false_mean: 40.2,
          true_median: 58,
          false_median: 39,
          absolute_mean_difference: 20.9,
          cohens_d: 0.7,
        },
      },
      stability: { ...candidate().evidence.stability, segment_count: 3, analyzable_segment_count: 3 },
    },
    caveats: [
      { code: 'moderate_coverage', label: 'Умеренное покрытие', message: 'Часть подходящих дней не имеет обоих показателей.', detail: 'Умеренное покрытие.', severity: 'warning' },
      { code: 'association_not_causation', label: 'Связь не означает причинность', message: 'Наблюдаемая связь не доказывает, что один показатель вызывает другой.', detail: 'Связь не причинность.', severity: 'info' },
    ],
    in_default_feed: true,
  })
}

/** A blocked candidate: only visible when the hidden filter is on. */
export function blockedCandidate(): InsightCandidateRead {
  return candidate({
    fingerprint: 'c'.repeat(64),
    status: 'hidden',
    x: ENERGY,
    y: variable('state.sleep_minutes', 'Сон, минуты', 'numeric'),
    lag: 5,
    text: {
      statement: 'Показатели «Энергия» и «Сон, минуты» были слабо связаны в данных за период.',
      timing: 'Через пять дней',
      prefix: 'Результат не прошёл статистические проверки: ',
      full: 'Результат не прошёл статистические проверки: показатели «Энергия» и «Сон, минуты» были слабо связаны в данных за период.',
      template_version: '1',
    },
    guardrail: {
      verdict: 'blocked',
      policy_version: '1',
      family_mode: 'discovery',
      family_size: 225,
      tested_size: 225,
      family_rank: 40,
      threshold: 0.1,
      raw_p_value: 0.4,
      adjusted_q_value: 0.5,
      blocking_reasons: [{ code: 'below_effect_threshold', label: 'Связь слабее порога', message: 'Величина связи ниже минимального значимого уровня.' }],
      warnings: [],
      confidence_capped: false,
    },
    caveats: [
      { code: 'below_effect_threshold', label: 'Связь слабее порога', message: 'Величина связи ниже минимального значимого уровня.', detail: 'Величина связи ниже минимального значимого уровня.', severity: 'blocking' },
    ],
    alternatives: [],
    in_default_feed: false,
  })
}

export function chartFor(selected: InsightCandidateRead): InsightChartRead {
  const dates = Array.from({ length: 6 }, (_, index) => `2026-09-${String(index + 1).padStart(2, '0')}`)
  const points = dates.map((date, index) => ({
    date,
    value: index === 2 ? null : 1 + index,
    missing: index === 2,
    incomplete: false,
  }))
  return {
    x: { variable: selected.x, points, rolling: [{ date: dates[0]!, window: 7, mean: 2, status: 'ok' }] },
    y: {
      variable: selected.y,
      points: points.map((point) => ({ ...point, value: point.missing ? null : 0.5 })),
      rolling: [],
    },
    pairs:
      selected.x.type === 'boolean' || selected.y.type === 'boolean'
        ? []
        : [{ x_date: dates[0]!, y_date: dates[0]!, x: 3, y: 4 }],
    lag_profile: selected.alternatives,
    segments: selected.evidence.segments,
    summaries: [
      { key: 'series', title: 'Как менялись показатели', summary: `Показатели «${selected.x.label}» и «${selected.y.label}» по датам периода. Заполнено точек: 5 и 5; пропуски оставлены пустыми.` },
      { key: 'lag_profile', title: 'Профиль задержек', summary: 'Проверено задержек: 15. Для каждой показана величина связи и результат проверок.' },
      { key: 'segments', title: 'Отрезки истории', summary: 'История разделена на 3 последовательных отрезка.' },
      { key: 'groups', title: 'Сравнение групп', summary: 'Показатель «Тренировка»: «Да» — 54 наблюдений, «Нет» — 34 наблюдений.' },
    ],
  }
}

export function analyticsPayload(
  insights: InsightCandidateRead[],
  overrides: Partial<InsightAnalyticsRead> = {},
): InsightAnalyticsRead {
  return {
    contract_version: '8A.1',
    dataset_contract_version: '7A.1',
    insight_policy_version: '1',
    guardrail_policy_version: '1',
    confidence_policy_version: '1',
    template_version: '1',
    today: TODAY,
    mode: 'discovery',
    window: PERIOD,
    source_range: { start: '2026-06-21', end: '2026-09-25' },
    lags: [0, 1, 2, 3, 4, 5, 6, 7],
    include_hidden: false,
    discovery_policy: {
      version: '1',
      default_window_days: 90,
      minimum_window_days: 7,
      maximum_window_days: 730,
      default_variable_budget: 6,
      maximum_variable_budget: 8,
      default_lags: [0, 1, 2, 3, 4, 5, 6, 7],
      maximum_hypotheses: 480,
    },
    sort_order: ['guardrail_usability', 'confidence_maturity', 'recency', 'sample_size', 'absolute_effect', 'fingerprint'],
    summary: {
      availability: 'ok',
      message: 'Найдены наблюдения, которые прошли статистические проверки.',
      counts: {
        hypotheses: 225,
        evaluated_hypotheses: 225,
        admissible_hypotheses: 87,
        blocked_hypotheses: 138,
        unevaluable_hypotheses: 0,
        groups: 15,
        shown: insights.length,
        in_default_feed: insights.filter((item) => item.in_default_feed).length,
        by_status: {
          preliminary: 0,
          stable: 0,
          well_supported: insights.filter((item) => item.status === 'well_supported').length,
          warning: insights.filter((item) => item.status === 'warning').length,
          hidden: 0,
          not_evaluable: 0,
        },
        by_blocking_reason: { false_discovery_risk: 129 },
      },
    },
    insights,
    ...overrides,
  }
}

export function historyRows(selected: InsightCandidateRead): InsightSnapshotRead[] {
  return [
    snapshot(selected, 1, '2026-09-20', 'preliminary', '0.44'),
    snapshot(selected, 2, '2026-09-25', 'well_supported', '0.62'),
  ]
}

function snapshot(
  selected: InsightCandidateRead,
  id: number,
  evaluatedOn: string,
  status: InsightSnapshotRead['status'],
  coefficient: string,
): InsightSnapshotRead {
  return {
    id,
    fingerprint: selected.fingerprint,
    evaluated_on: evaluatedOn,
    period: PERIOD,
    x_key: selected.x.key,
    y_key: selected.y.key,
    x_label: selected.x.label,
    y_label: selected.y.label,
    x_archived: null,
    y_archived: selected.y.habit_id !== null ? false : null,
    grain: 'daily',
    lag: selected.lag,
    lag_unit: 'day',
    orientation: 'same_period',
    method: 'spearman',
    coefficient: Number(coefficient),
    n: 90,
    pair_coverage: 0.98,
    confidence: status === 'preliminary' ? 'preliminary' : 'well_supported',
    guardrail_verdict: 'pass',
    status,
    blocking_reasons: [],
    warnings: [],
    statement: `${evaluatedOn}: ${selected.text.statement}`,
    insight_policy_version: '1',
    guardrail_policy_version: '1',
    confidence_policy_version: '1',
    template_version: '1',
    created_at: `${evaluatedOn}T12:00:00`,
    updated_at: `${evaluatedOn}T12:00:00`,
  }
}

export function detailPayload(
  selected: InsightCandidateRead,
  history: InsightSnapshotRead[] = [],
): InsightDetailRead {
  return {
    contract_version: '8A.1',
    today: TODAY,
    mode: 'discovery',
    window: PERIOD,
    snapshot_policy:
      'Снимок истории создаётся только явным обновлением аналитики и не чаще одного раза на календарный день для одной гипотезы.',
    candidate: selected,
    chart: chartFor(selected),
    history,
  }
}

export function cataloguePayload(): InsightCatalogueRead {
  return {
    contract_version: '8A.1',
    discovery_policy: analyticsPayload([]).discovery_policy,
    areas: [{ id: 1, name: 'Здоровье', color: '#2f9e5f', is_archived: false }],
    variables: [
      { key: ENERGY.key, label: ENERGY.label, type: ENERGY.type, grain: 'daily', group: 'state', habit_id: null, area_id: null, area_name: null, is_archived: false, supported: true, in_default_sweep: true },
      { key: MOOD.key, label: MOOD.label, type: MOOD.type, grain: 'daily', group: 'state', habit_id: null, area_id: null, area_name: null, is_archived: false, supported: true, in_default_sweep: true },
      { key: SCORE.key, label: SCORE.label, type: SCORE.type, grain: 'daily', group: 'score', habit_id: null, area_id: null, area_name: null, is_archived: false, supported: true, in_default_sweep: true },
      { key: TRAINING.key, label: TRAINING.label, type: TRAINING.type, grain: 'daily', group: 'habit', habit_id: 1, area_id: 1, area_name: 'Здоровье', is_archived: false, supported: true, in_default_sweep: true },
      { key: 'state.sleep_status', label: 'Сон', type: 'categorical', grain: 'daily', group: 'state', habit_id: null, area_id: null, area_name: null, is_archived: false, supported: false, in_default_sweep: false },
    ],
  }
}

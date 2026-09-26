/**
 * Stage 8 insight API.
 *
 * The frontend only *formats* this contract: every coefficient, coverage,
 * confidence level and guardrail verdict is computed by the backend and sent
 * ready to display. Nothing here recomputes a statistic.
 */

import { apiRequest } from './client'
import type { OwlState } from './owl'

// --- vocabulary ----------------------------------------------------------------------

export type InsightStatus =
  | 'preliminary'
  | 'stable'
  | 'well_supported'
  | 'warning'
  | 'hidden'
  | 'not_evaluable'

export type ConfidenceLevel = 'preliminary' | 'stable' | 'well_supported'
export type GuardrailVerdict = 'pass' | 'pass_with_warnings' | 'blocked' | 'not_evaluable'
export type InsightFeedMode = 'discovery' | 'explorer'
export type InsightOrientation = 'same_period' | 'x_earlier' | 'x_later'
export type CaveatSeverity = 'info' | 'warning' | 'blocking'

export interface InsightPeriod {
  start: string
  end: string
}

export interface InsightVariableRead {
  key: string
  label: string
  type: string
  grain: string
  source: string
  missing_semantics: string
  categories: string[]
  minimum: number | null
  maximum: number | null
  habit_id: number | null
}

export interface InsightTextRead {
  statement: string
  timing: string
  prefix: string
  full: string
  template_version: string
}

export interface InsightCaveatRead {
  code: string
  label: string
  message: string
  detail: string
  severity: CaveatSeverity
}

export interface InsightReasonRead {
  code: string
  label: string
  message: string
}

export interface InsightRelationshipRead {
  method: string | null
  coefficient: number | null
  absolute_coefficient: number | null
  direction: string | null
  strength: string | null
  n: number
  status: string
  reason: string | null
  limitations: string[]
  method_agreement: string
}

export interface InsightGuardrailRead {
  verdict: GuardrailVerdict
  policy_version: string
  family_mode: string
  family_size: number
  tested_size: number
  family_rank: number | null
  threshold: number
  raw_p_value: number | null
  adjusted_q_value: number | null
  blocking_reasons: InsightReasonRead[]
  warnings: InsightReasonRead[]
  confidence_capped: boolean
}

export interface InsightConfidenceRead {
  status: 'evaluated' | 'not_evaluable'
  level: ConfidenceLevel | null
  policy_version: string
  reason: string | null
}

export interface InsightSampleRead {
  n: number
  requested_count: number
  eligible_count: number
  excluded_count: number
  missing_count: number
  unavailable_count: number
  pair_coverage: number | null
  minimum_n_met: boolean
  stable_n_met: boolean
  well_supported_n_met: boolean
}

export interface InsightCoverageRead {
  pair_coverage: number | null
  eligible_count: number
  stable_coverage_met: boolean
  well_supported_coverage_met: boolean
  segment_pair_coverage: number[]
  minimum_segment_coverage: number | null
  maximum_segment_coverage: number | null
  coverage_imbalance: number | null
  low_coverage: boolean
  segment_instability: boolean
}

export interface InsightStabilityRead {
  segment_count: number
  analyzable_segment_count: number
  insufficient_segment_count: number
  same_direction_count: number
  near_zero_count: number
  opposite_direction_count: number
  coefficients: (number | null)[]
  median_coefficient: number | null
  median_absolute_coefficient: number | null
  coefficient_range: number | null
  maximum_deviation_from_full: number | null
  direction_consistent: boolean
  meaningful_reversal: boolean
  magnitude_stable: boolean
  magnitude_well_supported: boolean
}

export interface InsightMethodsRead {
  primary_method: string | null
  methods: string[]
  coefficients: (number | null)[]
  directions: string[]
  agreement: string
}

export interface InsightGroupRead {
  boolean_side: 'x' | 'y'
  true_count: number
  false_count: number
  minority_count: number
  minority_share: number
  true_mean: number | null
  false_mean: number | null
  true_median: number | null
  false_median: number | null
  absolute_mean_difference: number | null
  cohens_d: number | null
}

export interface InsightEffectRead {
  method: string | null
  coefficient: number | null
  absolute_coefficient: number | null
  minimum_absolute_effect: number
  meets_minimum: boolean
  group: InsightGroupRead | null
}

export interface InsightWeekdayRead {
  status: string
  outcome: string
  weekday_basis: string | null
  strata_count: number
  usable_strata_count: number
  observations: number
  raw_coefficient: number | null
  adjusted_coefficient: number | null
  absolute_difference: number | null
  relative_attenuation: number | null
  direction_change: boolean
}

export interface InsightCheckRead {
  name: string
  status: string
  blocking: boolean
  detail: string
  observed: number | null
  threshold: number | null
}

export interface InsightSegmentRead {
  index: number
  name: string
  period: InsightPeriod
  coefficient: number | null
  direction: string | null
  strength: string | null
  relation_to_full: string
}

export interface InsightEvidenceRead {
  sample: InsightSampleRead
  coverage: InsightCoverageRead
  stability: InsightStabilityRead
  methods: InsightMethodsRead
  effect: InsightEffectRead
  weekday: InsightWeekdayRead
  checks: InsightCheckRead[]
  segments: InsightSegmentRead[]
}

export interface InsightAlternativeRead {
  fingerprint: string
  timing: string
  lag: number
  is_representative: boolean
  orientation: InsightOrientation
  guardrail: GuardrailVerdict
  status: InsightStatus
  confidence: ConfidenceLevel | null
  coefficient: number | null
  absolute_coefficient: number | null
  direction: string | null
  n: number
  pair_coverage: number | null
  blocking_reasons: string[]
  warnings: string[]
}

export interface InsightCandidateRead {
  fingerprint: string
  kind: 'association'
  status: InsightStatus
  orientation: InsightOrientation
  x: InsightVariableRead
  y: InsightVariableRead
  grain: string | null
  lag: number
  lag_unit: 'day' | 'week' | null
  target_period: InsightPeriod
  text: InsightTextRead
  relationship: InsightRelationshipRead
  guardrail: InsightGuardrailRead
  confidence: InsightConfidenceRead
  evidence: InsightEvidenceRead
  caveats: InsightCaveatRead[]
  alternatives: InsightAlternativeRead[]
  in_default_feed: boolean
  first_seen: string | null
}

export interface InsightCountsRead {
  hypotheses: number
  evaluated_hypotheses: number
  admissible_hypotheses: number
  blocked_hypotheses: number
  unevaluable_hypotheses: number
  groups: number
  shown: number
  in_default_feed: number
  by_status: Record<InsightStatus, number>
  by_blocking_reason: Record<string, number>
}

export interface InsightSummaryRead {
  availability:
    | 'ok'
    | 'preliminary_only'
    | 'no_guardrails_passed'
    | 'insufficient_data'
    | 'no_data'
  message: string
  counts: InsightCountsRead
}

export interface DiscoveryPolicyRead {
  version: string
  default_window_days: number
  minimum_window_days: number
  maximum_window_days: number
  default_variable_budget: number
  maximum_variable_budget: number
  default_lags: number[]
  maximum_hypotheses: number
}

export interface InsightAnalyticsRead {
  contract_version: string
  dataset_contract_version: string
  insight_policy_version: string
  guardrail_policy_version: string
  confidence_policy_version: string
  template_version: string
  today: string
  mode: InsightFeedMode
  window: InsightPeriod
  source_range: InsightPeriod
  lags: number[]
  include_hidden: boolean
  discovery_policy: DiscoveryPolicyRead
  sort_order: string[]
  summary: InsightSummaryRead
  insights: InsightCandidateRead[]
  /** Stage 9: the single contextual Owl state, or null. */
  owl: OwlState | null
}

export interface InsightChartPointRead {
  date: string
  value: number | null
  missing: boolean
  incomplete: boolean
}

export interface InsightSeriesRead {
  variable: InsightVariableRead
  points: InsightChartPointRead[]
  rolling: { date: string; window: number; mean: number | null; status: string }[]
}

export interface InsightPairPointRead {
  x_date: string
  y_date: string
  x: number
  y: number
}

export interface InsightChartSummaryRead {
  key: string
  title: string
  summary: string
}

export interface InsightChartRead {
  x: InsightSeriesRead
  y: InsightSeriesRead
  pairs: InsightPairPointRead[]
  lag_profile: InsightAlternativeRead[]
  segments: InsightSegmentRead[]
  summaries: InsightChartSummaryRead[]
}

export interface InsightSnapshotRead {
  id: number
  fingerprint: string
  evaluated_on: string
  period: InsightPeriod
  x_key: string
  y_key: string
  x_label: string
  y_label: string
  x_archived: boolean | null
  y_archived: boolean | null
  grain: string
  lag: number
  lag_unit: string | null
  orientation: string
  method: string | null
  coefficient: number | null
  n: number
  pair_coverage: number | null
  confidence: ConfidenceLevel | null
  guardrail_verdict: GuardrailVerdict
  status: InsightStatus
  blocking_reasons: string[]
  warnings: string[]
  statement: string
  insight_policy_version: string
  guardrail_policy_version: string
  confidence_policy_version: string
  template_version: string
  created_at: string
  updated_at: string
}

export interface InsightDetailRead {
  contract_version: string
  today: string
  mode: InsightFeedMode
  window: InsightPeriod
  snapshot_policy: string
  candidate: InsightCandidateRead
  chart: InsightChartRead
  history: InsightSnapshotRead[]
}

export interface InsightVariableOptionRead {
  key: string
  label: string
  type: string
  grain: string
  group: 'score' | 'state' | 'habit' | 'calendar' | 'other'
  habit_id: number | null
  area_id: number | null
  area_name: string | null
  is_archived: boolean
  supported: boolean
  in_default_sweep: boolean
}

export interface InsightAreaRead {
  id: number
  name: string
  color: string
  is_archived: boolean
}

export interface InsightCatalogueRead {
  contract_version: string
  discovery_policy: DiscoveryPolicyRead
  areas: InsightAreaRead[]
  variables: InsightVariableOptionRead[]
}

export interface InsightSnapshotSummaryRead {
  evaluated_on: string
  created: number
  updated: number
  unchanged: number
  total: number
}

export interface InsightRefreshResultRead {
  analytics: InsightAnalyticsRead
  snapshots: InsightSnapshotSummaryRead
}

// --- queries -------------------------------------------------------------------------

export interface InsightQuery {
  start: string
  end: string
  /** `explorer` evaluates exactly the requested pair; `discovery` sweeps. */
  mode?: InsightFeedMode
  x?: string
  y?: string
  lag?: number
  lags?: number[]
  maxVariables?: number
  includeHidden?: boolean
  confidence?: ConfidenceLevel[]
  verdicts?: GuardrailVerdict[]
  variables?: string[]
}

export function buildInsightQuery(query: InsightQuery): string {
  const params = new URLSearchParams({ start: query.start, end: query.end })
  if (query.mode) params.set('mode', query.mode)
  if (query.x) params.set('x', query.x)
  if (query.y) params.set('y', query.y)
  if (query.lag !== undefined) params.set('lag', String(query.lag))
  if (query.lags) for (const lag of query.lags) params.append('lags', String(lag))
  if (query.maxVariables !== undefined) params.set('max_variables', String(query.maxVariables))
  if (query.includeHidden) params.set('include_hidden', 'true')
  if (query.confidence) for (const level of query.confidence) params.append('confidence', level)
  if (query.verdicts) for (const verdict of query.verdicts) params.append('verdicts', verdict)
  if (query.variables) for (const key of query.variables) params.append('variables', key)
  return params.toString()
}

// --- requests ------------------------------------------------------------------------

export function fetchInsights(
  query: InsightQuery,
  signal?: AbortSignal,
): Promise<InsightAnalyticsRead> {
  return apiRequest<InsightAnalyticsRead>(`/api/analytics/insights?${buildInsightQuery(query)}`, {
    signal,
  })
}

export function fetchInsightDetail(
  fingerprint: string,
  query: InsightQuery,
  signal?: AbortSignal,
): Promise<InsightDetailRead> {
  return apiRequest<InsightDetailRead>(
    `/api/analytics/insights/${encodeURIComponent(fingerprint)}?${buildInsightQuery(query)}`,
    { signal },
  )
}

export function fetchInsightHistory(
  fingerprint: string,
  signal?: AbortSignal,
): Promise<InsightSnapshotRead[]> {
  return apiRequest<InsightSnapshotRead[]>(
    `/api/analytics/insights/${encodeURIComponent(fingerprint)}/history`,
    { signal },
  )
}

export function fetchInsightCatalogue(signal?: AbortSignal): Promise<InsightCatalogueRead> {
  return apiRequest<InsightCatalogueRead>('/api/analytics/insights/variables', { signal })
}

/** The only call that writes insight history: at most one snapshot per day. */
export function refreshInsights(
  payload: { start: string; end: string; lags?: number[]; max_variables?: number },
  signal?: AbortSignal,
): Promise<InsightRefreshResultRead> {
  return apiRequest<InsightRefreshResultRead>('/api/analytics/insights/refresh', {
    method: 'POST',
    body: payload,
    signal,
  })
}

/**
 * Stage 10 experiment endpoints.
 *
 * The frontend never computes a comparison: the backend describes the
 * before/during/after windows over the canonical dataset. This module only
 * shapes requests and mirrors the response contract.
 */

import { apiRequest } from './client'
import type { OwlState } from './owl'

export type ExperimentStatus = 'scheduled' | 'active' | 'completed' | 'cancelled'
export type ExperimentStage = 'before' | 'during' | 'after'

export interface ExperimentWindow {
  key: ExperimentStage
  start: string
  end: string
}

export interface ExperimentWindows {
  before: ExperimentWindow
  during: ExperimentWindow
  after: ExperimentWindow
}

export interface ExperimentPhase {
  status: ExperimentStatus
  stage: ExperimentStage
  day_index: number | null
  days_total: number | null
  days_until_start: number | null
  days_since_end: number | null
  after_collected_days: number
  after_total_days: number
}

export interface Experiment {
  id: number
  title: string
  hypothesis: string
  protocol: string
  start_date: string
  end_date: string
  status: ExperimentStatus
  phase: ExperimentPhase
  cancelled_on: string | null
  created_at: string
  updated_at: string
}

export interface PeriodCoverage {
  calendar_days: number
  elapsed_days: number
  observed_days: number
  /** 0..1, or null when the period has no calendar days at all. */
  coverage: number | null
}

export interface OverallPeriod {
  coverage: PeriodCoverage
  mean_score: number | null
  scored_days: number
  completed_weight: number
  required_weight: number
}

export interface OverallComparison {
  before: OverallPeriod
  during: OverallPeriod
  after: OverallPeriod
  delta_before_during: number | null
  delta_during_after: number | null
  delta_before_after: number | null
}

export interface HabitPeriod {
  obligation_days: number
  observed_days: number
  done_days: number
  missed_days: number
  completion_ratio: number | null
}

export interface HabitComparison {
  habit_id: number
  name: string
  before: HabitPeriod
  during: HabitPeriod
  after: HabitPeriod
  delta_during_vs_before: number | null
}

export interface StatePeriod {
  observed_days: number
  value: number | null
}

export interface StateComparison {
  key: string
  label: string
  kind: string
  before: StatePeriod
  during: StatePeriod
  after: StatePeriod
  delta_during_vs_before: number | null
}

export interface SeriesPoint {
  date: string
  phase: ExperimentStage
  score: number | null
  energy: number | null
}

export interface ExperimentAnalysis {
  windows: ExperimentWindows
  overall: OverallComparison
  habits: HabitComparison[]
  state: StateComparison[]
  series: SeriesPoint[]
  sufficient: boolean
  summary: string
}

export interface ExperimentOverlap {
  id: number
  title: string
  start_date: string
  end_date: string
}

export interface ExperimentListRead {
  experiments: Experiment[]
  owl: OwlState | null
}

export interface ExperimentDetailRead {
  experiment: Experiment
  overlaps: ExperimentOverlap[]
  analysis: ExperimentAnalysis
}

export interface ExperimentInput {
  title: string
  hypothesis: string
  protocol: string
  start_date: string
  end_date: string
}

/** Partial update: send only the fields that change. */
export type ExperimentUpdateInput = Partial<ExperimentInput>

export function fetchExperiments(signal?: AbortSignal): Promise<ExperimentListRead> {
  return apiRequest<ExperimentListRead>('/api/experiments', { signal })
}

export function fetchExperiment(id: number, signal?: AbortSignal): Promise<ExperimentDetailRead> {
  return apiRequest<ExperimentDetailRead>(`/api/experiments/${id}`, { signal })
}

export function createExperiment(input: ExperimentInput): Promise<Experiment> {
  return apiRequest<Experiment>('/api/experiments', { method: 'POST', body: input })
}

export function updateExperiment(id: number, input: ExperimentUpdateInput): Promise<Experiment> {
  return apiRequest<Experiment>(`/api/experiments/${id}`, { method: 'PATCH', body: input })
}

export function cancelExperiment(id: number): Promise<Experiment> {
  return apiRequest<Experiment>(`/api/experiments/${id}/cancel`, { method: 'POST' })
}

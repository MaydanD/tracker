import type {
  Experiment,
  ExperimentAnalysis,
  ExperimentDetailRead,
  ExperimentListRead,
  HabitComparison,
  OverallComparison,
  OverallPeriod,
  PeriodCoverage,
  StateComparison,
} from '../api/experiments'
import { jsonResponse, stubApi, type StubHandler, type StubRequest } from './fetchStub'

export function experimentFixture(overrides: Partial<Experiment> = {}): Experiment {
  const status = overrides.status ?? 'active'
  return {
    id: 1,
    title: 'Без алкоголя 14 дней',
    hypothesis: 'Проверить, будет ли выше энергия',
    protocol: 'Не употреблять алкоголь с 1 по 14 сентября.',
    start_date: '2026-09-01',
    end_date: '2026-09-14',
    status,
    phase: {
      status,
      stage: 'during',
      day_index: 6,
      days_total: 14,
      days_until_start: null,
      days_since_end: null,
      after_collected_days: 0,
      after_total_days: 14,
    },
    cancelled_on: null,
    created_at: '2026-09-01T10:00:00',
    updated_at: '2026-09-01T10:00:00',
    ...overrides,
  }
}

function coverage(calendar: number, observed: number): PeriodCoverage {
  return {
    calendar_days: calendar,
    elapsed_days: calendar,
    observed_days: observed,
    coverage: calendar === 0 ? null : observed / calendar,
  }
}

function overallPeriod(mean: number | null, observed: number, calendar = 14): OverallPeriod {
  return {
    coverage: coverage(calendar, observed),
    mean_score: mean,
    scored_days: mean === null ? 0 : observed,
    completed_weight: observed,
    required_weight: calendar,
  }
}

function overallComparison(overrides: Partial<OverallComparison> = {}): OverallComparison {
  return {
    before: overallPeriod(62, 12),
    during: overallPeriod(76, 14),
    after: overallPeriod(70, 4),
    delta_before_during: 14,
    delta_during_after: 6,
    delta_before_after: 8,
    ...overrides,
  }
}

function habitComparison(overrides: Partial<HabitComparison> = {}): HabitComparison {
  return {
    habit_id: 7,
    name: 'Чтение',
    before: { obligation_days: 14, observed_days: 12, done_days: 9, missed_days: 3, completion_ratio: 64 },
    during: { obligation_days: 14, observed_days: 14, done_days: 13, missed_days: 1, completion_ratio: 93 },
    after: { obligation_days: 14, observed_days: 4, done_days: 3, missed_days: 1, completion_ratio: 75 },
    delta_during_vs_before: 29,
    ...overrides,
  }
}

function stateComparison(overrides: Partial<StateComparison> = {}): StateComparison {
  return {
    key: 'state.energy',
    label: 'Энергия',
    kind: 'ordinal',
    before: { observed_days: 12, value: 3.1 },
    during: { observed_days: 14, value: 3.7 },
    after: { observed_days: 4, value: 3.4 },
    delta_during_vs_before: 0.6,
    ...overrides,
  }
}

export function analysisFixture(overrides: Partial<ExperimentAnalysis> = {}): ExperimentAnalysis {
  return {
    windows: {
      before: { key: 'before', start: '2026-08-18', end: '2026-08-31' },
      during: { key: 'during', start: '2026-09-01', end: '2026-09-14' },
      after: { key: 'after', start: '2026-09-15', end: '2026-09-28' },
    },
    overall: overallComparison(),
    habits: [habitComparison()],
    state: [stateComparison()],
    series: [
      { date: '2026-08-18', phase: 'before', score: 60, energy: 3 },
      { date: '2026-08-19', phase: 'before', score: null, energy: null },
      { date: '2026-09-01', phase: 'during', score: 80, energy: 4 },
      { date: '2026-09-02', phase: 'during', score: 72, energy: 3 },
      { date: '2026-09-15', phase: 'after', score: null, energy: null },
    ],
    sufficient: true,
    summary:
      'Во время эксперимента средний дневной прогресс был выше примерно на 14 п.п., чем за предыдущий сопоставимый период.',
    ...overrides,
  }
}

export function detailFixture(
  overrides: Partial<ExperimentDetailRead> = {},
): ExperimentDetailRead {
  return {
    experiment: experimentFixture(),
    overlaps: [],
    analysis: analysisFixture(),
    ...overrides,
  }
}

export function listFixture(
  experiments: Experiment[],
  owl: ExperimentListRead['owl'] = null,
): ExperimentListRead {
  return { experiments, owl }
}

export interface FakeExperiments {
  experiments: Experiment[]
  detail: ExperimentDetailRead
  handle: StubHandler
}

/**
 * A tiny in-memory experiments API: enough for list/create/cancel/detail without
 * reimplementing the backend's comparison math.
 */
export function createFakeExperiments(options: {
  experiments?: Experiment[]
  detail?: ExperimentDetailRead
} = {}): FakeExperiments {
  const state = {
    experiments: [...(options.experiments ?? [])],
    detail: options.detail ?? detailFixture(),
    nextId: 100,
  }

  function handle(request: StubRequest): Response {
    const segments = request.path.split('/').filter((part) => part.length > 0)
    // ['api', 'experiments', maybe id, maybe action]
    const id = segments[2] && /^\d+$/.test(segments[2]) ? Number(segments[2]) : null
    const action = id === null ? segments[2] : segments[3]

    if (request.method === 'GET' && id === null) {
      return jsonResponse(listFixture(state.experiments))
    }

    if (request.method === 'POST' && id === null) {
      const body = (request.body ?? {}) as Partial<Experiment>
      const created = experimentFixture({
        id: state.nextId++,
        title: String(body.title ?? ''),
        hypothesis: String(body.hypothesis ?? ''),
        protocol: String(body.protocol ?? ''),
        start_date: String(body.start_date ?? ''),
        end_date: String(body.end_date ?? ''),
        status: 'scheduled',
      })
      state.experiments = [created, ...state.experiments]
      return jsonResponse(created, 201)
    }

    if (id === null) return jsonResponse({ error: { code: 'not_found', message: 'no route' } }, 404)

    const experiment = state.experiments.find((item) => item.id === id)
    if (request.method === 'GET' && action === undefined) {
      return jsonResponse({ ...state.detail, experiment: experiment ?? state.detail.experiment })
    }
    if (request.method === 'PATCH' && action === undefined) {
      const body = (request.body ?? {}) as Partial<Experiment>
      const updated = { ...(experiment ?? state.detail.experiment), ...body }
      state.experiments = state.experiments.map((item) => (item.id === id ? updated : item))
      return jsonResponse(updated)
    }
    if (request.method === 'POST' && action === 'cancel') {
      const cancelled = {
        ...(experiment ?? state.detail.experiment),
        status: 'cancelled' as Experiment['status'],
        cancelled_on: '2026-09-06',
      }
      state.experiments = state.experiments.map((item) => (item.id === id ? cancelled : item))
      return jsonResponse(cancelled)
    }
    return jsonResponse({ error: { code: 'not_found', message: 'no route' } }, 404)
  }

  return {
    get experiments() {
      return state.experiments
    },
    get detail() {
      return state.detail
    },
    handle,
  }
}

export function stubExperimentsApi(fake: FakeExperiments) {
  return stubApi({}, { fallback: fake.handle })
}


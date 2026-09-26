import type {
  Achievement,
  AchievementCategory,
  RecordsPreview,
  RecordsRead,
} from '../api/records'
import { jsonResponse, stubApi } from './fetchStub'

export function achievementFixture(overrides: Partial<Achievement> = {}): Achievement {
  const target = overrides.progress?.target ?? 30
  return {
    key: 'streak_30',
    title: 'Месяц без отрыва',
    description: 'Одна привычка держалась 30 дней подряд.',
    category: 'streak' as AchievementCategory,
    achieved: true,
    achieved_on: '2026-09-18',
    progress: { current: target, target },
    ...overrides,
  }
}

export function recordsPreviewFixture(
  overrides: Partial<RecordsPreview> = {},
): RecordsPreview {
  return {
    longest_streak: {
      habit_id: 1,
      name: 'Чтение',
      unit: 'days',
      current_streak: 12,
      best_streak: 28,
      best_start: '2026-08-12',
      best_end: '2026-09-08',
      archived: false,
    },
    latest_achievement: achievementFixture(),
    achieved_count: 4,
    total_count: 12,
    ...overrides,
  }
}

export function recordsFixture(overrides: Partial<RecordsRead> = {}): RecordsRead {
  const achievements: Achievement[] = [
    achievementFixture(),
    achievementFixture({
      key: 'first_habit_completion',
      title: 'Первое выполнение',
      description: 'Первая привычка отмечена выполненной.',
      category: 'consistency',
      achieved_on: '2026-08-05',
      progress: { current: 1, target: 1 },
    }),
    achievementFixture({
      key: 'habit_100_completions',
      title: '100 выполнений',
      description: 'Одна привычка выполнена 100 раз.',
      category: 'consistency',
      achieved: false,
      achieved_on: null,
      progress: { current: 73, target: 100 },
    }),
    achievementFixture({
      key: 'tracked_100_days',
      title: '100 дней трекинга',
      description: 'Записи есть за 100 разных дней.',
      category: 'tracking',
      achieved: false,
      achieved_on: null,
      progress: { current: 42, target: 100 },
    }),
  ]

  return {
    summary: {
      first_tracked_day: '2026-08-05',
      tracked_days: 42,
      habit_completions: 412,
      experiments_created: 3,
      completed_experiments: 2,
      stable_insight_on: '2026-09-02',
      well_supported_insight_on: null,
    },
    records: {
      longest_streak: {
        habit_id: 1,
        name: 'Чтение',
        unit: 'days',
        current_streak: 12,
        best_streak: 28,
        best_start: '2026-08-12',
        best_end: '2026-09-08',
        archived: false,
      },
      best_day: {
        day: '2026-09-05',
        score: 100,
        completed_weight: 6,
        required_weight: 6,
        ties: 3,
      },
      best_week: {
        week_start: '2026-08-24',
        week_end: '2026-08-30',
        score: 93.5,
        coverage: 1,
        observed_days: 7,
        obligation_days: 7,
        ties: 1,
      },
      most_completed: {
        day: '2026-09-05',
        completed_count: 4,
        required_count: 4,
        ties: 2,
      },
      consistency: [
        {
          habit_id: 1,
          name: 'Чтение',
          archived: false,
          period_start: '2026-08-01',
          period_end: '2026-08-31',
          done_days: 29,
          obligation_days: 31,
          ratio: 93.5,
        },
      ],
    },
    achievements,
    recent_achievements: [achievements[0] as Achievement],
    achieved_count: achievements.filter((item) => item.achieved).length,
    total_count: achievements.length,
    ...overrides,
  }
}

/** Stub the records endpoint with a fixed payload. */
export function stubRecords(records: RecordsRead = recordsFixture()) {
  return stubApi({ 'GET /api/records': () => jsonResponse(records) })
}

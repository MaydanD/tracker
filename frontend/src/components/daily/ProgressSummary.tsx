import type { HabitStreak, ProgressState, Score, WeekHabitProgress } from '../../api/types'
import { WEEKDAY_OPTIONS } from '../habits/options'
import { formatDayLabel } from './dates'

const STATUS = {
  satisfied: 'Выполнено за неделю',
  pending: 'Ожидает выполнения',
  failed: 'Неделя не выполнена',
}

function ScoreValue({ value }: { value: Score }) {
  return value.score === null ? <p>Нет обязательных привычек</p> : (
    <p>
      <strong>{value.score.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%</strong>
      {' · '}{value.completed_weight} / {value.required_weight} по весу
    </p>
  )
}

export function StreakLabel({ streak }: { streak: HabitStreak }) {
  const n = streak.current_streak
  const plural = new Intl.PluralRules('ru-RU').select(n)
  const labels = streak.unit === 'days'
    ? { one: 'день', few: 'дня', many: 'дней', other: 'дней' }
    : { one: 'неделя', few: 'недели', many: 'недель', other: 'недель' }
  const unit = labels[plural as keyof typeof labels] ?? labels.other
  return <span>🔥 {n} {unit} · серия на {formatDayLabel(streak.as_of)}</span>
}

export function HabitWeekLabel({ progress }: { progress: WeekHabitProgress }) {
  return (
    <div className="habit-progress">
      <span>{progress.completed_count} / {progress.quota} за выбранную неделю · {STATUS[progress.status]}</span>
      {progress.weekly_quota > 0 ? (
        <>
          {progress.preferred_weekdays.length > 0 ? (
            <span>Предпочтительно: {progress.preferred_weekdays.map((d) => WEEKDAY_OPTIONS[d]?.label).join(', ')}</span>
          ) : null}
          <span className="text-muted">Выполнение можно перенести внутри недели, с понедельника по воскресенье.</span>
          {progress.daily_required_count > 0 ? (
            <span>Ежедневные: {progress.daily_completed_count} / {progress.daily_required_count}; недельная квота: {progress.weekly_completed_count} / {progress.weekly_quota}.</span>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

export function ProgressSummary({ progress }: { progress: ProgressState }) {
  return (
    <section aria-label="Показатели выполнения" className="progress-summary">
      <div>
        <h2>Оценка дня</h2>
        <ScoreValue value={progress.day} />
        <p className="text-muted">Только ежедневные обязательства. Пропуск с причиной не повышает оценку.</p>
      </div>
      <div>
        <h2>Оценка недели</h2>
        <p>{formatDayLabel(progress.week.week_start)} — {formatDayLabel(progress.week.week_end)}</p>
        <ScoreValue value={progress.week} />
        <details>
          <summary>Прогресс всех привычек за неделю</summary>
          <ul>
            {progress.week.habits.map((habit) => (
              <li key={habit.habit_id}>{habit.name}: {habit.completed_count} / {habit.quota} · {STATUS[habit.status]}</li>
            ))}
          </ul>
        </details>
      </div>
    </section>
  )
}

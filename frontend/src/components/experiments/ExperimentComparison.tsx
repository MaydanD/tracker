import type {
  HabitComparison,
  OverallComparison,
  StateComparison,
} from '../../api/experiments'
import {
  formatAverage,
  formatCoverage,
  formatCount,
  formatPercent,
  formatPoints,
  formatValue,
  stateDeltaText,
  statePeriodText,
} from './labels'

export interface OverallComparisonProps {
  overall: OverallComparison
}

/**
 * Overall daily progress per window.
 *
 * The wording stays descriptive: the period *coincided* with a difference; the
 * UI never says the experiment improved or caused anything.
 */
export function ExperimentOverall({ overall }: OverallComparisonProps) {
  return (
    <div className="experiment-compare">
      <div className="experiment-compare__row">
        {(['before', 'during', 'after'] as const).map((key) => {
          const period = overall[key]
          return (
            <div key={key} className={`experiment-compare__cell experiment-compare__cell--${key}`}>
              <span className="experiment-compare__label">{PERIOD_LABELS[key]}</span>
              <strong className="experiment-compare__value">{formatPercent(period.mean_score)}</strong>
              <span className="experiment-compare__coverage">{formatCoverage(period.coverage)}</span>
            </div>
          )
        })}
      </div>
      <p className="experiment-compare__delta">
        {`Средний дневной прогресс во время эксперимента: ${formatPoints(overall.delta_before_during)} относительно периода до, `}
        {`${formatPoints(overall.delta_during_after)} относительно периода после.`}
      </p>
    </div>
  )
}

export interface StateComparisonProps {
  state: StateComparison[]
}

export function ExperimentStateTable({ state }: StateComparisonProps) {
  if (state.length === 0) {
    return <p className="empty">Состояние дня в этот период не заполнялось.</p>
  }
  return (
    <div className="experiment-table-wrap">
      <table className="experiment-table">
        <caption className="experiment-table__caption">
          Средние оценки состояния дня. Прочерк означает, что показатель в этот период не
          заполняли.
        </caption>
        <thead>
          <tr>
            <th scope="col">Показатель</th>
            <th scope="col">До</th>
            <th scope="col">Во время</th>
            <th scope="col">После</th>
            <th scope="col">Изменение</th>
          </tr>
        </thead>
        <tbody>
          {state.map((metric) => (
            <tr key={metric.key}>
              <th scope="row">{metric.label}</th>
              <td>{statePeriodText(metric.before, metric.kind)}</td>
              <td>{statePeriodText(metric.during, metric.kind)}</td>
              <td>{statePeriodText(metric.after, metric.kind)}</td>
              <td className="experiment-table__delta">{stateDeltaText(metric)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export interface HabitComparisonProps {
  habits: HabitComparison[]
}

export function ExperimentHabitsTable({ habits }: HabitComparisonProps) {
  if (habits.length === 0) {
    return <p className="empty">Привычек с заполненной историей в этот период нет.</p>
  }
  return (
    <div className="experiment-table-wrap">
      <table className="experiment-table">
        <caption className="experiment-table__caption">
          Доля выполненных обязательных дней по привычке. Пустая ячейка — привычку в этот
          период не отмечали.
        </caption>
        <thead>
          <tr>
            <th scope="col">Привычка</th>
            <th scope="col">До</th>
            <th scope="col">Во время</th>
            <th scope="col">После</th>
            <th scope="col">Изменение</th>
          </tr>
        </thead>
        <tbody>
          {habits.map((habit) => (
            <tr key={habit.habit_id}>
              <th scope="row">{habit.name}</th>
              <td>
                {formatPercent(habit.before.completion_ratio)}
                <span className="experiment-table__sub">{` (${formatCount(habit.before.observed_days)} дн.)`}</span>
              </td>
              <td>
                {formatPercent(habit.during.completion_ratio)}
                <span className="experiment-table__sub">{` (${formatCount(habit.during.observed_days)} дн.)`}</span>
              </td>
              <td>
                {formatPercent(habit.after.completion_ratio)}
                <span className="experiment-table__sub">{` (${formatCount(habit.after.observed_days)} дн.)`}</span>
              </td>
              <td className="experiment-table__delta">
                {formatPoints(habit.delta_during_vs_before)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Averages are descriptive; the state table already shows the raw numbers. */
export function ExperimentAverages({ state }: StateComparisonProps) {
  const numeric = state.filter((metric) => metric.kind !== 'boolean')
  if (numeric.length === 0) return null
  return (
    <ul className="experiment-averages">
      {numeric.map((metric) => (
        <li key={metric.key}>
          {`${metric.label}: ${formatValue(metric.before.value)} → ${formatValue(metric.during.value)} (${formatAverage(metric.delta_during_vs_before)})`}
        </li>
      ))}
    </ul>
  )
}

const PERIOD_LABELS = {
  before: 'До',
  during: 'Во время',
  after: 'После',
} as const

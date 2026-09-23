import type { ScheduleType } from '../../api/types'
import { SCHEDULE_TYPE_OPTIONS, WEEKDAY_OPTIONS } from './options'

export interface HabitScheduleFieldsProps {
  scheduleType: ScheduleType
  weekdays: number[]
  timesPerWeek: string
  onScheduleTypeChange: (type: ScheduleType) => void
  onWeekdayToggle: (weekday: number) => void
  onTimesPerWeekChange: (value: string) => void
}

/**
 * Schedule configuration only — Этап 2 stores the plan; evaluating it against
 * real days belongs to Этап 4.
 */
export function HabitScheduleFields({
  scheduleType,
  weekdays,
  timesPerWeek,
  onScheduleTypeChange,
  onWeekdayToggle,
  onTimesPerWeekChange,
}: HabitScheduleFieldsProps) {
  return (
    <fieldset className="fieldset">
      <legend className="fieldset__legend">Расписание</legend>

      <div className="choice-group">
        {SCHEDULE_TYPE_OPTIONS.map((option) => (
          <label key={option.value} className="choice">
            <input
              type="radio"
              name="schedule-type"
              value={option.value}
              checked={scheduleType === option.value}
              onChange={() => onScheduleTypeChange(option.value as ScheduleType)}
            />
            <span>
              {option.label}
              {option.hint ? <span className="choice__hint">{option.hint}</span> : null}
            </span>
          </label>
        ))}
      </div>

      {scheduleType === 'weekdays' ? (
        <div className="field">
          <span className="field__label" id="weekday-label">
            Предпочтительные дни
          </span>
          <div className="weekday-picker" role="group" aria-labelledby="weekday-label">
            {WEEKDAY_OPTIONS.map((day) => {
              const selected = weekdays.includes(day.value)
              return (
                <button
                  key={day.value}
                  type="button"
                  className={`weekday${selected ? ' weekday--selected' : ''}`}
                  aria-pressed={selected}
                  onClick={() => onWeekdayToggle(day.value)}
                >
                  {day.label}
                </button>
              )
            })}
          </div>
          <span className="field__hint">
            Выполнение можно перенести на другой день той же недели
            (с понедельника по воскресенье). Выполнений в неделю — по числу
            выбранных дней ({weekdays.length}).
          </span>
        </div>
      ) : null}

      {scheduleType === 'times_per_week' ? (
        <div className="field">
          <label className="field__label" htmlFor="habit-times-per-week">
            Выполнений в неделю
          </label>
          <input
            id="habit-times-per-week"
            className="field__input field__input--narrow"
            type="number"
            min={1}
            max={7}
            step={1}
            value={timesPerWeek}
            onChange={(event) => onTimesPerWeekChange(event.target.value)}
          />
          <span className="field__hint">
            От 1 до 7: привычку можно выполнить не больше одного раза за день.
          </span>
        </div>
      ) : null}
    </fieldset>
  )
}

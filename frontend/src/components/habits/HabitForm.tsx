import { useState, type FormEvent } from 'react'

import { describeApiError } from '../../api/client'
import { createHabit, updateHabit } from '../../api/habits'
import type {
  Habit,
  HabitInput,
  ScheduleInput,
  ScheduleType,
  TrackingMode,
} from '../../api/types'
import { ErrorBanner, InfoBanner } from '../Feedback'
import { HabitScheduleFields } from './HabitScheduleFields'
import { TRACKING_MODE_OPTIONS, WEIGHT_OPTIONS } from './options'

/** Only what the picker needs, so an archived area can stay selectable. */
export interface AreaOption {
  id: number
  name: string
}

export interface HabitFormProps {
  /** Areas that can be chosen (active ones, plus the habit's own area). */
  areas: AreaOption[]
  /** The habit being edited, or null when creating a new one. */
  habit?: Habit | null
  onSaved: (habit: Habit) => void
  onCancel: () => void
}

interface FormState {
  name: string
  description: string
  areaId: string
  weight: number
  trackingMode: TrackingMode
  quantityUnit: string
  allowsDecimal: boolean
  scheduleType: ScheduleType
  weekdays: number[]
  timesPerWeek: string
}

function initialState(habit: Habit | null | undefined): FormState {
  if (!habit) {
    return {
      name: '',
      description: '',
      areaId: '',
      weight: 1,
      trackingMode: 'binary',
      quantityUnit: '',
      allowsDecimal: false,
      scheduleType: 'daily',
      weekdays: [0, 1, 2, 3, 4],
      timesPerWeek: '3',
    }
  }

  return {
    name: habit.name,
    description: habit.description ?? '',
    areaId: String(habit.area_id),
    weight: habit.weight,
    trackingMode: habit.tracking_mode,
    quantityUnit: habit.quantity_unit ?? '',
    allowsDecimal: habit.quantity_allows_decimal,
    scheduleType: habit.schedule.type,
    weekdays: habit.schedule.weekdays,
    timesPerWeek: String(habit.schedule.times_per_week ?? 3),
  }
}

/**
 * Check the form before it reaches the API.
 *
 * These are the same rules the backend enforces, repeated here on purpose: the
 * form must not be able to submit a contradictory configuration, and the user
 * should not need a round-trip to learn what is missing. The server stays the
 * authority — its errors are still displayed.
 */
function validate(state: FormState): string[] {
  const problems: string[] = []

  if (state.name.trim() === '') problems.push('Введите название привычки.')
  if (state.areaId === '') problems.push('Выберите сферу.')

  if (state.trackingMode === 'binary_quantity' && state.quantityUnit.trim() === '') {
    problems.push('Укажите единицу измерения, например страницы, км или повторения.')
  }

  if (state.scheduleType === 'weekdays' && state.weekdays.length === 0) {
    problems.push('Выберите хотя бы один день недели.')
  }

  if (state.scheduleType === 'times_per_week') {
    const times = Number(state.timesPerWeek)
    if (!Number.isInteger(times) || times < 1 || times > 7) {
      problems.push('Укажите число выполнений в неделю от 1 до 7.')
    }
  }

  return problems
}

function buildSchedule(state: FormState): ScheduleInput {
  if (state.scheduleType === 'weekdays') {
    return { type: 'weekdays', weekdays: [...state.weekdays].sort((a, b) => a - b) }
  }
  if (state.scheduleType === 'times_per_week') {
    return { type: 'times_per_week', times_per_week: Number(state.timesPerWeek) }
  }
  return { type: 'daily' }
}

function toInput(state: FormState): HabitInput {
  const quantity = state.trackingMode === 'binary_quantity'
  return {
    name: state.name.trim(),
    description: state.description.trim() === '' ? null : state.description.trim(),
    area_id: Number(state.areaId),
    weight: state.weight,
    tracking_mode: state.trackingMode,
    quantity_unit: quantity ? state.quantityUnit.trim() : null,
    quantity_allows_decimal: quantity ? state.allowsDecimal : false,
    schedule: buildSchedule(state),
  }
}

export function HabitForm({ areas, habit = null, onSaved, onCancel }: HabitFormProps) {
  const [state, setState] = useState<FormState>(() => initialState(habit))
  const [problems, setProblems] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setState((current) => ({ ...current, [key]: value }))
  }

  function toggleWeekday(weekday: number) {
    setState((current) => ({
      ...current,
      weekdays: current.weekdays.includes(weekday)
        ? current.weekdays.filter((day) => day !== weekday)
        : [...current.weekdays, weekday],
    }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const found = validate(state)
    setProblems(found)
    setError(null)
    if (found.length > 0) return

    setSaving(true)
    try {
      const input = toInput(state)
      const saved = habit
        ? await updateHabit(habit.id, input)
        : await createHabit(input)
      onSaved(saved)
    } catch (cause) {
      // Input stays untouched so a failed save never loses typing.
      setError(describeApiError(cause))
    } finally {
      setSaving(false)
    }
  }

  const noAreas = areas.length === 0

  return (
    // noValidate: browser constraint validation would silently block submission
    // for out-of-range values, hiding the message that explains what to fix.
    <form className="card" onSubmit={handleSubmit} noValidate>
      <h3 className="card__title">
        {habit ? `Изменить: ${habit.name}` : 'Новая привычка'}
      </h3>

      {noAreas ? (
        <InfoBanner>
          Сначала создайте сферу — каждая привычка относится к одной сфере.
        </InfoBanner>
      ) : null}

      <div className="field">
        <label className="field__label" htmlFor="habit-name">
          Название
        </label>
        <input
          id="habit-name"
          className="field__input"
          value={state.name}
          maxLength={120}
          onChange={(event) => update('name', event.target.value)}
        />
      </div>

      <div className="field">
        <label className="field__label" htmlFor="habit-description">
          Описание (необязательно)
        </label>
        <textarea
          id="habit-description"
          className="field__input"
          rows={2}
          value={state.description}
          onChange={(event) => update('description', event.target.value)}
        />
      </div>

      <div className="field-row">
        <div className="field">
          <label className="field__label" htmlFor="habit-area">
            Сфера
          </label>
          <select
            id="habit-area"
            className="field__input"
            value={state.areaId}
            onChange={(event) => update('areaId', event.target.value)}
          >
            <option value="">Выберите сферу…</option>
            {areas.map((area) => (
              <option key={area.id} value={area.id}>
                {area.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="habit-weight">
            Важность
          </label>
          <select
            id="habit-weight"
            className="field__input"
            value={state.weight}
            onChange={(event) => update('weight', Number(event.target.value))}
          >
            {WEIGHT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.value} — {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <fieldset className="fieldset">
        <legend className="fieldset__legend">Способ учёта</legend>
        <div className="choice-group">
          {TRACKING_MODE_OPTIONS.map((option) => (
            <label key={option.value} className="choice">
              <input
                type="radio"
                name="tracking-mode"
                value={option.value}
                checked={state.trackingMode === option.value}
                onChange={() => update('trackingMode', option.value as TrackingMode)}
              />
              <span>
                {option.label}
                {option.hint ? (
                  <span className="choice__hint">{option.hint}</span>
                ) : null}
              </span>
            </label>
          ))}
        </div>

        {state.trackingMode === 'binary_quantity' ? (
          <div className="field-row">
            <div className="field">
              <label className="field__label" htmlFor="habit-unit">
                Единица измерения
              </label>
              <input
                id="habit-unit"
                className="field__input"
                value={state.quantityUnit}
                maxLength={32}
                placeholder="страницы, минуты, км, повторения…"
                onChange={(event) => update('quantityUnit', event.target.value)}
              />
            </div>
            <div className="field">
              <span className="field__label">Дробные значения</span>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={state.allowsDecimal}
                  onChange={(event) => update('allowsDecimal', event.target.checked)}
                />
                <span>Разрешить дробные значения</span>
              </label>
            </div>
          </div>
        ) : null}
      </fieldset>

      <HabitScheduleFields
        scheduleType={state.scheduleType}
        weekdays={state.weekdays}
        timesPerWeek={state.timesPerWeek}
        onScheduleTypeChange={(type) => update('scheduleType', type)}
        onWeekdayToggle={toggleWeekday}
        onTimesPerWeekChange={(value) => update('timesPerWeek', value)}
      />

      {problems.length > 0 ? (
        <ul className="banner banner--error" role="alert">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      ) : null}

      <ErrorBanner message={error} />

      <div className="card__actions">
        <button
          type="submit"
          className="button button--primary"
          disabled={saving || noAreas}
        >
          {saving ? 'Сохранение…' : habit ? 'Сохранить изменения' : 'Создать привычку'}
        </button>
        <button type="button" className="button" onClick={onCancel} disabled={saving}>
          Отмена
        </button>
      </div>
    </form>
  )
}

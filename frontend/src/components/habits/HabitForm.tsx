import { useState, type FormEvent } from 'react'

import { describeApiError } from '../../api/client'
import { createHabit, updateHabit } from '../../api/habits'
import type {
  Direction,
  Habit,
  HabitInput,
  Importance,
  ScheduleInput,
  ScheduleType,
} from '../../api/types'
import { ErrorBanner, InfoBanner } from '../Feedback'
import { HabitScheduleFields } from './HabitScheduleFields'
import {
  DEFAULT_SCALE_LABELS,
  DIRECTION_OPTIONS,
  WEIGHT_OPTIONS,
  markKindOf,
  markKindOptions,
  scaleLengthOf,
  valueTypeOf,
  type MarkKind,
} from './options'

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
  /** Fixed area for creation started inside an area card. Editing keeps the picker. */
  areaId?: number
  onSaved: (habit: Habit) => void
  onCancel: () => void
}

interface FormState {
  name: string
  description: string
  areaId: string
  /**
   * Legacy metadata the user no longer sets.
   *
   * It is carried through so saving an edit never rewrites the stored column by
   * accident; a new habit is ordinary. The single user-facing control is weight
   * — «Важность».
   */
  importance: Importance
  weight: number
  /** How a day is answered: completion, quantity, or a value scale. */
  markKind: MarkKind
  quantityUnit: string
  allowsDecimal: boolean
  /** Words of the value scale, up to four; only the used ones are submitted. */
  valueLabels: string[]
  direction: Direction
  scheduleType: ScheduleType
  weekdays: number[]
  timesPerWeek: string
}

function initialState(habit: Habit | null | undefined, areaId?: number): FormState {
  if (!habit) {
    return {
      name: '',
      description: '',
      areaId: areaId === undefined ? '' : String(areaId),
      // A new habit is ordinary unless the user says otherwise, and carries no
      // judgement about which end of its scale is good.
      importance: 'normal',
      weight: 1,
      markKind: 'completion',
      quantityUnit: '',
      allowsDecimal: false,
      valueLabels: [...DEFAULT_SCALE_LABELS.ordinal_4],
      direction: 'neutral',
      scheduleType: 'daily',
      weekdays: [0, 1, 2, 3, 4],
      timesPerWeek: '3',
    }
  }

  const markKind = markKindOf(habit.tracking_mode, habit.value_type)
  return {
    name: habit.name,
    description: habit.description ?? '',
    areaId: String(habit.area_id),
    importance: habit.importance,
    weight: habit.weight,
    markKind,
    quantityUnit: habit.quantity_unit ?? '',
    allowsDecimal: habit.quantity_allows_decimal,
    valueLabels: [...(habit.value_labels ?? DEFAULT_SCALE_LABELS.ordinal_4)],
    direction: habit.direction ?? 'neutral',
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

  if (state.markKind === 'quantity' && state.quantityUnit.trim() === '') {
    problems.push('Укажите единицу измерения, например страницы, км или повторения.')
  }

  const isValue = valueTypeOf(state.markKind) !== null
  if (isValue) {
    const labels = state.valueLabels
      .slice(0, scaleLengthOf(state.markKind))
      .map((label) => label.trim())
    if (labels.some((label) => label === '')) {
      problems.push('У каждого значения шкалы должно быть слово.')
    } else if (new Set(labels).size !== labels.length) {
      // Two positions with the same word leave the user unable to tell the
      // answers apart on the check-in screen, so they are refused up front.
      problems.push('Слова шкалы должны различаться.')
    }
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
  const quantity = state.markKind === 'quantity'
  const valueType = valueTypeOf(state.markKind)
  return {
    name: state.name.trim(),
    description: state.description.trim() === '' ? null : state.description.trim(),
    area_id: Number(state.areaId),
    weight: state.weight,
    importance: state.importance,
    tracking_mode: quantity ? 'binary_quantity' : 'binary',
    quantity_unit: quantity ? state.quantityUnit.trim() : null,
    quantity_allows_decimal: quantity ? state.allowsDecimal : false,
    value_type: valueType,
    value_labels:
      valueType === null
        ? null
        : state.valueLabels
            .slice(0, scaleLengthOf(state.markKind))
            .map((label) => label.trim()),
    direction: valueType === null ? null : state.direction,
    schedule: buildSchedule(state),
  }
}

export function HabitForm({ areas, habit = null, areaId, onSaved, onCancel }: HabitFormProps) {
  const [state, setState] = useState<FormState>(() => initialState(habit, areaId))
  const [problems, setProblems] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setState((current) => ({ ...current, [key]: value }))
  }

  /**
   * Switching the mark kind re-states the words of the new scale.
   *
   * A scale's words belong to that scale, so «0 / мало / нормально / много» must
   * not survive into a да/нет habit: the two positions would carry the wrong
   * words until the user noticed.
   */
  function changeMarkKind(kind: MarkKind) {
    setState((current) => {
      const valueType = valueTypeOf(kind)
      return {
        ...current,
        markKind: kind,
        valueLabels:
          valueType === null ? current.valueLabels : [...DEFAULT_SCALE_LABELS[valueType]],
      }
    })
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
  // A value habit asks «how much» instead of «did it happen», so its scale, its
  // words and its direction are part of the form; a completion habit has none.
  const isValueHabit = valueTypeOf(state.markKind) !== null
  // «Выполнено и количество» is legacy: offered only while editing a habit that
  // already uses it, so no new habit can select it.
  const markKinds = markKindOptions(markKindOf(habit?.tracking_mode ?? 'binary', habit?.value_type ?? null))

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
        {!habit && areaId !== undefined ? (
          <div className="field">
            <span className="field__label">Сфера</span>
            <span>{areas.find((area) => area.id === areaId)?.name}</span>
          </div>
        ) : (
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
        )}

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
                {option.label}
              </option>
            ))}
          </select>
          <span className="field__hint">Насколько привычка важна для оценки дня и недели.</span>
        </div>
      </div>

      <fieldset className="fieldset">
        <legend className="fieldset__legend">Тип отметки</legend>
        <div className="choice-group">
          {markKinds.map((option) => (
            <label key={option.value} className="choice">
              <input
                type="radio"
                name="mark-kind"
                value={option.value}
                checked={state.markKind === option.value}
                onChange={() => changeMarkKind(option.value)}
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

        {isValueHabit ? (
          <div className="field-row">
            <div className="field">
              <span className="field__label">Значения шкалы</span>
              {state.valueLabels
                .slice(0, scaleLengthOf(state.markKind))
                .map((label, index) => (
                  <input
                    key={index}
                    aria-label={`Значение ${index}`}
                    className="field__input"
                    maxLength={40}
                    value={label}
                    placeholder={DEFAULT_SCALE_LABELS.ordinal_4[index]}
                    onChange={(event) =>
                      update(
                        'valueLabels',
                        state.valueLabels.map((current, position) =>
                          position === index ? event.target.value : current,
                        ),
                      )
                    }
                  />
                ))}
            </div>
            <div className="field">
              <label className="field__label" htmlFor="habit-direction">
                Направление
              </label>
              <select
                id="habit-direction"
                className="field__input"
                value={state.direction}
                onChange={(event) => update('direction', event.target.value as Direction)}
              >
                {DIRECTION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="field__hint">
                «Полезная» — больше значит лучше, «Вредная» — меньше значит лучше.
                «Нейтральная» ничего не оценивает и влияет только на заполнение.
              </span>
            </div>
          </div>
        ) : null}

        {state.markKind === 'quantity' ? (
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

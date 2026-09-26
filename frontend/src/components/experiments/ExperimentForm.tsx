import { useState, type FormEvent } from 'react'

import { describeApiError } from '../../api/client'
import { createExperiment, updateExperiment } from '../../api/experiments'
import type { Experiment } from '../../api/experiments'
import { ErrorBanner } from '../Feedback'

export interface ExperimentFormProps {
  /** The experiment being edited, or null when creating a new one. */
  experiment?: Experiment | null
  /** Today's ISO date, so a new experiment defaults to a sensible window. */
  today: string
  onSaved: (experiment: Experiment) => void
  onCancel: () => void
}

interface FormState {
  title: string
  hypothesis: string
  protocol: string
  startDate: string
  endDate: string
}

/**
 * Add days to an ISO date without timezone drift (local components only).
 */
function addDays(iso: string, days: number): string {
  const [year = 1970, month = 1, day = 1] = iso.split('-').map(Number)
  const value = new Date(year, month - 1, day)
  value.setDate(value.getDate() + days)
  const monthPart = `${value.getMonth() + 1}`.padStart(2, '0')
  const dayPart = `${value.getDate()}`.padStart(2, '0')
  return `${value.getFullYear()}-${monthPart}-${dayPart}`
}

function initialState(experiment: Experiment | null | undefined, today: string): FormState {
  if (experiment) {
    return {
      title: experiment.title,
      hypothesis: experiment.hypothesis,
      protocol: experiment.protocol,
      startDate: experiment.start_date,
      endDate: experiment.end_date,
    }
  }
  return {
    title: '',
    hypothesis: '',
    protocol: '',
    startDate: today,
    endDate: addDays(today, 13),
  }
}

/** Mirrors the backend rules so the form cannot submit a contradictory window. */
function validate(state: FormState): string[] {
  const problems: string[] = []
  if (state.title.trim() === '') problems.push('Введите название эксперимента.')
  if (state.hypothesis.trim() === '') problems.push('Опишите гипотезу: что вы ожидаете увидеть.')
  if (state.protocol.trim() === '') problems.push('Опишите, что именно вы меняете.')
  if (state.startDate === '' || state.endDate === '') {
    problems.push('Укажите даты начала и окончания.')
  } else if (state.endDate < state.startDate) {
    problems.push('Дата окончания не может быть раньше даты начала.')
  }
  return problems
}

export function ExperimentForm({ experiment = null, today, onSaved, onCancel }: ExperimentFormProps) {
  const [state, setState] = useState<FormState>(() => initialState(experiment, today))
  const [problems, setProblems] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setState((current) => ({ ...current, [key]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const found = validate(state)
    setProblems(found)
    setError(null)
    if (found.length > 0) return

    setSaving(true)
    try {
      const input = {
        title: state.title.trim(),
        hypothesis: state.hypothesis.trim(),
        protocol: state.protocol.trim(),
        start_date: state.startDate,
        end_date: state.endDate,
      }
      // A started experiment may still have its text corrected, but dates are
      // only sent while the window can change; the backend enforces the policy.
      const saved = experiment
        ? await updateExperiment(experiment.id, input)
        : await createExperiment(input)
      onSaved(saved)
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card experiment-form" onSubmit={handleSubmit} noValidate>
      <h3 className="card__title">
        {experiment ? `Изменить: ${experiment.title}` : 'Новый эксперимент'}
      </h3>

      <div className="field">
        <label className="field__label" htmlFor="experiment-title">
          Название
        </label>
        <input
          id="experiment-title"
          className="field__input"
          value={state.title}
          maxLength={120}
          placeholder="Например: Без алкоголя 14 дней"
          onChange={(event) => update('title', event.target.value)}
        />
      </div>

      <div className="field">
        <label className="field__label" htmlFor="experiment-hypothesis">
          Гипотеза
        </label>
        <textarea
          id="experiment-hypothesis"
          className="field__input"
          rows={3}
          value={state.hypothesis}
          maxLength={2000}
          placeholder="Что вы предполагаете увидеть в этот период."
          onChange={(event) => update('hypothesis', event.target.value)}
        />
        <span className="field__hint">
          Это ваша формулировка, а не вывод системы: Tracker покажет только то, как
          показатели соотносились с периодом.
        </span>
      </div>

      <div className="field">
        <label className="field__label" htmlFor="experiment-protocol">
          Что меняем
        </label>
        <textarea
          id="experiment-protocol"
          className="field__input"
          rows={3}
          value={state.protocol}
          maxLength={2000}
          placeholder="Например: не употреблять алкоголь с 1 по 14 октября."
          onChange={(event) => update('protocol', event.target.value)}
        />
      </div>

      <div className="field-row">
        <div className="field">
          <label className="field__label" htmlFor="experiment-start">
            Дата начала
          </label>
          <input
            id="experiment-start"
            className="field__input field__input--date"
            type="date"
            value={state.startDate}
            onChange={(event) => update('startDate', event.target.value)}
          />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="experiment-end">
            Дата окончания
          </label>
          <input
            id="experiment-end"
            className="field__input field__input--date"
            type="date"
            value={state.endDate}
            onChange={(event) => update('endDate', event.target.value)}
          />
        </div>
      </div>

      {problems.length > 0 ? (
        <ul className="banner banner--error" role="alert">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      ) : null}

      <ErrorBanner message={error} />

      <div className="card__actions">
        <button type="submit" className="button button--primary" disabled={saving}>
          {saving ? 'Сохранение…' : experiment ? 'Сохранить изменения' : 'Создать эксперимент'}
        </button>
        <button type="button" className="button" onClick={onCancel} disabled={saving}>
          Отмена
        </button>
      </div>
    </form>
  )
}

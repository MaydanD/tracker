import { useState } from 'react'
import { Link } from 'react-router-dom'

import { describeApiError } from '../api/client'
import { cancelExperiment, fetchExperiments } from '../api/experiments'
import type { Experiment } from '../api/experiments'
import { EmptyState, ErrorBanner, LoadingText } from '../components/Feedback'
import { ExperimentForm } from '../components/experiments/ExperimentForm'
import { formatPhase, formatRange, STATUS_LABELS } from '../components/experiments/labels'
import { OwlAssistantBanner } from '../components/owl/OwlAssistantBanner'
import { localTodayIso } from '../components/daily/dates'
import { useAsyncData } from '../hooks/useAsyncData'

export function ExperimentsPage() {
  const [today] = useState(() => localTodayIso())
  const list = useAsyncData((signal) => fetchExperiments(signal), [])
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Experiment | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const experiments = list.data?.experiments ?? []

  function closeForm() {
    setCreating(false)
    setEditing(null)
  }

  async function handleCancel(experiment: Experiment) {
    setBusyId(experiment.id)
    setActionError(null)
    try {
      await cancelExperiment(experiment.id)
      if (editing?.id === experiment.id) closeForm()
      list.reload()
    } catch (cause) {
      setActionError(describeApiError(cause))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Эксперименты</h1>
        <span className="badge">Этап 10</span>
      </header>
      <p className="page__summary">
        Личные эксперименты: задайте период и гипотезу, а затем посмотрите, как показатели
        Tracker соотносились с этим периодом — до, во время и после.
      </p>

      <OwlAssistantBanner state={list.data?.owl ?? null} />

      <div className="toolbar">
        <button
          type="button"
          className="button button--primary"
          onClick={() => {
            setEditing(null)
            setCreating(true)
          }}
          disabled={creating || editing !== null}
        >
          Новый эксперимент
        </button>
      </div>

      <ErrorBanner message={actionError} />
      <ErrorBanner message={list.error} />

      {creating || editing ? (
        <ExperimentForm
          key={editing?.id ?? 'new'}
          experiment={editing}
          today={today}
          onSaved={() => {
            closeForm()
            list.reload()
          }}
          onCancel={closeForm}
        />
      ) : null}

      {list.loading && list.data === null ? (
        <LoadingText>Загрузка экспериментов…</LoadingText>
      ) : experiments.length === 0 ? (
        <EmptyState>
          Экспериментов пока нет. Создайте первый — например, «Без алкоголя 14 дней».
        </EmptyState>
      ) : (
        <ul className="experiment-list">
          {experiments.map((experiment) => (
            <li
              key={experiment.id}
              className={`experiment-card experiment-card--${experiment.status}`}
            >
              <div className="experiment-card__head">
                <Link className="experiment-card__title" to={`/experiments/${experiment.id}`}>
                  {experiment.title}
                </Link>
                <span className={`experiment-status experiment-status--${experiment.status}`}>
                  {STATUS_LABELS[experiment.status]}
                </span>
              </div>

              <p className="experiment-card__dates">{formatRange(experiment.start_date, experiment.end_date)}</p>
              <p className="experiment-card__phase">{formatPhase(experiment)}</p>
              <p className="experiment-card__hypothesis">{experiment.hypothesis}</p>

              <div className="experiment-card__actions">
                <Link className="button button--small" to={`/experiments/${experiment.id}`}>
                  Открыть
                </Link>
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => setEditing(experiment)}
                  disabled={creating || editing !== null}
                >
                  Изменить
                </button>
                {experiment.status === 'scheduled' || experiment.status === 'active' ? (
                  <button
                    type="button"
                    className="button button--small"
                    onClick={() => void handleCancel(experiment)}
                    disabled={busyId === experiment.id}
                  >
                    {busyId === experiment.id ? 'Останавливаем…' : 'Отменить'}
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

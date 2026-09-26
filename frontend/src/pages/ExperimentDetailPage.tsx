import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { fetchExperiment } from '../api/experiments'
import { EmptyState, ErrorBanner, InfoBanner, LoadingText } from '../components/Feedback'
import { ExperimentChart } from '../components/experiments/ExperimentChart'
import {
  ExperimentAverages,
  ExperimentHabitsTable,
  ExperimentOverall,
  ExperimentStateTable,
} from '../components/experiments/ExperimentComparison'
import { ExperimentForm } from '../components/experiments/ExperimentForm'
import {
  formatCoverage,
  formatDate,
  formatPhase,
  formatRange,
  STATUS_LABELS,
} from '../components/experiments/labels'
import { ExperimentTimeline } from '../components/experiments/ExperimentTimeline'
import { localTodayIso } from '../components/daily/dates'
import { useAsyncData } from '../hooks/useAsyncData'

export function ExperimentDetailPage() {
  const { experimentId } = useParams<{ experimentId: string }>()
  const id = Number(experimentId)
  const valid = Number.isInteger(id) && id > 0
  const [today] = useState(() => localTodayIso())
  const detail = useAsyncData(
    (signal) => (valid ? fetchExperiment(id, signal) : Promise.reject(new Error('bad id'))),
    [id, valid],
  )
  const [editing, setEditing] = useState(false)

  if (!valid) {
    return (
      <section className="page">
        <ErrorBanner message="Эксперимент не найден." />
        <p>
          <Link className="button" to="/experiments">Вернуться к списку</Link>
        </p>
      </section>
    )
  }

  if (detail.error !== null) {
    return (
      <section className="page">
        <header className="page__header">
          <h1 className="page__title">Эксперимент</h1>
        </header>
        <ErrorBanner message={detail.error} />
        <p>
          <Link className="button" to="/experiments">Вернуться к списку</Link>
        </p>
      </section>
    )
  }

  if (detail.data === null) {
    return (
      <section className="page">
        <LoadingText>Загрузка эксперимента…</LoadingText>
      </section>
    )
  }

  const { experiment, overlaps, analysis } = detail.data
  const canEditDates = experiment.status === 'scheduled' || experiment.status === 'active'

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">{experiment.title}</h1>
        <span className={`experiment-status experiment-status--${experiment.status}`}>
          {STATUS_LABELS[experiment.status]}
        </span>
      </header>
      <p className="experiment-detail__dates">
        {`${formatRange(experiment.start_date, experiment.end_date)} · ${formatPhase(experiment)}`}
      </p>

      <div className="experiment-detail__actions">
        <Link className="button button--small" to="/experiments">
          К списку
        </Link>
        <button
          type="button"
          className="button button--small"
          onClick={() => setEditing((value) => !value)}
        >
          {editing ? 'Свернуть' : 'Изменить'}
        </button>
      </div>

      {editing ? (
        <ExperimentForm
          experiment={experiment}
          today={today}
          onSaved={() => {
            setEditing(false)
            detail.reload()
          }}
          onCancel={() => setEditing(false)}
        />
      ) : null}

      {overlaps.length > 0 ? (
        <InfoBanner>
          {`В этот период пересекался ещё ${overlaps.length} ${pluralExperiments(overlaps.length)}. `}
          Одновременные эксперименты затрудняют интерпретацию: изменения могли совпасть с обоими.
        </InfoBanner>
      ) : null}

      <div className="experiment-detail__grid">
        <div className="card experiment-note">
          <h2 className="card__title">Гипотеза</h2>
          <p>{experiment.hypothesis}</p>
        </div>
        <div className="card experiment-note">
          <h2 className="card__title">Что меняем</h2>
          <p>{experiment.protocol}</p>
        </div>
      </div>

      <h2 className="experiment-section__title">Периоды</h2>
      <ExperimentTimeline windows={analysis.windows} today={today} />

      <h2 className="experiment-section__title">Общий прогресс</h2>
      <ExperimentOverall overall={analysis.overall} />

      <h2 className="experiment-section__title">Динамика по дням</h2>
      <ExperimentChart series={analysis.series} />

      <h2 className="experiment-section__title">Состояние дня</h2>
      <ExperimentStateTable state={analysis.state} />
      <ExperimentAverages state={analysis.state} />

      <h2 className="experiment-section__title">Привычки</h2>
      <ExperimentHabitsTable habits={analysis.habits} />

      <h2 className="experiment-section__title">Качество данных</h2>
      <ul className="experiment-coverage">
        <li>
          {`До: ${formatCoverage(analysis.overall.before.coverage)}`}
        </li>
        <li>
          {`Во время: ${formatCoverage(analysis.overall.during.coverage)}`}
        </li>
        <li>
          {`После: ${formatCoverage(analysis.overall.after.coverage)}`}
        </li>
      </ul>

      <h2 className="experiment-section__title">Итог</h2>
      {analysis.sufficient ? (
        <p className="experiment-summary">{analysis.summary}</p>
      ) : (
        <EmptyState>{analysis.summary}</EmptyState>
      )}
      <p className="experiment-disclaimer">
        Это описание того, как показатели соотносились с периодом, а не доказательство
        причинности: эксперимент не устанавливает, что именно стало причиной изменений.
      </p>

      {canEditDates ? null : (
        <p className="experiment-detail__frozen">
          {`Даты завершённого эксперимента не меняются — история остаётся сопоставимой. Последний день периода: ${formatDate(experiment.cancelled_on ?? experiment.end_date)}.`}
        </p>
      )}
    </section>
  )
}

function pluralExperiments(count: number): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return 'эксперимент'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'эксперимента'
  return 'экспериментов'
}

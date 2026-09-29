import { useState } from 'react'

import { fetchDay } from '../api/daily'
import { fetchProgress } from '../api/progress'
import { ProgressSummary } from '../components/daily/ProgressSummary'
import { EmptyState, ErrorBanner, InfoBanner, LoadingText } from '../components/Feedback'
import { DayNavigator } from '../components/daily/DayNavigator'
import { CheckInGrid } from '../components/daily/CheckInGrid'
import { refreshOwl } from '../components/owl/owlStore'
import { formatDayLabel, localTodayIso } from '../components/daily/dates'
import { useAsyncData } from '../hooks/useAsyncData'

/**
 * Итоги дня — answer the day's habits for a chosen calendar date.
 *
 * The screen shows the habits that are active on that date, grouped into their
 * spheres (Тело, Развитие, Досуг, Питание). A habit answered with a
 * completion offers «Выполнено / Не выполнено / Пропуск»; a habit answered on a
 * value scale (да/нет, 0…3) offers exactly the words the user configured, and a
 * recorded `0` is a real answer rather than a missing one. Nothing about either
 * kind is hardcoded here — the scale, its labels and the direction come from the
 * habit's configuration, and so does the optional importance shown with it.
 *
 * Habits, not a separate daily-state form: mood, energy, sleep, alcohol, games
 * and computer use are ordinary habits now, so the user has one place per day
 * instead of two. The old daily-state records stay readable through their own
 * endpoint for history and analytics.
 */
export function CheckInPage() {
  const [entryDate, setEntryDate] = useState(() => localTodayIso())
  const [revision, setRevision] = useState(0)

  const { data, error, loading } = useAsyncData(
    (signal) => fetchDay(entryDate, signal),
    [entryDate, revision],
  )
  const derived = useAsyncData(
    (signal) => fetchProgress(entryDate, signal),
    [entryDate, revision],
  )
  const progress =
    derived.data?.day.entry_date === entryDate ? derived.data : null

  function refresh() {
    setRevision((value) => value + 1)
    refreshOwl()
  }

  // Keep the last result for this date visible during refresh, and never render
  // one day's controls under another day's label.
  const day = data !== null && data.entry_date === entryDate ? data : null
  const today = data?.today ?? localTodayIso()
  const isFuture = day?.is_future ?? false

  return (
    <section className="page checkin-page">
      <h1 className="sr-only">Итоги дня</h1>

      <DayNavigator
        entryDate={entryDate}
        today={today}
        disabled={loading}
        onChange={setEntryDate}
      />

      {isFuture ? (
        <InfoBanner>
          Будущий день: показатели нельзя отметить заранее — вернитесь к этой дате,
          когда она начнётся.
        </InfoBanner>
      ) : null}

      <ErrorBanner message={error} />
      <ErrorBanner message={derived.error} />
      {derived.error ? (
        <button className="button" onClick={derived.reload}>
          Повторить расчёт
        </button>
      ) : null}

      {progress ? <ProgressSummary progress={progress} /> : null}

      {day === null ? (
        <LoadingText>Загрузка показателей за {formatDayLabel(entryDate)}…</LoadingText>
      ) : day.items.length === 0 ? (
        <EmptyState>
          На эту дату привычек ещё нет. Привычка действует с даты её создания —
          выберите более позднюю дату.
        </EmptyState>
      ) : (
        <CheckInGrid
          items={day.items}
          entryDate={entryDate}
          isFuture={isFuture}
          onChanged={refresh}
          progress={progress}
          includeDailyState={false}
          groupByArea
        />
      )}
    </section>
  )
}

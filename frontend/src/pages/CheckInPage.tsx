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
 * Итоги дня — record what happened for each habit on a chosen calendar date.
 *
 * Two states are deliberately kept apart in the wording and in the data:
 * «Нет отметки» means nothing has been recorded, «Пропущено» means the user
 * said the habit was not done. Clearing a day returns it to «Нет отметки»;
 * Tracker never turns silence into a miss.
 *
 * Past days stay editable. For a future day only a planned skip is offered —
 * and the backend refuses anything else regardless of what is clicked.
 */
export function CheckInPage() {
  // The initial day is the browser's local date; everything that follows (the
  // «Сегодня» button, «Вчера»/«Завтра», which rules apply) comes from the
  // server's date in the response, so both sides agree on what "today" is.
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
    derived.data?.day.entry_date === entryDate
      ? derived.data
      : null

  function refresh() {
    setRevision((value) => value + 1)
    // Marking a day can change the Owl (all done, miss pile-up, records), so
    // the header mascot is refreshed alongside the day's own data.
    refreshOwl()
  }

  // Keep this date's last result visible during refresh. Removing the summary
  // briefly shrinks the document, drops its scrollbar and can change grid columns.
  // Only the response for the date in the navigator is shown. A reload (after
  // a save, or while another day loads) therefore never renders one day's
  // records — or one day's enabled actions — under a different day's label.
  const day = data !== null && data.entry_date === entryDate ? data : null

  const isFuture = day?.is_future ?? false
  // `today` is the server's date and does not depend on the requested day, so
  // it may come from any loaded response.
  const today = data?.today ?? localTodayIso()

  return (
    <section className="page checkin-page">
      {/*
       * The screen's heading. The design has no visible title, but the page
       * still needs one: it names the screen for screen readers and gives the
       * «Оценка дня»/«Оценка недели» subheadings something to belong to.
       */}
      <h1 className="sr-only">Итоги дня</h1>

      {/* ── Compact date navigator ─────────────────────────── */}
      <DayNavigator
        entryDate={entryDate}
        today={today}
        disabled={loading}
        onChange={setEntryDate}
      />

      {isFuture ? (
        <InfoBanner>
          Будущий день: можно только запланировать пропуск. «Выполнено» и
          «Пропущено» появятся, когда день начнётся.
        </InfoBanner>
      ) : null}

      <ErrorBanner message={error} />
      <ErrorBanner message={derived.error} />
      {derived.error ? (
        <button className="button" onClick={derived.reload}>
          Повторить расчёт
        </button>
      ) : null}

      {/* ── Progress summary (compact, above the grid) ──────── */}
      {progress ? (
        <ProgressSummary progress={progress} />
      ) : null}

      {/* ── Unified check-in grid ───────────────────────────── */}
      {day === null ? (
        <LoadingText>Загрузка отметок за {formatDayLabel(entryDate)}…</LoadingText>
      ) : (
        <>
          {day.items.length === 0 ? (
            <EmptyState>
              На эту дату ещё нет привычек: ни одна привычка не была настроена так
              рано. Создайте привычку или выберите другую дату.
            </EmptyState>
          ) : null}
          <CheckInGrid
            key={entryDate}
            items={day.items}
            entryDate={day.entry_date}
            isFuture={day.is_future}
            onChanged={refresh}
            progress={progress}
          />
        </>
      )}
    </section>
  )
}

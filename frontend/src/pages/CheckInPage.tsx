import { useState } from 'react'

import { fetchDay } from '../api/daily'
import { EmptyState, ErrorBanner, InfoBanner, LoadingText } from '../components/Feedback'
import { DayNavigator } from '../components/daily/DayNavigator'
import { HabitDayList } from '../components/daily/HabitDayList'
import { formatDayLabel, localTodayIso } from '../components/daily/dates'
import { useAsyncData } from '../hooks/useAsyncData'

/**
 * Итоги дня — record what happened for each habit on a chosen calendar date.
 *
 * Two states are deliberately kept apart in the wording and in the data:
 * «Нет отметки» means nothing has been recorded, «Пропущено» means the user said
 * the habit was not done. Clearing a day returns it to «Нет отметки»; Tracker
 * never turns silence into a miss.
 *
 * Past days stay editable. For a future day only a planned skip is offered —
 * and the backend refuses anything else regardless of what is clicked.
 */
export function CheckInPage() {
  // The initial day is the browser's local date; everything that follows (the
  // «Сегодня» button, «Вчера»/«Завтра», which rules apply) comes from the
  // server's date in the response, so both sides agree on what "today" is.
  const [entryDate, setEntryDate] = useState(() => localTodayIso())

  const { data, error, loading, reload } = useAsyncData(
    (signal) => fetchDay(entryDate, signal),
    [entryDate],
  )

  // Only the response for the date in the navigator is shown. A reload (after a
  // save, or while another day loads) therefore never renders one day's records
  // — or one day's enabled actions — under a different day's label.
  const day = data !== null && data.entry_date === entryDate ? data : null

  const isFuture = day?.is_future ?? false
  // `today` is the server's date and does not depend on the requested day, so it
  // may come from any loaded response.
  const today = data?.today ?? localTodayIso()

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Итоги дня</h1>
        <span className="badge">Этап 3</span>
      </header>
      <p className="page__summary">
        Отметьте состояние каждой привычки за выбранный день. Запись можно
        изменить или полностью убрать — тогда день снова станет «Нет отметки».
        Отсутствие отметки не превращается в пропуск само по себе.
      </p>

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

      {day === null ? (
        <LoadingText>Загрузка отметок за {formatDayLabel(entryDate)}…</LoadingText>
      ) : day.items.length === 0 ? (
        <EmptyState>
          На эту дату ещё нет привычек: ни одна привычка не была настроена так
          рано. Создайте привычку или выберите другую дату.
        </EmptyState>
      ) : (
        <HabitDayList
          items={day.items}
          entryDate={day.entry_date}
          isFuture={day.is_future}
          onChanged={reload}
        />
      )}
    </section>
  )
}

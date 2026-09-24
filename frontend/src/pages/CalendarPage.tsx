import { useEffect, useState } from 'react'

import { fetchCalendarRange, fetchDayOverview, type CalendarDaySummaryRead, type DayOverviewRead } from '../api/calendar'
import { ErrorBanner, LoadingText } from '../components/Feedback'
import { statusLabel } from '../components/daily/status'
import { describeApiError } from '../api/client'
import {
  SHORT_WEEKDAYS_MON_FIRST,
  formatFullDateLabel,
  formatIsoDate,
  formatMonthTitle,
  formatShortDateLabel,
  getMonthGridDays,
  getYearGridWeeks,
  monthGridBounds,
  nextMonth,
  parseIsoParts,
  prevMonth,
  yearBounds,
} from '../utils/dateUtils'
import { formatMinutes, formatSleepStatus } from '../utils/formatters'

export function CalendarPage() {
  const now = new Date()
  const [currentYear, setCurrentYear] = useState(() => now.getFullYear())
  const [currentMonth, setCurrentMonth] = useState(() => now.getMonth() + 1)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  // Calendar month state
  const [monthData, setMonthData] = useState<Record<string, CalendarDaySummaryRead>>({})
  const [monthLoading, setMonthLoading] = useState(true)
  const [monthError, setMonthError] = useState<string | null>(null)

  // Heatmap year state
  const [heatmapYear, setHeatmapYear] = useState(() => now.getFullYear())
  const [yearData, setYearData] = useState<Record<string, CalendarDaySummaryRead>>({})
  const [yearError, setYearError] = useState<string | null>(null)

  // Selected Day Card state
  const [dayOverview, setDayOverview] = useState<DayOverviewRead | null>(null)
  const [dayLoading, setDayLoading] = useState(false)
  const [dayError, setDayError] = useState<string | null>(null)

  // 1. Fetch Month Data with Async Race Protection
  useEffect(() => {
    const controller = new AbortController()
    setMonthLoading(true)
    setMonthError(null)

    const { start, end } = monthGridBounds(currentYear, currentMonth)
    fetchCalendarRange(start, end, controller.signal)
      .then((items) => {
        if (controller.signal.aborted) return
        const map: Record<string, CalendarDaySummaryRead> = {}
        for (const item of items) {
          map[item.entry_date] = item
        }
        setMonthData(map)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setMonthError(describeApiError(err))
      })
      .finally(() => {
        if (!controller.signal.aborted) setMonthLoading(false)
      })

    return () => controller.abort()
  }, [currentYear, currentMonth])

  // 2. Fetch Heatmap Year Data with Async Race Protection
  useEffect(() => {
    const controller = new AbortController()
    setYearError(null)

    const { start, end } = yearBounds(heatmapYear)
    fetchCalendarRange(start, end, controller.signal)
      .then((items) => {
        if (controller.signal.aborted) return
        const map: Record<string, CalendarDaySummaryRead> = {}
        for (const item of items) {
          map[item.entry_date] = item
        }
        setYearData(map)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setYearError(describeApiError(err))
      })

    return () => controller.abort()
  }, [heatmapYear])

  // 3. Fetch Selected Day Overview with Async Race Protection
  useEffect(() => {
    if (!selectedDate) {
      setDayOverview(null)
      return
    }

    const controller = new AbortController()
    setDayLoading(true)
    setDayError(null)

    fetchDayOverview(selectedDate, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setDayOverview(data)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setDayError(describeApiError(err))
      })
      .finally(() => {
        if (!controller.signal.aborted) setDayLoading(false)
      })

    return () => controller.abort()
  }, [selectedDate])

  const todayIso = formatIsoDate(now.getFullYear(), now.getMonth() + 1, now.getDate())
  const monthGridDays = getMonthGridDays(currentYear, currentMonth)
  const yearWeeks = getYearGridWeeks(heatmapYear)

  const handlePrevMonth = () => {
    const p = prevMonth(currentYear, currentMonth)
    setCurrentYear(p.year)
    setCurrentMonth(p.month)
  }

  const handleNextMonth = () => {
    const n = nextMonth(currentYear, currentMonth)
    setCurrentYear(n.year)
    setCurrentMonth(n.month)
  }

  const handleTodayMonth = () => {
    setCurrentYear(now.getFullYear())
    setCurrentMonth(now.getMonth() + 1)
  }

  function getHeatmapLevelClass(item: CalendarDaySummaryRead | undefined): string {
    if (!item || item.is_future || !item.has_obligations || item.daily_score === null) {
      return 'heatmap-cell--null'
    }
    const score = item.daily_score
    if (score <= 0) return 'heatmap-cell--level-0'
    if (score <= 25) return 'heatmap-cell--level-1'
    if (score <= 50) return 'heatmap-cell--level-2'
    if (score <= 75) return 'heatmap-cell--level-3'
    if (score < 100) return 'heatmap-cell--level-4'
    return 'heatmap-cell--level-5'
  }

  function getHeatmapTooltip(date: string, item: CalendarDaySummaryRead | undefined): string {
    const shortDate = formatShortDateLabel(date)
    if (!item || item.is_future) return `${shortDate}: Будущий день`
    if (!item.has_obligations || item.daily_score === null) return `${shortDate}: Нет обязательств`
    return `${shortDate}: ${item.daily_score.toFixed(1)}%`
  }

  return (
    <section className="page calendar-page">
      <header className="page__header">
        <h1 className="page__title">Календарь и тепловая карта</h1>
        <span className="badge">Этап 6</span>
      </header>
      <p className="page__summary">
        Просматривайте историю выполнений по месяцам и за весь год. Выберите любой день для просмотра деталей.
      </p>

      {/* Section 1: Месячный календарь */}
      <section className="calendar-section" aria-label="Месячный календарь">
        <header className="calendar-header">
          <h2 className="calendar-header__title">{formatMonthTitle(currentYear, currentMonth)}</h2>
          <div className="calendar-header__controls">
            <button className="button button--small" onClick={handlePrevMonth} aria-label="Предыдущий месяц">
              ←
            </button>
            <button className="button button--small" onClick={handleTodayMonth}>
              Сегодня
            </button>
            <button className="button button--small" onClick={handleNextMonth} aria-label="Следующий месяц">
              →
            </button>
          </div>
        </header>

        <ErrorBanner message={monthError} />

        <div className="calendar-grid">
          {SHORT_WEEKDAYS_MON_FIRST.map((wd) => (
            <div key={wd} className="calendar-grid__weekday">
              {wd}
            </div>
          ))}

          {monthGridDays.map((dateStr) => {
            const parts = parseIsoParts(dateStr)
            const isCurrentMonth = parts.month === currentMonth
            const item = monthData[dateStr]
            const isToday = dateStr === todayIso
            const isSelected = dateStr === selectedDate

            let cellClasses = 'calendar-cell'
            if (!isCurrentMonth) cellClasses += ' calendar-cell--other-month'
            if (isToday) cellClasses += ' calendar-cell--today'
            if (isSelected) cellClasses += ' calendar-cell--selected'

            return (
              <button
                key={dateStr}
                type="button"
                className={cellClasses}
                onClick={() => setSelectedDate(dateStr)}
                aria-label={`Выбрать день ${formatShortDateLabel(dateStr)}`}
              >
                <div className="calendar-cell__num">{parts.day}</div>
                {item ? (
                  <div>
                    <div className="calendar-cell__score">
                      {item.is_future || !item.has_obligations || item.daily_score === null
                        ? '—'
                        : `${item.daily_score.toFixed(0)}%`}
                    </div>
                    {item.has_daily_state && item.mood !== null ? (
                      <div className="calendar-cell__mood">● {item.mood}</div>
                    ) : null}
                  </div>
                ) : monthLoading ? (
                  <div className="calendar-cell__score">…</div>
                ) : null}
              </button>
            )
          })}
        </div>
      </section>

      {/* Section 2: Годовая Heatmap */}
      <section className="calendar-section" aria-label="Активность за год">
        <header className="calendar-header">
          <h2 className="calendar-header__title">Активность за {heatmapYear} год</h2>
          <div className="calendar-header__controls">
            <button
              className="button button--small"
              onClick={() => setHeatmapYear((y) => y - 1)}
              aria-label="Предыдущий год"
            >
              ←
            </button>
            <button
              className="button button--small"
              onClick={() => setHeatmapYear(now.getFullYear())}
            >
              Текущий год
            </button>
            <button
              className="button button--small"
              onClick={() => setHeatmapYear((y) => y + 1)}
              aria-label="Следующий год"
            >
              →
            </button>
          </div>
        </header>

        <ErrorBanner message={yearError} />

        <div className="heatmap-container">
          <div className="heatmap-grid" role="grid" aria-label={`Тепловая карта за ${heatmapYear} год`}>
            {yearWeeks.map((week, wIdx) => (
              <div key={wIdx} className="heatmap-week">
                {week.map((dateStr) => {
                  const item = yearData[dateStr]
                  const isSelected = dateStr === selectedDate
                  const levelClass = getHeatmapLevelClass(item)
                  const tooltip = getHeatmapTooltip(dateStr, item)

                  return (
                    <button
                      key={dateStr}
                      type="button"
                      title={tooltip}
                      aria-label={tooltip}
                      className={`heatmap-cell ${levelClass} ${isSelected ? 'heatmap-cell--selected' : ''}`}
                      onClick={() => setSelectedDate(dateStr)}
                    />
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Section 3: Карточка выбранного дня */}
      {selectedDate ? (
        <section className="day-card-panel" aria-label="Карточка выбранного дня">
          <header className="day-card-panel__header">
            <h2 className="card__title">{formatFullDateLabel(selectedDate)}</h2>
            <button
              className="button button--small"
              onClick={() => setSelectedDate(null)}
              aria-label="Закрыть карточку дня"
            >
              ✕
            </button>
          </header>

          <ErrorBanner message={dayError} />

          {dayLoading ? (
            <LoadingText>Загрузка информации о дне…</LoadingText>
          ) : dayOverview ? (
            <>
              {/* Day Score & Weight */}
              <div className="dashboard-card__score">
                <span className="dashboard-card__score-value">
                  {dayOverview.progress.score === null
                    ? '—'
                    : `${dayOverview.progress.score.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`}
                </span>
                <span className="dashboard-card__score-sub">
                  {dayOverview.progress.score === null
                    ? 'Нет обязательных привычек'
                    : `Важность: ${dayOverview.progress.completed_weight} / ${dayOverview.progress.required_weight}`}
                </span>
              </div>

              {/* Habits */}
              <h3 className="card__title">Привычки дня</h3>
              {dayOverview.items.length === 0 ? (
                <p className="loading">На эту дату нет привычек.</p>
              ) : (
                <ul className="dashboard-habits-list">
                  {dayOverview.items.map((item) => {
                    const statusText = item.entry ? statusLabel(item.entry.status) : 'Нет отметки'
                    const statusClass = item.entry ? `state--${item.entry.status}` : 'state--none'
                    return (
                      <li key={item.habit_id} className="dashboard-habit-item">
                        <div className="dashboard-habit-item__main">
                          <span className="dashboard-habit-item__name">{item.name}</span>
                          {item.entry?.quantity_value !== null && item.entry?.quantity_value !== undefined ? (
                            <span className="dashboard-habit-item__meta">
                              Количество: {item.entry.quantity_value} {item.entry.quantity_unit ?? ''}
                            </span>
                          ) : null}
                          {item.entry?.note ? (
                            <span className="list__note">Заметка: {item.entry.note}</span>
                          ) : null}
                        </div>
                        <span className={`state ${statusClass}`}>{statusText}</span>
                      </li>
                    )
                  })}
                </ul>
              )}

              {/* Daily State */}
              <h3 className="card__title">Состояние дня</h3>
              {dayOverview.state === null ? (
                <div className="empty">Состояние дня не заполнено</div>
              ) : (
                <div className="state-summary-grid">
                  {dayOverview.state.mood !== null && dayOverview.state.mood !== undefined ? (
                    <div className="state-summary-item">
                      <span className="state-summary-item__label">Настроение</span>
                      <span className="state-summary-item__value">{dayOverview.state.mood} / 5</span>
                    </div>
                  ) : null}

                  {dayOverview.state.energy !== null && dayOverview.state.energy !== undefined ? (
                    <div className="state-summary-item">
                      <span className="state-summary-item__label">Энергия</span>
                      <span className="state-summary-item__value">{dayOverview.state.energy} / 5</span>
                    </div>
                  ) : null}

                  {dayOverview.state.wellbeing !== null && dayOverview.state.wellbeing !== undefined ? (
                    <div className="state-summary-item">
                      <span className="state-summary-item__label">Самочувствие</span>
                      <span className="state-summary-item__value">{dayOverview.state.wellbeing} / 5</span>
                    </div>
                  ) : null}

                  {(dayOverview.state.sleep_status || dayOverview.state.sleep_minutes !== null) ? (
                    <div className="state-summary-item">
                      <span className="state-summary-item__label">Сон</span>
                      <span className="state-summary-item__value">
                        {formatSleepStatus(dayOverview.state.sleep_status)}
                        {dayOverview.state.sleep_minutes !== null
                          ? ` · ${formatMinutes(dayOverview.state.sleep_minutes)}`
                          : ''}
                      </span>
                    </div>
                  ) : null}

                  {dayOverview.state.alcohol !== null && dayOverview.state.alcohol !== undefined ? (
                    <div className="state-summary-item">
                      <span className="state-summary-item__label">Алкоголь</span>
                      <span className="state-summary-item__value">
                        {dayOverview.state.alcohol
                          ? `Да${dayOverview.state.alcohol_detail ? ` · ${dayOverview.state.alcohol_detail}` : ''}`
                          : 'Нет'}
                      </span>
                    </div>
                  ) : null}

                  {dayOverview.state.gaming !== null && dayOverview.state.gaming !== undefined ? (
                    <div className="state-summary-item">
                      <span className="state-summary-item__label">Игры</span>
                      <span className="state-summary-item__value">
                        {dayOverview.state.gaming
                          ? formatMinutes(dayOverview.state.gaming_minutes)
                          : 'Нет'}
                      </span>
                    </div>
                  ) : null}

                  {dayOverview.state.computer_overuse !== null && dayOverview.state.computer_overuse !== undefined ? (
                    <div className="state-summary-item">
                      <span className="state-summary-item__label">Компьютер</span>
                      <span className="state-summary-item__value">
                        {dayOverview.state.computer_overuse
                          ? `Слишком много${dayOverview.state.computer_minutes !== null ? ` · ${formatMinutes(dayOverview.state.computer_minutes)}` : ''}`
                          : 'Нормально'}
                      </span>
                    </div>
                  ) : null}

                  {dayOverview.state.note ? (
                    <div className="state-summary-item" style={{ gridColumn: '1 / -1' }}>
                      <span className="state-summary-item__label">Заметка</span>
                      <span className="state-summary-item__value">{dayOverview.state.note}</span>
                    </div>
                  ) : null}
                </div>
              )}

              {/* Action Button */}
              <div className="card__actions" style={{ marginTop: '12px' }}>
                <a
                  href={`#/check-in?date=${selectedDate}`}
                  className="button button--primary"
                >
                  Открыть день →
                </a>
              </div>
            </>
          ) : null}
        </section>
      ) : null}
    </section>
  )
}

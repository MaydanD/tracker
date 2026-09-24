/**
 * Calendar-date helpers for the day screen.
 *
 * A day is an ISO string (`2026-09-24`), exactly like the API uses. Arithmetic
 * and formatting go through `Date` built from *local* components: parsing the ISO
 * string with `new Date('2026-09-24')` would treat it as UTC midnight and show the
 * previous day in any timezone west of Greenwich.
 */

const DAY_LABELS = [
  'воскресенье',
  'понедельник',
  'вторник',
  'среда',
  'четверг',
  'пятница',
  'суббота',
]

const MONTH_LABELS = [
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
]

/** Local calendar date for an ISO day string. */
export function parseIsoDate(iso: string): Date {
  const [year = 1970, month = 1, day = 1] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

/** ISO day string (`YYYY-MM-DD`) for a local date. */
export function toIsoDate(value: Date): string {
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** The ISO day `days` away from `iso` (negative goes back). */
export function addDays(iso: string, days: number): string {
  const value = parseIsoDate(iso)
  value.setDate(value.getDate() + days)
  return toIsoDate(value)
}

/** The browser's local date, used only to pick the day the screen opens on. */
export function localTodayIso(): string {
  return toIsoDate(new Date())
}

/** Human label, e.g. `24 сентября 2026, четверг`. */
export function formatDayLabel(iso: string): string {
  const value = parseIsoDate(iso)
  return (
    `${value.getDate()} ${MONTH_LABELS[value.getMonth()]} ${value.getFullYear()}, ` +
    DAY_LABELS[value.getDay()]
  )
}

/** Relative label (`Сегодня`, `Вчера`, `Завтра`), or `null` when it is unrelated. */
export function relativeDayLabel(iso: string, today: string): string | null {
  if (iso === today) return 'Сегодня'
  if (iso === addDays(today, -1)) return 'Вчера'
  if (iso === addDays(today, 1)) return 'Завтра'
  return null
}

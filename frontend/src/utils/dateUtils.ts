/**
 * Timezone-safe date math and formatting helpers for Calendar and Heatmap.
 * All arithmetic uses local Date components to avoid UTC serialization shifts.
 */

const MONTH_NAMES_NOMINATIVE = [
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
]

const MONTH_NAMES_GENITIVE = [
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

const DAY_NAMES = [
  'воскресенье',
  'понедельник',
  'вторник',
  'среда',
  'четверг',
  'пятница',
  'суббота',
]

export const SHORT_WEEKDAYS_MON_FIRST = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

export function parseIsoParts(iso: string): { year: number; month: number; day: number } {
  const [year = 1970, month = 1, day = 1] = iso.split('-').map(Number)
  return { year, month, day }
}

export function formatIsoDate(year: number, month: number, day: number): string {
  const mm = String(month).padStart(2, '0')
  const dd = String(day).padStart(2, '0')
  return `${year}-${mm}-${dd}`
}

export function isLeapYear(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0
}

export function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

/** Monday = 0, Tuesday = 1, ..., Sunday = 6 */
export function weekdayMondayFirst(year: number, month: number, day: number): number {
  const sundayZeroDay = new Date(year, month - 1, day).getDay()
  return (sundayZeroDay + 6) % 7
}

export function prevMonth(year: number, month: number): { year: number; month: number } {
  if (month === 1) return { year: year - 1, month: 12 }
  return { year, month: month - 1 }
}

export function nextMonth(year: number, month: number): { year: number; month: number } {
  if (month === 12) return { year: year + 1, month: 1 }
  return { year, month: month + 1 }
}

/**
 * Returns an array of ISO date strings (`YYYY-MM-DD`) covering the 7-column
 * Monday-first month grid (includes padding days from adjacent months).
 */
export function getMonthGridDays(year: number, month: number): string[] {
  const firstDayWeekday = weekdayMondayFirst(year, month, 1)
  const totalDays = daysInMonth(year, month)
  const totalCells = Math.ceil((firstDayWeekday + totalDays) / 7) * 7

  const days: string[] = []
  const startDate = new Date(year, month - 1, 1 - firstDayWeekday)

  for (let i = 0; i < totalCells; i++) {
    const current = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate() + i)
    days.push(formatIsoDate(current.getFullYear(), current.getMonth() + 1, current.getDate()))
  }

  return days
}

export function monthGridBounds(year: number, month: number): { start: string; end: string } {
  const days = getMonthGridDays(year, month)
  const fallbackStart = `${year}-${String(month).padStart(2, '0')}-01`
  const fallbackEnd = `${year}-${String(month).padStart(2, '0')}-28`
  return {
    start: days[0] ?? fallbackStart,
    end: days[days.length - 1] ?? fallbackEnd,
  }
}

export function yearBounds(year: number): { start: string; end: string } {
  return {
    start: `${year}-01-01`,
    end: `${year}-12-31`,
  }
}

/**
 * Returns weeks (each week is an array of 7 ISO date strings Mon..Sun)
 * covering the target year for heatmap contribution grid.
 */
export function getYearGridWeeks(year: number): string[][] {
  const jan1Weekday = weekdayMondayFirst(year, 1, 1)
  const startDate = new Date(year, 0, 1 - jan1Weekday)
  const dec31 = new Date(year, 11, 31)

  const weeks: string[][] = []
  let cursor = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate())

  while (cursor <= dec31 || weeks.length === 0 || cursor.getDay() !== 1) {
    const week: string[] = []
    for (let i = 0; i < 7; i++) {
      week.push(formatIsoDate(cursor.getFullYear(), cursor.getMonth() + 1, cursor.getDate()))
      cursor.setDate(cursor.getDate() + 1)
    }
    weeks.push(week)
  }

  return weeks
}

export function formatMonthTitle(year: number, month: number): string {
  return `${MONTH_NAMES_NOMINATIVE[month - 1]} ${year}`
}

export function formatFullDateLabel(iso: string): string {
  const { year, month, day } = parseIsoParts(iso)
  const d = new Date(year, month - 1, day)
  return `${day} ${MONTH_NAMES_GENITIVE[month - 1]} ${year}, ${DAY_NAMES[d.getDay()]}`
}

export function formatShortDateLabel(iso: string): string {
  const { year, month, day } = parseIsoParts(iso)
  const mm = String(month).padStart(2, '0')
  const dd = String(day).padStart(2, '0')
  return `${dd}.${mm}.${year}`
}

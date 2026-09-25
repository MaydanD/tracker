/** Shared Russian formatting utilities for UI components. */

export function formatStreakText(count: number, unit: 'days' | 'weeks'): string {
  const plural = new Intl.PluralRules('ru-RU').select(count)
  const labels = unit === 'days'
    ? { one: 'день', few: 'дня', many: 'дней', other: 'дней' }
    : { one: 'неделя', few: 'недели', many: 'недель', other: 'недель' }
  const word = labels[plural as keyof typeof labels] ?? labels.other
  return `🔥 ${count} ${word}`
}

export function formatMinutes(totalMinutes: number | null): string {
  if (totalMinutes === null || totalMinutes < 0) return 'Не указано'
  const hours = Math.floor(totalMinutes / 60)
  const mins = totalMinutes % 60
  if (hours === 0) return `${mins} мин`
  if (mins === 0) return `${hours} ч`
  return `${hours} ч ${mins} мин`
}

export function formatSleepStatus(status: 'underslept' | 'normal' | 'overslept' | null): string {
  switch (status) {
    case 'underslept': return 'Недосып'
    case 'normal': return 'Нормальный'
    case 'overslept': return 'Избыточный сон'
    default: return 'Не указано'
  }
}

export function formatPreferredWeekdays(weekdays: number[]): string {
  if (!weekdays || weekdays.length === 0) return ''
  const labels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
  return weekdays.map((d) => labels[d] ?? '').filter(Boolean).join(', ')
}

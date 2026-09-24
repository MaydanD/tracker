/**
 * Presentation vocabulary for daily entries.
 *
 * The words are product wording: «Нет отметки» is the absence of a record and is
 * deliberately distinct from «Пропущено», which is an explicit statement by the
 * user. The backend owns the rules; these labels only name them.
 */

import type { EntryStatus } from '../../api/types'

export interface StatusOption {
  value: EntryStatus
  label: string
}

/** Offered on a past or current day, in the order they are shown. */
export const DAILY_STATUS_OPTIONS: StatusOption[] = [
  { value: 'done', label: 'Выполнено' },
  { value: 'missed', label: 'Пропущено' },
  { value: 'skipped', label: 'Осознанный пропуск' },
]

/** The same action on a future day, where only a planned skip is possible. */
export const PLANNED_SKIP_LABEL = 'Запланировать пропуск'

/** The absence of a record. Never rendered as «Пропущено». */
export const NO_ENTRY_LABEL = 'Нет отметки'

export function statusLabel(status: EntryStatus): string {
  return DAILY_STATUS_OPTIONS.find((option) => option.value === status)?.label ?? status
}

/** Button label for a status, adjusted for the rules of a future day. */
export function statusActionLabel(status: EntryStatus, isFuture: boolean): string {
  if (isFuture && status === 'skipped') return PLANNED_SKIP_LABEL
  return statusLabel(status)
}

import { useState, type FormEvent } from 'react'

import { describeApiError } from '../../api/client'
import { deleteDailyEntry, saveDailyEntry } from '../../api/daily'
import type { DailyEntry, DailyEntryInput, DayItem, EntryStatus } from '../../api/types'
import { ErrorBanner } from '../Feedback'
import { scheduleLabel, unitLabel, weightLabel } from '../habits/options'
import { DAILY_STATUS_OPTIONS, NO_ENTRY_LABEL, statusActionLabel, statusLabel } from './status'

/** Local draft of the row. `status === null` means the day has no record. */
interface Draft {
  status: EntryStatus | null
  quantity: string
  skipReason: string
  note: string
}

export interface DayHabitRowProps {
  item: DayItem
  entryDate: string
  /** A date that has not happened yet: only a planned skip is offered. */
  isFuture: boolean
  onChanged: () => void
}

function draftFrom(entry: DailyEntry | null): Draft {
  return {
    status: entry?.status ?? null,
    quantity: entry?.quantity_value === null || entry?.quantity_value === undefined
      ? ''
      : String(entry.quantity_value),
    skipReason: entry?.skip_reason ?? '',
    note: entry?.note ?? '',
  }
}

/** Stable identity of the stored record, used to reset the draft when it changes. */
export function entryKey(habitId: number, entry: DailyEntry | null): string {
  if (entry === null) return `${habitId}:none`
  return `${habitId}:${entry.status}|${entry.quantity_value}|${entry.skip_reason}|${entry.note}`
}

function quantityText(value: number | null, unit: string | null): string | null {
  if (value === null) return null
  return `${value}${unit === null ? '' : ` ${unit}`}`
}

/**
 * The recorded state of a habit — the one line the user reads.
 *
 * «Нет отметки» and «Пропущено» are different words, different styles and
 * different states: one says nothing has been recorded, the other says the user
 * explicitly marked the habit as not done.
 */
function EntrySummary({ item }: { item: DayItem }) {
  const entry = item.entry

  if (entry === null) {
    return (
      <span className="state state--none" role="status">
        {NO_ENTRY_LABEL}
        <span className="state__hint">Привычка ещё не отмечена за этот день</span>
      </span>
    )
  }

  const quantity = quantityText(entry.quantity_value, entry.quantity_unit)

  return (
    <span className={`state state--${entry.status}`} role="status">
      {statusLabel(entry.status)}
      {entry.status === 'skipped' && entry.skip_reason !== null ? (
        <span className="state__reason">Причина: {entry.skip_reason}</span>
      ) : null}
      {quantity !== null ? <span className="state__extra">{quantity}</span> : null}
      {entry.note !== null ? <span className="state__note">{entry.note}</span> : null}
    </span>
  )
}

/**
 * One habit on one date: what is recorded, and the editor for changing it.
 *
 * The whole record is saved at once, so leaving a field empty clears it. Nothing
 * here decides the rules — the backend rejects a future `done`/`missed`, a skip
 * without a reason, a reason on a non-skip, and a quantity a habit does not
 * track; the screen simply avoids offering actions that would be refused.
 */
export function DayHabitRow({
  item,
  entryDate,
  isFuture,
  onChanged,
}: DayHabitRowProps) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(item.entry))
  const [problems, setProblems] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const tracksQuantity = item.tracking_mode === 'binary_quantity'
  const quantityId = `quantity-${item.habit_id}`
  const reasonId = `skip-reason-${item.habit_id}`
  const noteId = `note-${item.habit_id}`

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setProblems([])
    setDraft((current) => ({ ...current, [key]: value }))
  }

  function chooseStatus(status: EntryStatus) {
    setProblems([])
    setDraft((current) => ({
      ...current,
      status,
      // A skip reason only belongs to a skipped entry, so it never lingers.
      skipReason: status === 'skipped' ? current.skipReason : '',
    }))
  }

  /**
   * The same rules the backend enforces, checked before the round-trip so the
   * user gets an immediate, local answer. The server stays the authority: its
   * rejections are still shown.
   */
  function validate(current: Draft): string[] {
    const found: string[] = []

    if (current.status === 'skipped' && current.skipReason.trim() === '') {
      found.push('Укажите причину пропуска.')
    }

    if (tracksQuantity && current.quantity.trim() !== '') {
      const value = Number(current.quantity.replace(',', '.'))
      if (Number.isNaN(value)) {
        found.push('Введите число в поле «Количество».')
      } else if (value < 0) {
        found.push('Количество не может быть отрицательным.')
      } else if (!item.quantity_allows_decimal && !Number.isInteger(value)) {
        found.push('Для этой привычки допустимы только целые значения.')
      }
    }

    return found
  }

  function buildInput(current: Draft): DailyEntryInput {
    const quantity =
      tracksQuantity && current.quantity.trim() !== ''
        ? Number(current.quantity.replace(',', '.'))
        : null

    return {
      status: current.status as EntryStatus,
      quantity_value: quantity,
      skip_reason: current.status === 'skipped' ? current.skipReason.trim() : null,
      note: current.note.trim() === '' ? null : current.note.trim(),
    }
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (draft.status === null) return

    const found = validate(draft)
    setProblems(found)
    setError(null)
    if (found.length > 0) return

    setBusy(true)
    try {
      await saveDailyEntry(item.habit_id, entryDate, buildInput(draft))
      onChanged()
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function handleClear() {
    setBusy(true)
    setError(null)
    setProblems([])
    try {
      await deleteDailyEntry(item.habit_id, entryDate)
      onChanged()
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className={`day-row${item.is_archived ? ' day-row--archived' : ''}`}>
      <div className="day-row__head">
        <span className="day-row__name">
          <span
            className="swatch swatch--small"
            style={{ backgroundColor: item.area.color }}
            aria-hidden="true"
          />
          {item.name}
          {item.is_archived ? <span className="badge badge--muted">В архиве</span> : null}
        </span>
        <EntrySummary item={item} />
      </div>

      <div className="day-row__meta">
        <span className="pill">{item.area.name}</span>
        <span className="pill">Важность {item.weight} · {weightLabel(item.weight)}</span>
        <span className="pill">{scheduleLabel(item.schedule)}</span>
        {tracksQuantity ? (
          <span className="pill">
            Количество{item.quantity_unit === null ? '' : unitLabel(item.quantity_unit)}
            {item.quantity_allows_decimal ? ' · дробное' : ' · целое'}
          </span>
        ) : null}
      </div>

      <form className="day-row__editor" onSubmit={handleSave} noValidate>
        <div className="choice-group choice-group--row" role="group" aria-label="Состояние">
          {DAILY_STATUS_OPTIONS.map((option) => {
            const blocked = isFuture && option.value !== 'skipped'
            return (
              <button
                key={option.value}
                type="button"
                className={`button button--small${
                  draft.status === option.value ? ' button--selected' : ''
                }`}
                aria-pressed={draft.status === option.value}
                disabled={busy || blocked}
                title={blocked ? 'Для будущей даты доступен только запланированный пропуск' : undefined}
                onClick={() => chooseStatus(option.value)}
              >
                {statusActionLabel(option.value, isFuture)}
              </button>
            )
          })}
        </div>

        {draft.status !== null ? (
          <>
            {tracksQuantity ? (
              <div className="field">
                <label className="field__label" htmlFor={quantityId}>
                  Количество
                </label>
                <input
                  id={quantityId}
                  className="field__input field__input--narrow"
                  type="number"
                  min={0}
                  step={item.quantity_allows_decimal ? 'any' : '1'}
                  value={draft.quantity}
                  onChange={(event) => update('quantity', event.target.value)}
                  disabled={busy}
                />
                <span className="field__hint">
                  {item.quantity_unit === null
                    ? 'Необязательно.'
                    : `Необязательно. Единица измерения на эту дату: ${item.quantity_unit}.`}
                </span>
              </div>
            ) : null}

            {draft.status === 'skipped' ? (
              <div className="field">
                <label className="field__label" htmlFor={reasonId}>
                  Причина пропуска
                </label>
                <input
                  id={reasonId}
                  className="field__input"
                  maxLength={200}
                  placeholder="поездка, болезнь, отпуск…"
                  value={draft.skipReason}
                  onChange={(event) => update('skipReason', event.target.value)}
                  disabled={busy}
                />
              </div>
            ) : null}

            <div className="field">
              <label className="field__label" htmlFor={noteId}>
                Заметка (необязательно)
              </label>
              <input
                id={noteId}
                className="field__input"
                maxLength={500}
                value={draft.note}
                onChange={(event) => update('note', event.target.value)}
                disabled={busy}
              />
            </div>

            {problems.length > 0 ? (
              <ul className="banner banner--error" role="alert">
                {problems.map((problem) => (
                  <li key={problem}>{problem}</li>
                ))}
              </ul>
            ) : null}

            <ErrorBanner message={error} />

            <div className="card__actions">
              <button type="submit" className="button button--primary button--small" disabled={busy}>
                {busy ? 'Сохранение…' : 'Сохранить'}
              </button>
              {item.entry !== null ? (
                <button
                  type="button"
                  className="button button--small"
                  onClick={handleClear}
                  disabled={busy}
                >
                  Очистить
                </button>
              ) : null}
            </div>
          </>
        ) : (
          <>
            <ErrorBanner message={error} />
            <span className="field__hint">
              Выберите состояние, чтобы отметить привычку за этот день.
            </span>
          </>
        )}
      </form>
    </li>
  )
}

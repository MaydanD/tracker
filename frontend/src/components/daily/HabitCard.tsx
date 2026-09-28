import { useEffect, useRef, useState } from 'react'

import { describeApiError } from '../../api/client'
import { deleteDailyEntry, saveDailyEntry } from '../../api/daily'
import type { DailyEntry, DailyEntryInput, DayItem, EntryStatus } from '../../api/types'
import { useCardReadiness } from '../../hooks/useCardReadiness'
import { OkButton } from './OkButton'
import { importanceLabel, scheduleLabel } from '../habits/options'
import { DIRECTION_LABEL } from './direction'
import { DAILY_STATUS_OPTIONS, statusActionLabel, statusLabel } from './status'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface HabitCardProps {
  item: DayItem
  entryDate: string
  isFuture: boolean
  /** Called after any successful save or delete so the parent can react. */
  onSettled: (habitId: number, entry: DailyEntry | null) => void
  /** Called when the 5-second OK timer reaches 'done' (not fired in completed section). */
  onTimerDone?: (habitId: number) => void
  /** When true the card lives inside the "already recorded" section. */
  inCompletedSection?: boolean
}

/**
 * Local draft. `status === null` → no entry yet; `value === null` → no answer yet
 * (a chosen `0` is an answer, not an empty one).
 */
interface Draft {
  status: EntryStatus | null
  value: number | null
  quantity: string
  skipReason: string
  note: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function draftFrom(entry: DailyEntry | null): Draft {
  return {
    status: entry?.status ?? null,
    value: entry?.value ?? null,
    quantity:
      entry?.quantity_value == null ? '' : String(entry.quantity_value),
    skipReason: entry?.skip_reason ?? '',
    note: entry?.note ?? '',
  }
}

/**
 * The answer a habit of this kind can be saved with, or `null` when the draft is
 * not complete yet.
 *
 * A value-tracked habit is answered in one way only — a value on its own scale,
 * recorded as a completed day — so it never carries a quantity or a skip reason.
 */
function buildInput(
  draft: Draft,
  tracksQuantity: boolean,
  allowsDecimal: boolean,
  tracksValue: boolean,
): DailyEntryInput | null {
  const note = draft.note.trim() || null

  if (tracksValue) {
    if (draft.value === null) return null
    return { status: 'done', value: draft.value, note }
  }

  if (draft.status === null) return null
  const rawQty = draft.quantity.trim().replace(',', '.')
  const quantity =
    tracksQuantity && rawQty !== ''
      ? Number(rawQty)
      : null

  if (quantity !== null && (Number.isNaN(quantity) || quantity < 0)) return null
  if (!allowsDecimal && quantity !== null && !Number.isInteger(quantity)) return null

  return {
    status: draft.status,
    value: null,
    quantity_value: quantity,
    skip_reason: draft.status === 'skipped' ? draft.skipReason.trim() || null : null,
    note,
  }
}

/** The words of a value scale, defaulting to the position when none are stored. */
function valueLabels(item: DayItem): string[] {
  const max = item.value_type === 'binary' ? 1 : 3
  const stored = item.value_labels ?? []
  return Array.from({ length: max + 1 }, (_, value) => stored[value] ?? String(value))
}

/** Every value of a scale, in order: `0..1` for binary, `0..3` for ordinal_4. */
function valueOptions(item: DayItem): number[] {
  const max = item.value_type === 'binary' ? 1 : 3
  return Array.from({ length: max + 1 }, (_, value) => value)
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Compact colour-coded status pill: the answer, or «Нет отметки». */
function StatusPill({ entry, item }: { entry: DailyEntry | null; item: DayItem }) {
  if (entry === null) {
    return (
      <span className="ccard__pill ccard__pill--none" role="status" aria-label="Нет отметки">
        Нет отметки
      </span>
    )
  }
  if (item.value_type !== null) {
    // The label of the chosen position — a recorded 0 shows as its own word,
    // never as an empty card.
    return (
      <span role="status" className="ccard__pill ccard__pill--done">
        {valueLabels(item)[entry.value ?? 0]}
      </span>
    )
  }
  return (
    <span role="status" className={`ccard__pill ccard__pill--${entry.status}`}>
      {statusLabel(entry.status)}
      {entry.quantity_value !== null
        ? ` · ${entry.quantity_value}${entry.quantity_unit ? ` ${entry.quantity_unit}` : ''}`
        : null}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * A compact check-in card for one habit on one date.
 *
 * Autosaves on every status-button click (or when a required extra field
 * becomes valid). The OK button + progress fill gives the user 5 seconds to
 * reconsider before the card moves to "already recorded".
 *
 * Re-interaction (changing value) while the countdown runs resets the timer.
 */
export function HabitCard(props: HabitCardProps) {
  return <HabitCardEditor key={`${props.entryDate}:${props.item.habit_id}`} {...props} />
}
function HabitCardEditor({
  item,
  entryDate,
  isFuture,
  onSettled,
  onTimerDone,
  inCompletedSection = false,
}: HabitCardProps) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(item.entry))
  const [savedEntry, setSavedEntry] = useState<DailyEntry | null>(item.entry)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const tracksQuantity = item.tracking_mode === 'binary_quantity'
  const tracksValue = item.value_type !== null
  const mounted = useRef(true)
  const generation = useRef(0)
  const queue = useRef(Promise.resolve())
  const [revision, setRevision] = useState(0)
  const [savedRevision, setSavedRevision] = useState(0)
  const readiness = useCardReadiness({ revision, savedRevision,
    stored: savedEntry !== null,
    // A value habit is filled by its *value*: a `0` is an answer, and a row
    // without one (a completion recorded before the habit became a scale) is
    // not, so «ОК» is never offered for a card that still needs answering.
    filled: savedEntry !== null && (!tracksValue || savedEntry.value !== null),
    error, completed: inCompletedSection,
    onDone: () => onTimerDone?.(item.habit_id) })
  const { timerState, progress, confirmNow, reset } = readiness

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  function beginChange() {
    const version = ++generation.current
    setRevision(version)
    reset()
    setError(null)
    return version
  }
  function save(newDraft: Draft) {
    const version = beginChange()
    const input = buildInput(
      newDraft,
      tracksQuantity,
      item.quantity_allows_decimal,
      tracksValue,
    )
    if (input === null || (newDraft.status === 'skipped' && !input.skip_reason)) {
      setBusy(false)
      if (
        input === null &&
        !tracksValue &&
        newDraft.status !== null
      ) {
        setError(item.quantity_allows_decimal
          ? 'Укажите неотрицательное число.' : 'Для этой привычки допустимы только целые значения.')
      }
      return
    }
    setBusy(true)
    // Serialize writes so the backend also ends with the newest value. Stale
    // responses cannot mark a newer draft saved or start its countdown.
    queue.current = queue.current.then(async () => {
      if (generation.current !== version) return
      try {
        const entry = await saveDailyEntry(item.habit_id, entryDate, input)
        if (!mounted.current || generation.current !== version) return
        setSavedEntry(entry)
        setSavedRevision(version)
        onSettled(item.habit_id, entry)
      } catch (cause) {
        if (mounted.current && generation.current === version) setError(describeApiError(cause))
      } finally {
        if (mounted.current && generation.current === version) setBusy(false)
      }
    })
  }
  function handleClear() {
    const version = beginChange()
    setBusy(true)
    queue.current = queue.current.then(async () => {
      if (generation.current !== version) return
      try {
        await deleteDailyEntry(item.habit_id, entryDate)
        if (!mounted.current || generation.current !== version) return
        setDraft(draftFrom(null))
        setSavedEntry(null)
        setSavedRevision(version)
        onSettled(item.habit_id, null)
      } catch (cause) {
        if (mounted.current && generation.current === version) setError(describeApiError(cause))
      } finally {
        if (mounted.current && generation.current === version) setBusy(false)
      }
    })
  }

  // -------------------------------------------------------------------------
  // Draft changes → autosave
  // -------------------------------------------------------------------------

  function chooseStatus(status: EntryStatus) {
    const next: Draft = {
      ...draft,
      status,
      skipReason: status === 'skipped' ? draft.skipReason : '',
    }
    setDraft(next)
    setError(null)
    // Re-interaction resets the countdown so it starts fresh after save.
    reset()
    void save(next)
  }

  /** A value habit is answered by choosing a position on its own scale. */
  function chooseValue(value: number) {
    const next: Draft = { ...draft, status: 'done', value }
    setDraft(next)
    setError(null)
    reset()
    void save(next)
  }

  function updateExtra<K extends keyof Draft>(key: K, value: Draft[K]) {
    const next = { ...draft, [key]: value }
    setDraft(next)
    setError(null)
    reset()
    void save(next)
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  // In the active section: offer «ОК» as soon as the value is stored. Whether
  // the auto-countdown is already running is a separate question — interaction
  // with a field pauses it but never removes the button.
  const showOk = readiness.showOk

  const quantityId = `qty-${item.habit_id}`
  const reasonId = `reason-${item.habit_id}`
  const noteId = `note-${item.habit_id}`
  const labels = valueLabels(item)
  const answer = savedEntry === null ? null : draft.value ?? savedEntry.value

  return (
    <div
      role="group"
      aria-label={
        tracksValue && item.direction !== null
          ? `${item.name}. Направление: ${DIRECTION_LABEL[item.direction]}`
          : item.name
      }
      {...readiness.focusProps}
      className={[
        'ccard',
        timerState === 'counting' ? 'ccard--counting' : '',
        timerState !== 'idle' && !inCompletedSection ? 'ccard--filled' : '',
        item.is_archived ? 'ccard--archived' : '',
        busy ? 'ccard--busy' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      data-habit-id={item.habit_id}
    >
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="ccard__head">
        {/*
         * The tooltip carries the whole configuration the day was answered
         * with: the schedule, the importance the user set, and — for a value
         * habit — which end of the scale is good. All three are metadata about
         * the habit, never a verdict on a single answer.
         */}
        <span
          className="ccard__name"
          title={[
            scheduleLabel(item.schedule),
            `Важность: ${importanceLabel(item.importance)}`,
            item.direction === null ? null : DIRECTION_LABEL[item.direction],
          ]
            .filter(Boolean)
            .join(' · ')}
        >
          <span
            className="swatch swatch--small"
            style={{ backgroundColor: item.area.color }}
            aria-hidden="true"
          />
          <span className="ccard__name-text" title={scheduleLabel(item.schedule)}>{item.name}</span>
          {item.importance !== 'normal' ? (
            <span className="badge badge--muted" title={`Важность: ${importanceLabel(item.importance)}`}>
              {item.importance === 'high' ? 'высокая' : 'низкая'}
            </span>
          ) : null}
          {item.is_archived ? (
            <span className="badge badge--muted">архив</span>
          ) : null}
        </span>
        <StatusPill entry={savedEntry} item={item} />
        {/*
         * The clear control belongs to the recorded state, so it sits with the
         * status pill instead of the status buttons. The button row is exactly
         * as wide as its three options, and one more button there pushed the
         * row onto a second line — a visible jump the moment a habit was marked.
         */}
        {savedEntry !== null ? (
          <button
            type="button"
            className="ccard__clear-btn"
            onClick={handleClear}
            aria-label="Убрать отметку"
          >
            ✕
          </button>
        ) : null}
      </div>

      {/*
       * ── The answer ───────────────────────────────────────
       *
       * A habit answered on a value scale (да/нет, 0…3) shows exactly the words
       * the user configured. It is never asked for a completion or a skip: its
       * question is "how much", not "did it happen".
       */}
      {tracksValue ? (
        <div className="ccard__segments" role="group" aria-label="Значение">
          {valueOptions(item).map((value) => {
            const selected = answer === value
            return (
              <button
                key={value}
                type="button"
                className={`ccard__seg-btn${selected ? ' ccard__seg-btn--active' : ''}`}
                aria-pressed={selected}
                disabled={isFuture}
                title={
                  isFuture ? 'Будущий день нельзя отметить заранее' : labels[value]
                }
                onClick={() => chooseValue(value)}
              >
                {labels[value]}
              </button>
            )
          })}
        </div>
      ) : null}

      {/* ── Status buttons (completion habits only) ────────── */}
      {tracksValue ? null : (
        <div className="ccard__actions" role="group" aria-label="Отметка привычки">
          {DAILY_STATUS_OPTIONS.map((option) => {
            const blocked = isFuture && option.value !== 'skipped'
            const isSelected = draft.status === option.value
            return (
              <button
                key={option.value}
                type="button"
                className={`ccard__status-btn${isSelected ? ' ccard__status-btn--active' : ''}`}
                aria-pressed={isSelected}
                aria-label={statusActionLabel(option.value, isFuture)}
                disabled={blocked}
                title={
                  blocked
                    ? 'Для будущей даты доступен только запланированный пропуск'
                    : statusActionLabel(option.value, isFuture)
                }
                onClick={() => chooseStatus(option.value)}
              >
                {option.value === 'skipped' ? 'Пропуск' : statusActionLabel(option.value, isFuture)}
              </button>
            )
          })}
        </div>
      )}

      {/*
       * Quantity stays in its own row, but a habit that tracks a quantity
       * always shows this row — even before it is marked. Rendering it only
       * after a status was chosen used to add a whole row the moment the user
       * marked the habit, which shoved every card below it downwards.
       */}
      {tracksQuantity && !tracksValue ? (
        <div className="ccard__extra">
          <input
            id={quantityId}
            aria-label="Количество"
            className="ccard__input ccard__input--narrow"
            type="number"
            min={0}
            step={item.quantity_allows_decimal ? 'any' : '1'}
            placeholder={item.quantity_unit ?? 'Количество'}
            value={draft.quantity}
            disabled={draft.status === null || draft.status === 'skipped'}
            onChange={(e) => updateExtra('quantity', e.target.value)}
          />
        </div>
      ) : null}

      {/* ── Error ──────────────────────────────────────────── */}
      {error !== null ? (
        <p className="ccard__error" role="alert">
          {error}
        </p>
      ) : null}

      {/*
       * Footer: the note field plus the OK countdown, in one row that is
       * always rendered. The note simply gives up width to the OK button
       * instead of the card growing a new row. The skip-reason field joins
       * this row too, so revealing it cannot change the card's height either.
       */}
      <div className="ccard__footer">
        {!tracksValue && draft.status === 'skipped' ? (
          <input
            id={reasonId}
            aria-label="Причина пропуска"
            className="ccard__input ccard__input--note"
            placeholder="Причина пропуска"
            maxLength={200}
            value={draft.skipReason}
            onChange={(e) => updateExtra('skipReason', e.target.value)}
          />
        ) : null}
        <input
          id={noteId}
          aria-label="Заметка (необязательно)"
          className="ccard__input ccard__input--note"
          placeholder="Заметка (необязательно)"
          maxLength={500}
          value={draft.note}
          disabled={tracksValue ? draft.value === null : draft.status === null}
          onChange={(e) => updateExtra('note', e.target.value)}
        />
        {showOk ? (
          <OkButton
            inline
            progress={progress}
            counting={timerState === 'counting'}
            onConfirm={confirmNow}
            disabled={!readiness.canConfirm}
            locked={readiness.locked}
            onToggleLock={readiness.toggleLock}
          />
        ) : null}
      </div>
    </div>
  )
}

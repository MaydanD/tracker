import { useEffect, useRef, useState } from 'react'

import { describeApiError } from '../../api/client'
import { deleteDailyEntry, saveDailyEntry } from '../../api/daily'
import type { DailyEntry, DailyEntryInput, DayItem, EntryStatus } from '../../api/types'
import { useCardReadiness } from '../../hooks/useCardReadiness'
import { OkButton } from './OkButton'
import { scheduleLabel } from '../habits/options'
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

/** Local draft. `status === null` → no entry yet. */
interface Draft {
  status: EntryStatus | null
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
    quantity:
      entry?.quantity_value == null ? '' : String(entry.quantity_value),
    skipReason: entry?.skip_reason ?? '',
    note: entry?.note ?? '',
  }
}

function buildInput(
  draft: Draft,
  tracksQuantity: boolean,
  allowsDecimal: boolean,
): DailyEntryInput | null {
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
    quantity_value: quantity,
    skip_reason: draft.status === 'skipped' ? draft.skipReason.trim() || null : null,
    note: draft.note.trim() || null,
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Compact colour-coded status pill. */
function StatusPill({ entry }: { entry: DailyEntry | null }) {
  if (entry === null) {
    return (
      <span className="ccard__pill ccard__pill--none" role="status" aria-label="Нет отметки">
        Нет отметки
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
  const mounted = useRef(true)
  const generation = useRef(0)
  const queue = useRef(Promise.resolve())
  const [revision, setRevision] = useState(0)
  const [savedRevision, setSavedRevision] = useState(0)
  const readiness = useCardReadiness({ revision, savedRevision,
    filled: savedEntry !== null, error, completed: inCompletedSection,
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
    const input = buildInput(newDraft, tracksQuantity, item.quantity_allows_decimal)
    if (input === null || (newDraft.status === 'skipped' && !input.skip_reason)) {
      setBusy(false)
      if (input === null && newDraft.status !== null) setError(item.quantity_allows_decimal
        ? 'Укажите неотрицательное число.' : 'Для этой привычки допустимы только целые значения.')
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

  const isIdle = timerState === 'idle'

  // In the active section: show a "settled" look while counting down.
  const showCountdown = readiness.showActions

  const quantityId = `qty-${item.habit_id}`
  const reasonId = `reason-${item.habit_id}`
  const noteId = `note-${item.habit_id}`

  return (
    <div
      role="group" aria-label={item.name}
      {...readiness.focusProps}
      className={[
        'ccard',
        showCountdown ? 'ccard--counting' : '',
        !isIdle && !inCompletedSection ? 'ccard--filled' : '',
        item.is_archived ? 'ccard--archived' : '',
        busy ? 'ccard--busy' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      data-habit-id={item.habit_id}
    >
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="ccard__head">
        <span className="ccard__name" title={scheduleLabel(item.schedule)}>
          <span
            className="swatch swatch--small"
            style={{ backgroundColor: item.area.color }}
            aria-hidden="true"
          />
          {item.name}
          {item.is_archived ? (
            <span className="badge badge--muted">архив</span>
          ) : null}
        </span>
        <StatusPill entry={savedEntry} />
      </div>

      {/* ── Status buttons ─────────────────────────────────── */}
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
              disabled={blocked}
              title={
                blocked
                  ? 'Для будущей даты доступен только запланированный пропуск'
                  : undefined
              }
              onClick={() => chooseStatus(option.value)}
            >
              {statusActionLabel(option.value, isFuture)}
            </button>
          )
        })}

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

      {/* ── Extra fields ───────────────────────────────────── */}
      {draft.status === 'skipped' ? (
        <div className="ccard__extra">
          <input
            id={reasonId}
            aria-label="Причина пропуска"
            className="ccard__input"
            placeholder="Причина пропуска"
            maxLength={200}
            value={draft.skipReason}
            onChange={(e) => updateExtra('skipReason', e.target.value)}
          />
        </div>
      ) : null}

      {tracksQuantity && draft.status !== null && draft.status !== 'skipped' ? (
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
            onChange={(e) => updateExtra('quantity', e.target.value)}
          />
        </div>
      ) : null}

      {draft.status !== null ? (
        <div className="ccard__extra">
          <input
            id={noteId}
            aria-label="Заметка (необязательно)"
            className="ccard__input"
            placeholder="Заметка (необязательно)"
            maxLength={500}
            value={draft.note}
            onChange={(e) => updateExtra('note', e.target.value)}
          />
        </div>
      ) : null}

      {/* ── Error ──────────────────────────────────────────── */}
      {error !== null ? (
        <p className="ccard__error" role="alert">
          {error}
        </p>
      ) : null}

      {/* ── OK button (countdown) ──────────────────────────── */}
      {showCountdown ? (
        <OkButton
          progress={progress}
          onConfirm={confirmNow}
          locked={readiness.locked}
          onToggleLock={readiness.toggleLock}
        />
      ) : null}
    </div>
  )
}

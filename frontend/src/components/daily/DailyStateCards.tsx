/**
 * Daily-state fields as individual check-in cards.
 *
 * Architecture:
 *   - The shared store owns the single `DailyStateInput` draft and the one
 *     in-flight PUT.  Each card reads the slice it cares about and calls
 *     `patch(patch)` when the user picks a value.
 *   - The PUT replaces the entire record, so all fields are always sent.
 *     Writes are serialized and versioned per card; newer drafts survive responses.
 *   - Each card has its own `useCardTimer` instance for the OK countdown.
 *   - "Filled" means the field's value is non-null (and non-empty for strings).
 *   - Cards can live in the active section or the completed section; the parent
 *     `CheckInGrid` decides which bucket each card belongs to.
 *
 * Configurable Daily State note:
 *   The backend model stores a fixed set of fields (mood, energy, wellbeing,
 *   sleep_status, sleep_minutes, alcohol, gaming, computer_overuse, note +
 *   their detail/duration companions). There is no per-user field registry.
 *   Until a configurable-field model and migration are added to the backend,
 *   the set of cards is hardcoded here, matching `DailyStateInput` exactly.
 */

import { createContext, useContext, useEffect, useRef, useState, useSyncExternalStore } from 'react'

import { describeApiError } from '../../api/client'
import {
  deleteDailyState,
  emptyDailyState,
  fetchDailyState,
  saveDailyState,
  type DailyStateInput,
  type DailyStateResponse,
} from '../../api/dailyState'
import { useAsyncData } from '../../hooks/useAsyncData'
import { useCardReadiness } from '../../hooks/useCardReadiness'
import { LoadingText, ErrorBanner } from '../Feedback'
import { OkButton } from './OkButton'

// ---------------------------------------------------------------------------
// Card descriptor — drives the CheckInGrid's ordering and bucket assignment
// ---------------------------------------------------------------------------

/** Identifies a daily-state card for the grid. */
export type DailyStateCardId =
  | 'mood'
  | 'energy'
  | 'wellbeing'
  | 'sleep'
  | 'alcohol'
  | 'gaming'
  | 'computer'
  | 'ds-note'

export const DAILY_STATE_CARD_IDS: DailyStateCardId[] = [
  'mood',
  'energy',
  'wellbeing',
  'sleep',
  'alcohol',
  'gaming',
  'computer',
  'ds-note',
]

export const DAILY_STATE_CARD_LABELS: Record<DailyStateCardId, string> = {
  mood: 'Настроение',
  energy: 'Энергия',
  wellbeing: 'Самочувствие',
  sleep: 'Сон',
  alcohol: 'Алкоголь',
  gaming: 'Игры',
  computer: 'За компьютером',
  'ds-note': 'Заметка дня',
}

/** Returns true if the slice of state that card represents has been filled. */
export function isDailyStateCardFilled(
  id: DailyStateCardId,
  state: DailyStateInput,
): boolean {
  switch (id) {
    case 'mood':      return state.mood !== null
    case 'energy':    return state.energy !== null
    case 'wellbeing': return state.wellbeing !== null
    case 'sleep':     return state.sleep_status !== null || state.sleep_minutes !== null
    case 'alcohol':   return state.alcohol !== null
    case 'gaming':    return state.gaming !== null
    case 'computer':  return state.computer_overuse !== null || state.computer_minutes !== null
    case 'ds-note':   return (state.note ?? '').trim() !== ''
  }
}

// ---------------------------------------------------------------------------
// Shared store — one draft + one save loop, shared across all cards on a date
// ---------------------------------------------------------------------------

type Listener = () => void
interface CardSave { revision: number; savedRevision: number; error: string | null }
interface DailyStateStore {
  draft: DailyStateInput
  cards: Record<DailyStateCardId, CardSave>
  patch: (patch: Partial<DailyStateInput>) => void
  clearField: (cardId: DailyStateCardId) => void
  complete: (cardId: DailyStateCardId) => void
}

// The API replaces the whole record: serialize writes, retaining edits made
// during an in-flight request. Only revisions included in that write settle.
function createStore(initial: DailyStateResponse,
  onSettled: (id: DailyStateCardId, filled: boolean) => void,
  complete: (id: DailyStateCardId) => void,
) {
  let draft = toInput(initial.state)
  let cards = Object.fromEntries(DAILY_STATE_CARD_IDS.map(id =>
    [id, { revision: 0, savedRevision: 0, error: null }])) as Record<DailyStateCardId, CardSave>
  let active = true
  let running = false
  let queued = false
  const listeners = new Set<Listener>()
  const clearField = (id: DailyStateCardId) => change(id, clearCardFields(id, draft))
  let snapshot: DailyStateStore = { draft, cards, patch, clearField, complete }
  const notify = () => {
    snapshot = { draft, cards, patch, clearField, complete }
    listeners.forEach(fn => fn())
  }
  async function flush() {
    if (running) return
    running = true
    // Already accepted edits still drain to their original date on navigation.
    // Disposal disconnects UI notifications, not the user's queued writes.
    while (queued) {
      queued = false
      const sent = draft
      const versions = cards
      const changed = DAILY_STATE_CARD_IDS.filter(id => versions[id].revision !== versions[id].savedRevision)
      try {
        if (Object.values(sent).every(v => v === null || (typeof v === 'string' && v.trim() === ''))) await deleteDailyState(initial.state_date)
        else await saveDailyState(initial.state_date, sent)
        if (!active) continue
        for (const id of changed) {
          if (cards[id].revision !== versions[id].revision) continue
          cards = { ...cards, [id]: { ...cards[id], savedRevision: versions[id].revision, error: null } }
          onSettled(id, isDailyStateCardFilled(id, sent))
        }
      } catch (cause) {
        if (!active) continue
        for (const id of changed) {
          if (cards[id].revision !== versions[id].revision) continue
          cards = { ...cards, [id]: { ...cards[id], error: describeApiError(cause) } }
        }
      }
      if (active) notify()
    }
    running = false
  }
  function change(id: DailyStateCardId, next: DailyStateInput) {
    draft = next
    cards = { ...cards, [id]: { ...cards[id], revision: cards[id].revision + 1, error: null } }
    queued = true
    notify()
    void flush()
  }
  function patch(patch: Partial<DailyStateInput>) {
    // Detail values cannot survive clearing their controlling answer.
    if ('alcohol' in patch && patch.alcohol !== true) patch = { ...patch, alcohol_detail: null }
    if ('gaming' in patch && patch.gaming !== true) patch = { ...patch, gaming_minutes: null }
    change(detectCard(patch), { ...draft, ...patch })
  }
  return {
    initial: toInput(initial.state),
    getSnapshot: () => snapshot,
    subscribe(fn: Listener) { listeners.add(fn); return () => { listeners.delete(fn) } },
    activate() { active = true },
    dispose() { active = false },
  }
}

type StoreType = ReturnType<typeof createStore>
const DailyStateContext = createContext<StoreType | null>(null)
function useStore(): StoreType {
  const store = useContext(DailyStateContext)
  if (!store) throw new Error('DailyStateCard must be inside DailyStateProvider')
  return store
}
export function useInitialDailyState() { return useStore().initial }
function useStoreSnapshot(): DailyStateStore {
  const store = useStore()
  return useSyncExternalStore(store.subscribe, store.getSnapshot)
}
export interface DailyStateProviderProps {
  date: string
  onSettled: (cardId: DailyStateCardId, filled: boolean) => void
  onCompleted: (cardId: DailyStateCardId) => void
  children: React.ReactNode
}
export function DailyStateProvider(props: DailyStateProviderProps) {
  return <DailyStateResource key={props.date} {...props} />
}
function DailyStateResource(props: DailyStateProviderProps) {
  const { data, error, reload } = useAsyncData(signal => fetchDailyState(props.date, signal), [props.date])
  if (error) return <><ErrorBanner message={error} /><button className="button" onClick={reload}>Повторить загрузку состояния</button></>
  if (!data) return <LoadingText>Загрузка состояния дня…</LoadingText>
  return <LoadedDailyState {...props} initial={data} />
}
function LoadedDailyState({ initial, onSettled, onCompleted, children }: DailyStateProviderProps & { initial: DailyStateResponse }) {
  const callbacks = useRef({ onSettled, onCompleted })
  callbacks.current = { onSettled, onCompleted }
  const [store] = useState(() => createStore(initial,
    (id, filled) => callbacks.current.onSettled(id, filled),
    id => callbacks.current.onCompleted(id)))
  useEffect(() => { store.activate(); return () => store.dispose() }, [store])
  return <DailyStateContext.Provider value={store}>{children}</DailyStateContext.Provider>
}

// ---------------------------------------------------------------------------
// Individual cards
// ---------------------------------------------------------------------------

interface BaseCardProps {
  cardId: DailyStateCardId
  isFuture: boolean
  inCompletedSection?: boolean
}

// ---------------------------------------------------------------------------
// Duration field (hours + minutes)
// ---------------------------------------------------------------------------

/** `450` → `['7', '30']`; `null` (no value) → two empty boxes. */
function splitMinutes(total: number | null): [string, string] {
  return total === null ? ['', ''] : [String(Math.floor(total / 60)), String(total % 60)]
}

/**
 * Local «ч / мин» pair for one duration field.
 *
 * The shared draft is the source of truth, but the two boxes keep their own
 * text so the user can type freely. An outside change to the draft — the card
 * being cleared, a value arriving from another path — is therefore adopted,
 * while the component's own edit (the value it just wrote to the draft) keeps
 * exactly what was typed, digits and all. Nothing here writes by itself, so it
 * can never loop with the autosave.
 */
export function useDurationParts(
  value: number | null,
  commit: (total: number | null) => void,
) {
  const [hours, setHours] = useState(() => splitMinutes(value)[0])
  const [minutes, setMinutes] = useState(() => splitMinutes(value)[1])
  // What the boxes themselves last produced, so the echo of our own write is
  // never mistaken for an outside change.
  const written = useRef<number | null>(value)

  useEffect(() => {
    if (value === written.current) return
    written.current = value
    const [nextHours, nextMinutes] = splitMinutes(value)
    setHours(nextHours)
    setMinutes(nextMinutes)
  }, [value])

  function change(nextHours: string, nextMinutes: string) {
    setHours(nextHours)
    setMinutes(nextMinutes)
    const total = nextHours === '' && nextMinutes === ''
      ? null
      : Number(nextHours) * 60 + Number(nextMinutes)
    written.current = total
    commit(total)
  }

  return { hours, minutes, change }
}

/**
 * Shell shared by all daily-state cards.
 * Handles the OK-button countdown, error display, and the card styling states.
 */
function DailyStateCardShell({
  cardId,
  isFuture,
  inCompletedSection = false,
  filled,
  children,
  onClear,
}: BaseCardProps & {
  filled: boolean
  children: React.ReactNode
  onClear?: () => void
}) {
  const snap = useStoreSnapshot()
  const save = snap.cards[cardId]
  // `stored` tracks whether this card's value has already reached the server,
  // independently of the current draft (`filled`), so the «ОК» control stays
  // put while a new edit is in flight. `savedRevision` only advances when a
  // settled write matches the card's own latest revision.
  const stored = save.savedRevision > 0
  const readiness = useCardReadiness({ ...save, stored, filled, completed: inCompletedSection,
    onDone: () => snap.complete(cardId) })
  const { timerState, progress, confirmNow } = readiness
  const isCounting = timerState === 'counting'
  const busy = save.revision !== save.savedRevision && !save.error

  return (
    <div
      role="group" aria-label={DAILY_STATE_CARD_LABELS[cardId]} data-card-id={cardId}
      {...readiness.focusProps}
      className={[
        'ccard',
        isCounting && !inCompletedSection ? 'ccard--counting' : '',
        filled && !inCompletedSection ? 'ccard--filled' : '',
        busy ? 'ccard--busy' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="ccard__head">
        <span className="ccard__name">{DAILY_STATE_CARD_LABELS[cardId]}</span>
        {filled ? (
          <span className="ccard__pill ccard__pill--done">✓</span>
        ) : (
          <span className="ccard__pill ccard__pill--none">—</span>
        )}
        {filled && onClear ? (
          <button
            type="button"
            className="ccard__clear-btn"
            disabled={isFuture}
            onClick={onClear}
            aria-label="Убрать значение"
          >
            ✕
          </button>
        ) : null}
      </div>

      <fieldset className="ccard__fieldset" disabled={isFuture}>
        {children}
      </fieldset>

      {save.error !== null ? (
        <p className="ccard__error" role="alert">
          {save.error}
        </p>
      ) : null}

      {readiness.showOk ? (
        <OkButton
          progress={progress}
          counting={isCounting}
          onConfirm={confirmNow}
          disabled={!readiness.canConfirm}
          locked={readiness.locked}
          onToggleLock={readiness.toggleLock}
        />
      ) : null}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Scale card (mood / energy / wellbeing)
// ---------------------------------------------------------------------------

const SCALE_OPTIONS = [1, 2, 3, 4, 5] as const
const SCALE_HINTS: Record<DailyStateCardId, { low: string; high: string }> = {
  mood: { low: 'плохое', high: 'отличное' },
  energy: { low: 'нет сил', high: 'много' },
  wellbeing: { low: 'плохое', high: 'отличное' },
  sleep: { low: '', high: '' },
  alcohol: { low: '', high: '' },
  gaming: { low: '', high: '' },
  computer: { low: '', high: '' },
  'ds-note': { low: '', high: '' },
}

function ScaleCard({
  cardId,
  field,
  isFuture,
  inCompletedSection,
}: BaseCardProps & { field: keyof Pick<DailyStateInput, 'mood' | 'energy' | 'wellbeing'> }) {
  const { draft, patch, clearField } = useStoreSnapshot()
  const value = draft[field]
  const hint = SCALE_HINTS[cardId]

  return (
    <DailyStateCardShell
      cardId={cardId}
      isFuture={isFuture}
      inCompletedSection={inCompletedSection}
      filled={value !== null}
      onClear={() => clearField(cardId)}
    >
      <div className="ccard__scale">
        {SCALE_OPTIONS.map((n) => (
          <button
            key={n}
            type="button"
            className={`ccard__scale-btn${value === n ? ' ccard__scale-btn--active' : ''}`}
            aria-pressed={value === n}
            onClick={() => patch({ [field]: value === n ? null : n })}
          >
            {n}
          </button>
        ))}
      </div>
      <span className="ccard__scale-hint">
        {hint.low} · {hint.high}
      </span>
    </DailyStateCardShell>
  )
}

// ---------------------------------------------------------------------------
// Sleep card
// ---------------------------------------------------------------------------

const SLEEP_STATUS_OPTIONS = [
  { value: 'underslept' as const, label: 'Недосып' },
  { value: 'normal' as const,     label: 'Норма' },
  { value: 'overslept' as const,  label: 'Пересып' },
]

function SleepCard({ isFuture, inCompletedSection }: BaseCardProps) {
  const { draft, patch, clearField } = useStoreSnapshot()

  const filled =
    draft.sleep_status !== null || draft.sleep_minutes !== null

  const duration = useDurationParts(draft.sleep_minutes, total => patch({ sleep_minutes: total }))

  return (
    <DailyStateCardShell
      cardId="sleep"
      isFuture={isFuture}
      inCompletedSection={inCompletedSection}
      filled={filled}
      onClear={() => clearField('sleep')}
    >
      <div className="ccard__segments">
        {SLEEP_STATUS_OPTIONS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            className={`ccard__seg-btn${draft.sleep_status === value ? ' ccard__seg-btn--active' : ''}`}
            aria-pressed={draft.sleep_status === value}
            onClick={() => patch({ sleep_status: draft.sleep_status === value ? null : value })}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="ccard__duration">
        <label className="ccard__duration-label">
          ч
          <input
            className="ccard__input ccard__input--tiny"
            type="number"
            min={0}
            max={24}
            step={1}
            value={duration.hours}
            placeholder="0"
            onChange={(e) => duration.change(e.target.value, duration.minutes)}
          />
        </label>
        <label className="ccard__duration-label">
          мин
          <input
            className="ccard__input ccard__input--tiny"
            type="number"
            min={0}
            max={59}
            step={1}
            value={duration.minutes}
            placeholder="0"
            onChange={(e) => duration.change(duration.hours, e.target.value)}
          />
        </label>
      </div>
    </DailyStateCardShell>
  )
}

// ---------------------------------------------------------------------------
// Boolean card (alcohol / gaming / computer)
// ---------------------------------------------------------------------------

function BoolCard({
  cardId,
  field,
  isFuture,
  inCompletedSection,
  detailField,
  detailPlaceholder,
  durationField,
  durationLabel,
}: BaseCardProps & {
  field: keyof Pick<DailyStateInput, 'alcohol' | 'gaming' | 'computer_overuse'>
  detailField?: keyof Pick<DailyStateInput, 'alcohol_detail'>
  detailPlaceholder?: string
  durationField?: keyof Pick<DailyStateInput, 'gaming_minutes' | 'computer_minutes'>
  durationLabel?: string
}) {
  const { draft, patch, clearField } = useStoreSnapshot()
  const value = draft[field]

  const duration = useDurationParts(
    durationField ? draft[durationField] : null,
    total => { if (durationField) patch({ [durationField]: total }) },
  )

  const filled = value !== null

  return (
    <DailyStateCardShell
      cardId={cardId}
      isFuture={isFuture}
      inCompletedSection={inCompletedSection}
      filled={filled}
      onClear={() => clearField(cardId)}
    >
      <div className="ccard__segments">
        <button
          type="button"
          className={`ccard__seg-btn${value === false ? ' ccard__seg-btn--active' : ''}`}
          aria-pressed={value === false}
          onClick={() => patch({ [field]: value === false ? null : false })}
        >
          Нет
        </button>
        <button
          type="button"
          className={`ccard__seg-btn${value === true ? ' ccard__seg-btn--active' : ''}`}
          aria-pressed={value === true}
          onClick={() => patch({ [field]: value === true ? null : true })}
        >
          Да
        </button>
      </div>

      {value === true && detailField ? (
        <input
          className="ccard__input"
          placeholder={detailPlaceholder ?? 'Уточнение…'}
          maxLength={200}
          value={(draft[detailField] as string | null) ?? ''}
          onChange={(e) => patch({ [detailField]: e.target.value || null })}
        />
      ) : null}

      {value === true && durationField ? (
        <div className="ccard__duration">
          <label className="ccard__duration-label">
            ч
            <input
              className="ccard__input ccard__input--tiny"
              type="number"
              min={0}
              max={24}
              step={1}
              value={duration.hours}
              placeholder="0"
              onChange={(e) => duration.change(e.target.value, duration.minutes)}
            />
          </label>
          <label className="ccard__duration-label">
            мин
            <input
              className="ccard__input ccard__input--tiny"
              type="number"
              min={0}
              max={59}
              step={1}
              value={duration.minutes}
              placeholder="0"
              onChange={(e) => duration.change(duration.hours, e.target.value)}
            />
          </label>
          {durationLabel ? (
            <span className="ccard__duration-hint">{durationLabel}</span>
          ) : null}
        </div>
      ) : null}

    </DailyStateCardShell>
  )
}

// ---------------------------------------------------------------------------
// Computer card — duration is always shown, overuse is just a flag
// ---------------------------------------------------------------------------

function ComputerCard({ isFuture, inCompletedSection }: BaseCardProps) {
  const { draft, patch, clearField } = useStoreSnapshot()
  const value = draft.computer_overuse
  const filled = value !== null || draft.computer_minutes !== null

  const duration = useDurationParts(
    draft.computer_minutes,
    total => patch({ computer_minutes: total }),
  )

  return (
    <DailyStateCardShell
      cardId="computer"
      isFuture={isFuture}
      inCompletedSection={inCompletedSection}
      filled={filled}
      onClear={() => clearField('computer')}
    >
      <div className="ccard__segments">
        <button
          type="button"
          className={`ccard__seg-btn${value === false ? ' ccard__seg-btn--active' : ''}`}
          aria-pressed={value === false}
          onClick={() => patch({ computer_overuse: value === false ? null : false })}
        >
          Норма
        </button>
        <button
          type="button"
          className={`ccard__seg-btn${value === true ? ' ccard__seg-btn--active' : ''}`}
          aria-pressed={value === true}
          onClick={() => patch({ computer_overuse: value === true ? null : true })}
        >
          Слишком много
        </button>
      </div>
      <div className="ccard__duration">
        <label className="ccard__duration-label">
          ч
          <input
            className="ccard__input ccard__input--tiny"
            type="number"
            min={0}
            max={24}
            step={1}
            value={duration.hours}
            placeholder="0"
            onChange={(e) => duration.change(e.target.value, duration.minutes)}
          />
        </label>
        <label className="ccard__duration-label">
          мин
          <input
            className="ccard__input ccard__input--tiny"
            type="number"
            min={0}
            max={59}
            step={1}
            value={duration.minutes}
            placeholder="0"
            onChange={(e) => duration.change(duration.hours, e.target.value)}
          />
        </label>
      </div>
    </DailyStateCardShell>
  )
}

// ---------------------------------------------------------------------------
// Note card
// ---------------------------------------------------------------------------

function NoteCard({ isFuture, inCompletedSection }: BaseCardProps) {
  const { draft, patch, clearField } = useStoreSnapshot()
  const filled = (draft.note ?? '').trim() !== ''

  return (
    <DailyStateCardShell
      cardId="ds-note"
      isFuture={isFuture}
      inCompletedSection={inCompletedSection}
      filled={filled}
      onClear={() => clearField('ds-note')}
    >
      <textarea
        className="ccard__input ccard__textarea"
        rows={2}
        maxLength={500}
        aria-label="Заметка дня"
        placeholder="Заметка о дне…"
        value={draft.note ?? ''}
        onChange={(e) => patch({ note: e.target.value || null })}
      />
    </DailyStateCardShell>
  )
}

// ---------------------------------------------------------------------------
// Public API — render a card by ID
// ---------------------------------------------------------------------------

export interface DailyStateCardProps {
  cardId: DailyStateCardId
  isFuture: boolean
  inCompletedSection?: boolean
}

/** Renders the correct card widget for a given `DailyStateCardId`. */
export function DailyStateCard({
  cardId,
  isFuture,
  inCompletedSection = false,
}: DailyStateCardProps) {
  const base: BaseCardProps = { cardId, isFuture, inCompletedSection }

  switch (cardId) {
    case 'mood':
      return <ScaleCard {...base} field="mood" />
    case 'energy':
      return <ScaleCard {...base} field="energy" />
    case 'wellbeing':
      return <ScaleCard {...base} field="wellbeing" />
    case 'sleep':
      return <SleepCard {...base} />
    case 'alcohol':
      return (
        <BoolCard
          {...base}
          field="alcohol"
          detailField="alcohol_detail"
          detailPlaceholder="Например, бокал вина"
        />
      )
    case 'gaming':
      return (
        <BoolCard
          {...base}
          field="gaming"
          durationField="gaming_minutes"
          durationLabel="время в играх"
        />
      )
    case 'computer':
      return <ComputerCard {...base} />
    case 'ds-note':
      return <NoteCard {...base} />
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toInput(state: DailyStateInput | null): DailyStateInput {
  const empty = emptyDailyState()
  if (!state) return empty
  for (const key of Object.keys(empty) as (keyof DailyStateInput)[]) {
    Object.assign(empty, { [key]: state[key] })
  }
  return empty
}

function detectCard(patch: Partial<DailyStateInput>): DailyStateCardId {
  if ('mood' in patch)             return 'mood'
  if ('energy' in patch)           return 'energy'
  if ('wellbeing' in patch)        return 'wellbeing'
  if ('sleep_status' in patch || 'sleep_minutes' in patch) return 'sleep'
  if ('alcohol' in patch || 'alcohol_detail' in patch)     return 'alcohol'
  if ('gaming' in patch || 'gaming_minutes' in patch)      return 'gaming'
  if ('computer_overuse' in patch || 'computer_minutes' in patch) return 'computer'
  return 'ds-note'
}

function clearCardFields(
  cardId: DailyStateCardId,
  current: DailyStateInput,
): DailyStateInput {
  const next = { ...current }
  switch (cardId) {
    case 'mood':      next.mood = null; break
    case 'energy':    next.energy = null; break
    case 'wellbeing': next.wellbeing = null; break
    case 'sleep':
      next.sleep_status = null; next.sleep_minutes = null; break
    case 'alcohol':
      next.alcohol = null; next.alcohol_detail = null; break
    case 'gaming':
      next.gaming = null; next.gaming_minutes = null; break
    case 'computer':
      next.computer_overuse = null; next.computer_minutes = null; break
    case 'ds-note':
      next.note = null; break
  }
  return next
}

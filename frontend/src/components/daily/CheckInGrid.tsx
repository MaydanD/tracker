import { useCallback, useRef, useState } from 'react'
import type { DailyEntry, DayItem, ProgressState } from '../../api/types'
import { HabitCard, tracksValueType } from './HabitCard'
import { DAILY_STATE_CARD_IDS, DailyStateCard, DailyStateProvider, isDailyStateCardFilled,
  useInitialDailyState, type DailyStateCardId } from './DailyStateCards'
import { resolveOwlAsset } from '../owl/owlAssets'

type CardId = `habit:${number}` | `ds:${DailyStateCardId}`
export interface CheckInGridProps {
  items: DayItem[]
  entryDate: string
  isFuture: boolean
  onChanged: () => void
  progress?: ProgressState | null
  /**
   * Whether the separate daily-state card row is shown.
   *
   * The canonical habit set answers mood, energy, sleep, alcohol, games and
   * computer use itself, so the check-in screen turns these off and no question
   * is asked twice in one place.
   */
  includeDailyState?: boolean
  /** Group the cards under their sphere heading, in the order the API returns. */
  groupByArea?: boolean
}

/**
 * Whether a habit already holds an answer for this date.
 *
 * A completion habit is answered by its row: done, missed or skipped. A habit
 * answered on a value scale is answered by the *value*, so a row that carries no
 * value — a completion recorded before that habit became a value scale, say — is
 * not an answer and must not hide the card under «Уже отмечено». A recorded `0`
 * is a real value and counts, which is what keeps zero apart from missing.
 */
function answered(item: DayItem): boolean {
  if (item.entry === null) return false
  return !tracksValueType(item.value_type) || item.entry.value !== null
}

/** The habits or spheres of one date, answered card by card. */
function areaGroups(items: DayItem[]): { id: number; name: string; color: string; items: DayItem[] }[] {
  const groups: { id: number; name: string; color: string; items: DayItem[] }[] = []
  for (const item of items) {
    const last = groups[groups.length - 1]
    if (last !== undefined && last.id === item.area.id) last.items.push(item)
    else groups.push({ ...item.area, items: [item] })
  }
  return groups
}

// Key the resource as well as the cards, including when used outside CheckInPage.
export function CheckInGrid(props: CheckInGridProps) {
  return <GridResource key={props.entryDate} {...props} />
}
function GridResource(props: CheckInGridProps) {
  const events = useRef<(id: CardId, done: boolean) => void>(() => {})
  const onSettled = useCallback((id: DailyStateCardId, filled: boolean) => {
    if (!filled) events.current(`ds:${id}`, false)
    props.onChanged()
  }, [props.onChanged])
  const onCompleted = useCallback((id: DailyStateCardId) => events.current(`ds:${id}`, true), [])
  const cards = <GridCards {...props} events={events} />
  // Without the separate daily-state cards there is nothing to read, so the grid
  // must not wait for that endpoint: it used to hold back every habit card
  // behind a «Загрузка состояния дня…» that this screen never needed.
  if (props.includeDailyState === false) return cards
  return <DailyStateProvider date={props.entryDate} onSettled={onSettled} onCompleted={onCompleted}>
    {cards}
  </DailyStateProvider>
}
function GridCards({ items, entryDate, isFuture, onChanged, events,
  includeDailyState = true, groupByArea = false }: CheckInGridProps & {
  events: React.RefObject<(id: CardId, done: boolean) => void>
}) {
  const initial = useInitialDailyState()
  const stateCards = includeDailyState ? DAILY_STATE_CARD_IDS : []
  const [done, setDone] = useState(() => new Set<CardId>([
    ...items.filter(answered).map(item => `habit:${item.habit_id}` as CardId),
    ...stateCards.filter(id => isDailyStateCardFilled(id, initial)).map(id => `ds:${id}` as CardId),
  ]))
  // Keep successful local entries available when moving a card before a page
  // refresh resolves. Identity never depends on its mutable status.
  const [entries, setEntries] = useState<Record<number, DailyEntry | null>>({})
  const move = useCallback((id: CardId, completed: boolean) => setDone(previous => {
    if (previous.has(id) === completed) return previous
    const next = new Set(previous)
    if (completed) next.add(id); else next.delete(id)
    return next
  }), [])
  events.current = move
  function settled(id: number, entry: DailyEntry | null) {
    setEntries(previous => ({ ...previous, [id]: entry }))
    if (!entry) move(`habit:${id}`, false)
    onChanged()
  }
  function habitCards(completed: boolean, subset: DayItem[] = items) {
    return subset.filter(item => done.has(`habit:${item.habit_id}`) === completed).map(item =>
      <HabitCard key={item.habit_id} item={Object.hasOwn(entries, item.habit_id) ? { ...item, entry: entries[item.habit_id]! } : item}
        entryDate={entryDate} isFuture={isFuture} inCompletedSection={completed}
        onSettled={settled} onTimerDone={id => move(`habit:${id}`, true)} />)
  }
  function cards(completed: boolean) {
    // The sphere is the structure of the day: a heading names each group for
    // screen readers, and an area whose cards are all in the other section
    // leaves no empty heading behind.
    const groups = areaGroups(items)
      .map((group) => ({ group, cards: habitCards(completed, group.items) }))
      .filter((row) => row.cards.length > 0)
    return <div className={`checkin-grid__cells${completed ? ' checkin-grid__cells--done' : ''}`}>
      {stateCards.filter(id => done.has(`ds:${id}`) === completed).map(id =>
        <DailyStateCard key={id} cardId={id} isFuture={isFuture} inCompletedSection={completed} />)}
      {groupByArea ? groups.map(({ group, cards: rows }) =>
        <section key={group.id} className="checkin-group" aria-label={group.name}>
          <h2 className="checkin-group__title">{group.name}</h2>
          <div className="checkin-group__cards">{rows}</div>
        </section>)
        : habitCards(completed)}
    </div>
  }
  const total = items.length + stateCards.length
  return <div className="checkin-grid">
    {done.size === total ? <div className="checkin-grid__complete">
      <img className="checkin-grid__complete-img" src={resolveOwlAsset('owl_all_done')} alt="" aria-hidden="true" />
      <span>Всё отмечено за этот день</span>
    </div> : null}
    {cards(false)}
    {done.size > 0 ? <details className="checkin-grid__done">
      <summary className="checkin-grid__done-summary">{`Уже отмечено · ${done.size}`}</summary>
      {cards(true)}
    </details> : null}
  </div>
}

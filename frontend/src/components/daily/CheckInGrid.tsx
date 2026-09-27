import { useCallback, useRef, useState } from 'react'
import type { DailyEntry, DayItem, ProgressState } from '../../api/types'
import { HabitCard } from './HabitCard'
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
  return <DailyStateProvider date={props.entryDate} onSettled={onSettled} onCompleted={onCompleted}>
    <GridCards {...props} events={events} />
  </DailyStateProvider>
}
function GridCards({ items, entryDate, isFuture, onChanged, events }: CheckInGridProps & {
  events: React.RefObject<(id: CardId, done: boolean) => void>
}) {
  const initial = useInitialDailyState()
  const [done, setDone] = useState(() => new Set<CardId>([
    ...items.filter(item => item.entry !== null).map(item => `habit:${item.habit_id}` as CardId),
    ...DAILY_STATE_CARD_IDS.filter(id => isDailyStateCardFilled(id, initial)).map(id => `ds:${id}` as CardId),
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
  function cards(completed: boolean) {
    return <div className={`checkin-grid__cells${completed ? ' checkin-grid__cells--done' : ''}`}>
      {DAILY_STATE_CARD_IDS.filter(id => done.has(`ds:${id}`) === completed).map(id =>
        <DailyStateCard key={id} cardId={id} isFuture={isFuture} inCompletedSection={completed} />)}
      {items.filter(item => done.has(`habit:${item.habit_id}`) === completed).map(item =>
        <HabitCard key={item.habit_id} item={Object.hasOwn(entries, item.habit_id) ? { ...item, entry: entries[item.habit_id]! } : item}
          entryDate={entryDate} isFuture={isFuture} inCompletedSection={completed}
          onSettled={settled} onTimerDone={id => move(`habit:${id}`, true)} />)}
    </div>
  }
  return <div className="checkin-grid">
    {done.size === items.length + DAILY_STATE_CARD_IDS.length ? <div className="checkin-grid__complete">
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

import { useEffect, useRef, useState, type FormEvent } from 'react'

import { describeApiError } from '../../api/client'
import { deleteDailyState, emptyDailyState, fetchDailyState, saveDailyState, type DailyStateInput, type DailyStateResponse } from '../../api/dailyState'
import { useAsyncData } from '../../hooks/useAsyncData'
import { ErrorBanner, LoadingText } from '../Feedback'

/** Key the entire resource by date: neither a late read nor a late write can
 * replace another day's draft, even when the user leaves and returns quickly. */
export function DailyStatePanel({ date }: { date: string }) {
  return <DailyStateResource key={date} date={date} />
}

function DailyStateResource({ date }: { date: string }) {
  const { data, error, loading, reload } = useAsyncData((signal) => fetchDailyState(date, signal), [date])
  return (
    <section className="daily-state" aria-label="Состояние дня">
      <h2>Состояние дня</h2>
      <p className="daily-state__hint">Наблюдения о дне. Не влияют на оценки и серии привычек.</p>
      <ErrorBanner message={error} />
      {error ? <button className="button" onClick={reload}>Повторить загрузку состояния</button>
        : loading || data?.state_date !== date ? <LoadingText>Загрузка состояния дня…</LoadingText>
        : <DailyStateForm initial={data} />}
    </section>
  )
}

function Segments<T extends string | number | boolean | null>({ label, value, options, onChange }: {
  label: string; value: T; options: readonly (readonly [T, string])[]; onChange: (value: T) => void
}) {
  return <fieldset className="daily-state__choice">
    <legend>{label}</legend>
    <div className="daily-state__segments">
      {options.map(([option, text]) => <button key={String(option)} type="button"
        className={`button ${option === null ? 'daily-state__unset' : ''}`}
        aria-pressed={value === option} onClick={() => onChange(option)}>{text}</button>)}
    </div>
  </fieldset>
}

const triState = [[null, 'Не указано'], [false, 'Нет'], [true, 'Да']] as const
const scales = [[null, 'Не указано'], [1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5']] as const

function Duration({ label, value, onChange }: { label: string; value: number | null; onChange: (value: number | null) => void }) {
  // Blank and zero are distinct. Each part can be cleared independently.
  const [hours, setHours] = useState(value === null ? '' : String(Math.floor(value / 60)))
  const [minutes, setMinutes] = useState(value === null ? '' : String(value % 60))
  function change(h: string, m: string) {
    setHours(h); setMinutes(m)
    onChange(h === '' && m === '' ? null : Number(h) * 60 + Number(m))
  }
  return <fieldset className="daily-state__duration">
    <legend>{label}</legend>
    <label>ч <input className="field__input field__input--narrow" aria-label={`${label}: часы`} type="number" min="0" max="24" step="1"
      value={hours} onChange={(event) => change(event.target.value, minutes)} /></label>
    <label>мин <input className="field__input field__input--narrow" aria-label={`${label}: минуты`} type="number" min="0" max={Number(hours) === 24 ? 0 : 59} step="1"
      value={minutes} onChange={(event) => change(hours, event.target.value)} /></label>
  </fieldset>
}

function DailyStateForm({ initial }: { initial: DailyStateResponse }) {
  const [draft, setDraft] = useState<DailyStateInput>(() => toInput(initial.state))
  const [exists, setExists] = useState(initial.state !== null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const active = useRef(true)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  const future = initial.state_date > initial.today
  const empty = Object.values(draft).every((value) => value === null || (typeof value === 'string' && value.trim() === ''))

  function change(patch: Partial<DailyStateInput>) {
    setDraft((previous) => ({ ...previous, ...patch }))
    setMessage(null); setError(null)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (busy || future || empty) return
    setBusy(true); setError(null); setMessage(null)
    try {
      const state = await saveDailyState(initial.state_date, draft)
      if (!active.current) return
      setDraft(toInput(state)); setExists(true); setVersion((v) => v + 1)
      setMessage('Состояние дня сохранено')
    } catch (cause) { if (active.current) setError(describeApiError(cause)) }
    finally { if (active.current) setBusy(false) }
  }

  async function clear() {
    if (busy || future) return
    setBusy(true); setError(null); setMessage(null)
    try {
      await deleteDailyState(initial.state_date)
      if (!active.current) return
      setDraft(emptyDailyState()); setExists(false); setVersion((v) => v + 1)
      setMessage('Состояние дня удалено')
    } catch (cause) { if (active.current) setError(describeApiError(cause)) }
    finally { if (active.current) setBusy(false) }
  }

  return <form onSubmit={save}>
    {future ? <p>Состояние будущего дня нельзя заполнять</p>
      : !exists ? <p className="daily-state__hint">Состояние пока не заполнено. Можно указать только часть полей.</p> : null}
    <fieldset className="daily-state__fields" disabled={future || busy}>
      <div className="daily-state__grid">
        <div><Segments label="Настроение" value={draft.mood} options={scales} onChange={(mood) => change({ mood })} /><small>1 — очень плохое · 5 — отличное</small></div>
        <div><Segments label="Энергия" value={draft.energy} options={scales} onChange={(energy) => change({ energy })} /><small>1 — сил нет · 5 — очень много</small></div>
        <div><Segments label="Самочувствие" value={draft.wellbeing} options={scales} onChange={(wellbeing) => change({ wellbeing })} /><small>1 — очень плохое · 5 — отличное</small></div>
        <div>
          <Segments label="Сон" value={draft.sleep_status} options={[[null, 'Не указано'], ['underslept', 'Недосып'], ['normal', 'Норма'], ['overslept', 'Пересып']]} onChange={(sleep_status) => change({ sleep_status })} />
          <Duration key={`sleep-${version}`} label="Длительность сна" value={draft.sleep_minutes} onChange={(sleep_minutes) => change({ sleep_minutes })} />
        </div>
        <div>
          <Segments label="Алкоголь" value={draft.alcohol} options={triState} onChange={(alcohol) => change({ alcohol, alcohol_detail: alcohol === true ? draft.alcohol_detail : null })} />
          {draft.alcohol === true ? <label className="field">Уточнение алкоголя<input className="field__input" maxLength={200} placeholder="Например, бокал вина" value={draft.alcohol_detail ?? ''} onChange={(e) => change({ alcohol_detail: e.target.value || null })} /></label> : null}
        </div>
        <div>
          <Segments label="Игры" value={draft.gaming} options={triState} onChange={(gaming) => change({ gaming, gaming_minutes: gaming === true ? draft.gaming_minutes : null })} />
          {draft.gaming === true ? <Duration key={`gaming-${version}`} label="Время в играх" value={draft.gaming_minutes} onChange={(gaming_minutes) => change({ gaming_minutes })} /> : null}
        </div>
        <div>
          <Segments label="Слишком много времени за компьютером" value={draft.computer_overuse} options={triState} onChange={(computer_overuse) => change({ computer_overuse })} />
          <Duration key={`computer-${version}`} label="Общее время за компьютером" value={draft.computer_minutes} onChange={(computer_minutes) => change({ computer_minutes })} />
        </div>
      </div>
      <label className="field">Заметка дня<textarea className="field__input" rows={2} maxLength={500} value={draft.note ?? ''} onChange={(e) => change({ note: e.target.value || null })} /></label>
      <div className="daily-state__actions">
        <button className="button button--primary" type="submit" disabled={empty}>Сохранить состояние</button>
        {exists ? <button className="button" type="button" onClick={clear}>Очистить состояние</button> : null}
      </div>
    </fieldset>
    <ErrorBanner message={error} />
    {message ? <p role="status">{message}</p> : null}
  </form>
}

function toInput(state: DailyStateInput | null): DailyStateInput {
  const input = emptyDailyState()
  if (state === null) return input
  // Strip response metadata: PUT is a strict, complete replacement payload.
  for (const key of Object.keys(input) as (keyof DailyStateInput)[]) {
    Object.assign(input, { [key]: state[key] })
  }
  return input
}

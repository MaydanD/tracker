import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StrictMode } from 'react'
import { emptyDailyState, type DailyStateInput } from '../../api/dailyState'
import { dailyEntryFixture, dayItemFixture } from '../../test/fixtures'
import { emptyResponse, jsonResponse, stubFetch } from '../../test/fetchStub'
import { CheckInGrid } from './CheckInGrid'

const DATE = '2026-09-27'
let time = 0
let frames: Map<number, FrameRequestCallback>
let nextId = 0
beforeEach(() => {
  time = 0; frames = new Map(); nextId = 0
  vi.spyOn(performance, 'now').mockImplementation(() => time)
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { frames.set(++nextId, cb); return nextId })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id))
})
afterEach(() => vi.unstubAllGlobals())
function advance(ms: number) {
  act(() => {
    time += ms
    const pending = [...frames.values()]; frames.clear()
    pending.forEach(cb => cb(time))
  })
}
function gate() {
  let resolve!: () => void
  const promise = new Promise<void>(r => { resolve = r })
  return { promise, resolve }
}
function api(initial: Partial<DailyStateInput> = {}) {
  let state = { ...emptyDailyState(), ...initial }
  const writes: DailyStateInput[] = []
  const habits: unknown[] = []
  const controls = { fail: false, pause: null as ReturnType<typeof gate> | null }
  stubFetch(async (url, init) => {
    const method = init?.method ?? 'GET'
    if (String(url).endsWith('/state')) {
      if (method === 'GET') return jsonResponse({ state_date: DATE, today: DATE, state })
      if (method === 'DELETE') { state = emptyDailyState(); return emptyResponse() }
      const body = JSON.parse(String(init?.body)) as DailyStateInput
      writes.push(body)
      const pause = controls.pause; controls.pause = null
      if (pause) await pause.promise
      if (controls.fail) return jsonResponse({ error: { code: 'internal_error' } }, 500)
      state = body
      return jsonResponse(state)
    }
    if (method === 'DELETE') return emptyResponse()
    const body = JSON.parse(String(init?.body))
    habits.push(body)
    const pause = controls.pause; controls.pause = null
    if (pause) await pause.promise
    if (controls.fail) return jsonResponse({ error: { code: 'internal_error' } }, 500)
    return jsonResponse(dailyEntryFixture({ ...body, habit_id: 1, entry_date: DATE }))
  })
  return { writes, habits, controls }
}
function grid(persistedHabit = false, onChanged = vi.fn()) {
  const items = [dayItemFixture({ habit_id: 1, name: 'Чтение', entry: persistedHabit ? dailyEntryFixture() : null })]
  const props = { items, entryDate: DATE, isFuture: false, onChanged }
  return { ...render(<StrictMode><CheckInGrid {...props} /></StrictMode>), props }
}
function card(name: string) { return screen.getByRole('group', { name, hidden: true }) }
function active(name: string) { expect(card(name).closest('details')).toBeNull() }
function completed(name: string) { expect(card(name).closest('details')).not.toBeNull() }
function pick(name: string, value: string) { fireEvent.click(within(card(name)).getByRole('button', { name: value, hidden: true })) }
function ok(name: string) { return within(card(name)).queryByRole('button', { name: /ОК/, hidden: true }) }
async function saved(name: string) { await waitFor(() => expect(ok(name)).not.toBeNull()) }
async function loaded() { await screen.findByText('Настроение') }
function leave(element: HTMLElement, relatedTarget: HTMLElement | null = null) { fireEvent.blur(element, { relatedTarget }) }

describe('independent check-in card lifecycle', () => {
  it('mounts persisted habits and state directly under spoiler, without any countdown', async () => {
    api({ mood: 4, energy: 2, alcohol: false, computer_minutes: 0, note: 'Записано' })
    grid(true); await loaded()
    for (const name of ['Чтение', 'Настроение', 'Энергия', 'Алкоголь', 'За компьютером', 'Заметка дня']) completed(name)
    expect(screen.getByText('Уже отмечено · 6')).toBeInTheDocument()
    expect(frames.size).toBe(0)
    advance(10_000)
    expect(screen.queryByRole('button', { name: /ОК/, hidden: true })).toBeNull()
  })
  it('does not restart saved cards after returning to the page', async () => {
    api(); const first = grid(); await loaded()
    pick('Настроение', '4'); await saved('Настроение'); advance(5_000); completed('Настроение')
    first.unmount(); grid(); await loaded()
    completed('Настроение'); expect(frames.size).toBe(0)
    pick('Энергия', '2'); await saved('Энергия')
    advance(5_000); completed('Энергия'); completed('Настроение'); active('Самочувствие')
  })
  it('keeps a new card active for five seconds and completes only that card', async () => {
    api(); grid(); await loaded()
    pick('Настроение', '4'); await saved('Настроение'); advance(3_000)
    pick('Энергия', '2'); await saved('Энергия'); advance(2_000)
    completed('Настроение'); active('Энергия'); active('Чтение')
    advance(3_000); completed('Энергия')
  })
  it.each(['Настроение', 'Чтение'])('OK completes %s immediately and exactly once', async name => {
    api(); const onChanged = vi.fn(); grid(false, onChanged); await loaded()
    pick(name, name === 'Чтение' ? 'Выполнено' : '4'); await saved(name)
    fireEvent.click(ok(name)!); completed(name)
    expect(screen.getByText('Уже отмечено · 1')).toBeInTheDocument()
    advance(8_000); expect(onChanged).toHaveBeenCalledTimes(1)
  })
  it.each(['Настроение', 'Чтение'])('lock pins %s, unlock restarts five seconds, OK overrides lock', async name => {
    api(); grid(); await loaded()
    pick(name, name === 'Чтение' ? 'Выполнено' : '4'); await saved(name)
    advance(3_000); pick(name, 'Закрыть замок — оставить карточку')
    advance(9_000); active(name); expect(frames.size).toBe(0)
    pick(name, 'Открыть замок — запустить отсчёт'); advance(4_999); active(name)
    advance(1); completed(name)
  })
  it('OK remains available on a pinned card', async () => {
    api(); grid(); await loaded(); pick('Настроение', '4'); await saved('Настроение')
    pick('Настроение', 'Закрыть замок — оставить карточку'); fireEvent.click(ok('Настроение')!)
    completed('Настроение')
  })
  it('editing resets the previous timer without unpinning the card', async () => {
    api(); grid(); await loaded(); pick('Настроение', '4'); await saved('Настроение'); advance(4_000)
    pick('Настроение', '3'); await saved('Настроение'); advance(1_001); active('Настроение')
    pick('Настроение', 'Закрыть замок — оставить карточку'); pick('Настроение', '2'); await saved('Настроение')
    advance(10_000); active('Настроение'); expect(frames.size).toBe(0)
  })
  it('text starts counting only on card focus-leave, and re-entry cancels the countdown', async () => {
    const backend = api(); grid(); await loaded()
    const text = within(card('Заметка дня')).getByRole('textbox')
    fireEvent.focus(text); fireEvent.change(text, { target: { value: 'Т' } })
    await waitFor(() => expect(backend.writes).toHaveLength(1))
    advance(10_000); active('Заметка дня'); expect(ok('Заметка дня')).toBeNull()
    fireEvent.change(text, { target: { value: 'Текст' } }); await waitFor(() => expect(backend.writes).toHaveLength(2))
    leave(text); await saved('Заметка дня'); advance(3_000)
    fireEvent.focus(text); advance(10_000); active('Заметка дня'); expect(ok('Заметка дня')).toBeNull()
    leave(text); await saved('Заметка дня'); advance(4_999); active('Заметка дня'); advance(1); completed('Заметка дня')
  })
  it('moving between controls inside one card does not count as focus-leave', async () => {
    api(); grid(); await loaded(); pick('Алкоголь', 'Да'); await saved('Алкоголь')
    const text = within(card('Алкоголь')).getByRole('textbox')
    fireEvent.focus(text); fireEvent.change(text, { target: { value: 'Бокал' } })
    const other = within(card('Алкоголь')).getByRole('button', { name: 'Да' })
    leave(text, other); fireEvent.focus(other); advance(10_000)
    active('Алкоголь'); expect(ok('Алкоголь')).toBeNull()
    leave(other); await saved('Алкоголь'); advance(5_000); completed('Алкоголь')
  })
  it('habit text also waits for focus-leave, keeping inputs enabled while saving', async () => {
    const backend = api(); grid(); await loaded(); pick('Чтение', 'Выполнено'); await saved('Чтение')
    const input = within(card('Чтение')).getByPlaceholderText('Заметка (необязательно)')
    const pending = gate(); backend.controls.pause = pending
    fireEvent.focus(input); fireEvent.change(input, { target: { value: 'А' } })
    await waitFor(() => expect(backend.habits).toHaveLength(2))
    expect(input).toBeEnabled(); advance(10_000); active('Чтение'); expect(ok('Чтение')).toBeNull()
    fireEvent.change(input, { target: { value: 'АБ' } }); leave(input)
    await act(async () => pending.resolve()); await saved('Чтение')
    expect(backend.habits.at(-1)).toMatchObject({ note: 'АБ' }); advance(5_000); completed('Чтение')
  })
  it.each(['Настроение', 'Чтение'])('failed save cannot complete %s', async name => {
    const backend = api(); grid(); await loaded(); backend.controls.fail = true
    pick(name, name === 'Чтение' ? 'Выполнено' : '4')
    await screen.findByRole('alert'); advance(10_000); active(name); expect(ok(name)).toBeNull()
  })
  it('serializes whole-record saves and never overwrites newer drafts with old responses', async () => {
    const backend = api(); grid(); await loaded()
    const pending = gate(); backend.controls.pause = pending
    pick('Настроение', '4'); await waitFor(() => expect(backend.writes).toHaveLength(1))
    pick('Настроение', '2'); pick('Энергия', '5')
    const text = within(card('Заметка дня')).getByRole('textbox')
    fireEvent.focus(text); fireEvent.change(text, { target: { value: 'Новое' } })
    expect(backend.writes).toHaveLength(1)
    await act(async () => pending.resolve()); await saved('Настроение'); await saved('Энергия')
    expect(backend.writes).toHaveLength(2)
    expect(backend.writes[1]).toMatchObject({ mood: 2, energy: 5, note: 'Новое' })
    expect(text).toHaveValue('Новое'); expect(ok('Заметка дня')).toBeNull()
  })
  it('stale success cannot start a countdown before the latest write succeeds', async () => {
    const backend = api(); grid(); await loaded()
    const first = gate(); backend.controls.pause = first
    pick('Настроение', '4'); await waitFor(() => expect(backend.writes).toHaveLength(1))
    pick('Настроение', '2'); const second = gate(); backend.controls.pause = second
    await act(async () => first.resolve()); await waitFor(() => expect(backend.writes).toHaveLength(2))
    advance(10_000); active('Настроение'); expect(ok('Настроение')).toBeNull()
    await act(async () => second.resolve()); await saved('Настроение'); advance(5_000); completed('Настроение')
  })
  it('clearing a persisted card moves it up and preserves neighbouring values', async () => {
    const backend = api({ mood: 4, energy: 2 }); grid(true); await loaded()
    pick('Настроение', 'Убрать значение'); await waitFor(() => active('Настроение'))
    completed('Энергия'); expect(backend.writes.at(-1)).toMatchObject({ mood: null, energy: 2 })
    pick('Чтение', 'Убрать отметку'); await waitFor(() => active('Чтение'))
    expect(ok('Чтение')).toBeNull()
  })
  it('day change cleans timers and ignores delayed responses from the previous day', async () => {
    const backend = api(); const view = grid(); await loaded()
    pick('Настроение', '4'); await saved('Настроение')
    const pending = gate(); backend.controls.pause = pending
    pick('Энергия', '2'); await waitFor(() => expect(backend.writes).toHaveLength(2))
    view.rerender(<CheckInGrid {...view.props} entryDate="2026-09-26" />); await loaded()
    expect(frames.size).toBe(0)
    await act(async () => pending.resolve()); advance(10_000); active('Энергия')
    expect(view.props.onChanged).toHaveBeenCalledTimes(1)
  })
  it('unmount cancels RAF and ignores pending writes without callbacks', async () => {
    const backend = api(); const view = grid(); await loaded(); pick('Настроение', '4'); await saved('Настроение')
    const pending = gate(); backend.controls.pause = pending
    pick('Энергия', '2'); await waitFor(() => expect(backend.writes).toHaveLength(2)); view.unmount()
    expect(frames.size).toBe(0); await act(async () => pending.resolve()); advance(10_000)
    expect(view.props.onChanged).toHaveBeenCalledTimes(1)
  })
  it('a click on a non-focusable card header does not finish text interaction', async () => {
    api(); grid(); await loaded()
    const text = within(card('Заметка дня')).getByRole('textbox')
    fireEvent.focus(text); fireEvent.change(text, { target: { value: 'Текст' } })
    fireEvent.pointerDown(within(card('Заметка дня')).getByText('Заметка дня')); leave(text)
    advance(10_000); expect(ok('Заметка дня')).toBeNull()
    fireEvent.pointerDown(document.body); await saved('Заметка дня'); advance(5_000); completed('Заметка дня')
  })
  it('a second discrete choice still starts a fresh countdown after real focus changes', async () => {
    api(); grid(); await loaded(); pick('Настроение', '4'); await saved('Настроение'); advance(4_000)
    const next = within(card('Настроение')).getByRole('button', { name: '2' })
    fireEvent.focus(next); fireEvent.click(next); await saved('Настроение')
    advance(1_000); active('Настроение'); advance(4_000); completed('Настроение')
  })
  it('clearing a duration also clears its visible inputs', async () => {
    api(); grid(); await loaded()
    const inputs = within(card('Сон')).getAllByRole('spinbutton')
    fireEvent.focus(inputs[0]!); fireEvent.change(inputs[0]!, { target: { value: '7' } })
    leave(inputs[0]!); await saved('Сон')
    pick('Сон', 'Убрать значение')
    await waitFor(() => expect(ok('Сон')).toBeNull())
    expect(inputs[0]).toHaveValue(null); expect(inputs[1]).toHaveValue(null)
  })

  it.each(['Настроение', 'Чтение'])('drains the latest queued edit for %s after unmount without notifying UI', async name => {
    const backend = api(); const view = grid(); await loaded()
    const first = gate(); backend.controls.pause = first
    pick(name, name === 'Чтение' ? 'Выполнено' : '4')
    await waitFor(() => expect(name === 'Чтение' ? backend.habits : backend.writes).toHaveLength(1))
    pick(name, name === 'Чтение' ? 'Пропущено' : '2'); view.unmount()
    await act(async () => first.resolve())
    if (name === 'Чтение') expect(backend.habits.at(-1)).toMatchObject({ status: 'missed' })
    else expect(backend.writes.at(-1)).toMatchObject({ mood: 2 })
    expect(view.props.onChanged).not.toHaveBeenCalled(); expect(frames.size).toBe(0)
  })

  it('autosaves all state fields, reloads them under the spoiler, and edits there', async () => {
    const backend = api(); const view = grid(); await loaded()
    pick('Настроение', '4'); pick('Энергия', '2'); pick('Самочувствие', '5'); pick('Сон', 'Недосып')
    function duration(name: string, hours: string, minutes: string) {
      const inputs = within(card(name)).getAllByRole('spinbutton', { hidden: true })
      fireEvent.change(inputs[0]!, { target: { value: hours } })
      fireEvent.change(inputs[1]!, { target: { value: minutes } })
    }
    duration('Сон', '7', '30')
    pick('Алкоголь', 'Да')
    fireEvent.change(within(card('Алкоголь')).getByRole('textbox'), { target: { value: 'Бокал' } })
    pick('Игры', 'Да'); duration('Игры', '1', '20')
    pick('За компьютером', 'Норма'); duration('За компьютером', '3', '0')
    fireEvent.change(within(card('Заметка дня')).getByRole('textbox'), { target: { value: 'День дома' } })
    const expected = { mood: 4, energy: 2, wellbeing: 5, sleep_status: 'underslept', sleep_minutes: 450,
      alcohol: true, alcohol_detail: 'Бокал', gaming: true, gaming_minutes: 80,
      computer_overuse: false, computer_minutes: 180, note: 'День дома' }
    await waitFor(() => expect(backend.writes.at(-1)).toEqual(expected))
    await act(async () => {})
    view.unmount(); grid(); await loaded()
    expect(screen.getByText('Уже отмечено · 8')).toBeInTheDocument(); expect(frames.size).toBe(0)
    expect(within(card('Заметка дня')).getByRole('textbox', { hidden: true })).toHaveValue('День дома')
    pick('Алкоголь', 'Нет'); pick('Игры', 'Нет')
    await waitFor(() => expect(backend.writes.at(-1)).toMatchObject({ alcohol: false, alcohol_detail: null, gaming: false, gaming_minutes: null }))
    completed('Алкоголь'); completed('Игры'); expect(frames.size).toBe(0)
  })
  it('shows a state-load error and retries instead of displaying an endless loader', async () => {
    stubFetch(async () => jsonResponse({ error: { code: 'internal_error' } }, 500))
    grid(); await screen.findByRole('alert')
    api({ mood: 3 })
    fireEvent.click(screen.getByRole('button', { name: 'Повторить загрузку состояния' }))
    await loaded(); completed('Настроение'); expect(frames.size).toBe(0)
  })

})

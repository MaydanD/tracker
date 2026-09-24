import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { emptyDailyState, type DailyStateInput, type DailyStateRecord } from '../api/dailyState'
import { DailyStatePanel } from '../components/daily/DailyStatePanel'
import { addDays, localTodayIso } from '../components/daily/dates'
import { createFakeApi } from '../test/fakeApi'
import { emptyResponse, jsonResponse, stubApi, stubFetch } from '../test/fetchStub'
import { CheckInPage } from './CheckInPage'

const TODAY = localTodayIso()
function record(date: string, values: Partial<DailyStateInput> = {}): DailyStateRecord {
  return { ...emptyDailyState(), ...values, id: 1, state_date: date, created_at: TODAY, updated_at: TODAY }
}
function setup() {
  const saved = new Map<string, DailyStateRecord>()
  const writes: DailyStateInput[] = []
  const api = createFakeApi()
  const fetch = stubApi({}, { fallback: (request) => {
    if (!request.path.endsWith('/state')) return api.handle(request)
    const date = request.path.split('/')[3]!
    if (request.method === 'GET') return jsonResponse({ state_date: date, today: TODAY, state: saved.get(date) ?? null })
    if (request.method === 'DELETE') { saved.delete(date); return emptyResponse() }
    const input = request.body as DailyStateInput
    writes.push(input)
    const state = record(date, input)
    saved.set(date, state)
    return jsonResponse(state)
  } })
  return { saved, writes, fetch }
}
function choose(group: string, label: string) {
  fireEvent.click(within(screen.getByRole('group', { name: group })).getByRole('button', { name: label }))
}
function selected(group: string, label: string) {
  expect(within(screen.getByRole('group', { name: group })).getByRole('button', { name: label })).toHaveAttribute('aria-pressed', 'true')
}
function input(label: string, value: string) { fireEvent.change(screen.getByLabelText(label), { target: { value } }) }
async function save() {
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить состояние' }))
  await screen.findByText('Состояние дня сохранено')
}

describe('Состояние дня', () => {
  it('starts entirely unspecified, in Russian, without an empty save', async () => {
    setup()
    render(<DailyStatePanel date={TODAY} />)
    await screen.findByText(/Состояние пока не заполнено/)
    for (const group of ['Настроение', 'Энергия', 'Самочувствие', 'Сон', 'Алкоголь', 'Игры', 'Слишком много времени за компьютером']) selected(group, 'Не указано')
    expect(screen.getByRole('button', { name: 'Сохранить состояние' })).toBeDisabled()
    expect(screen.queryByLabelText('Уточнение алкоголя')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Время в играх: часы')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Состояние дня' }).textContent).not.toMatch(/[A-Za-z]/)
    expect(screen.getByLabelText('Длительность сна: часы')).toHaveValue(null)
  })

  it('saves every field, edits, reloads and clears without refreshing habits or progress', async () => {
    const api = setup()
    const first = render(<CheckInPage />)
    await screen.findByText(/Состояние пока не заполнено/)
    choose('Настроение', '4'); choose('Энергия', '2'); choose('Самочувствие', '5')
    choose('Сон', 'Недосып'); input('Длительность сна: часы', '7'); input('Длительность сна: минуты', '30')
    choose('Алкоголь', 'Да'); input('Уточнение алкоголя', '2 пива')
    choose('Игры', 'Да'); input('Время в играх: часы', '1'); input('Время в играх: минуты', '20')
    choose('Слишком много времени за компьютером', 'Нет'); input('Общее время за компьютером: часы', '3')
    input('Заметка дня', 'День дома')
    const habitReads = api.fetch.mock.calls.filter(([url]) => !String(url).endsWith('/state')).length
    await save()
    expect(api.writes[0]).toEqual({ mood: 4, energy: 2, wellbeing: 5, sleep_status: 'underslept', sleep_minutes: 450, alcohol: true, alcohol_detail: '2 пива', gaming: true, gaming_minutes: 80, computer_overuse: false, computer_minutes: 180, note: 'День дома' })
    expect(api.fetch.mock.calls.filter(([url]) => !String(url).endsWith('/state'))).toHaveLength(habitReads)
    first.unmount()
    render(<CheckInPage />)
    await screen.findByDisplayValue('День дома')
    selected('Алкоголь', 'Да'); selected('Слишком много времени за компьютером', 'Нет')
    expect(screen.getByLabelText('Длительность сна: минуты')).toHaveValue(30)
    choose('Алкоголь', 'Нет'); choose('Игры', 'Не указано'); choose('Настроение', '1')
    await save()
    expect(api.writes[1]).toMatchObject({ alcohol: false, alcohol_detail: null, gaming: null, gaming_minutes: null, mood: 1 })
    fireEvent.click(screen.getByRole('button', { name: 'Очистить состояние' }))
    await screen.findByText('Состояние дня удалено')
    expect(api.saved.size).toBe(0)
    selected('Алкоголь', 'Не указано')
    expect(screen.getByLabelText('Длительность сна: часы')).toHaveValue(null)
  })

  it.each(['Настроение', 'Энергия', 'Самочувствие'])('supports all five values and clearing %s', async (group) => {
    setup(); render(<DailyStatePanel date={TODAY} />)
    await screen.findByText(/Состояние пока не заполнено/)
    for (const value of ['1', '2', '3', '4', '5', 'Не указано']) { choose(group, value); selected(group, value) }
  })

  it.each(['Алкоголь', 'Игры', 'Слишком много времени за компьютером'])('preserves all three states of %s through save and reload', async (group) => {
    const api = setup()
    const field = group === 'Алкоголь' ? 'alcohol' : group === 'Игры' ? 'gaming' : 'computer_overuse'
    let view = render(<DailyStatePanel date={TODAY} />)
    await screen.findByText(/Состояние пока не заполнено/)
    input('Заметка дня', 'Наблюдение')
    for (const [label, value] of [['Нет', false], ['Да', true], ['Не указано', null]] as const) {
      choose(group, label); await save()
      expect(api.writes.at(-1)?.[field]).toBe(value)
      view.unmount(); view = render(<DailyStatePanel date={TODAY} />)
      await screen.findByDisplayValue('Наблюдение'); selected(group, label)
    }
  })

  it('keeps sleep and computer durations independent, including zero and 24 hours', async () => {
    const api = setup(); render(<DailyStatePanel date={TODAY} />)
    await screen.findByText(/Состояние пока не заполнено/)
    input('Длительность сна: минуты', '0'); input('Общее время за компьютером: часы', '24')
    await save()
    expect(api.writes[0]).toMatchObject({ sleep_status: null, sleep_minutes: 0, computer_overuse: null, computer_minutes: 1440 })
    input('Длительность сна: часы', ''); input('Длительность сна: минуты', '')
    for (const status of ['Недосып', 'Норма', 'Пересып']) { choose('Сон', status); await save() }
    expect(api.writes.at(-1)).toMatchObject({ sleep_status: 'overslept', sleep_minutes: null })
  })

  it('edits historical dates and disables future state', async () => {
    const api = setup(); const past = addDays(TODAY, -3000)
    const view = render(<DailyStatePanel date={past} />)
    await screen.findByText(/Состояние пока не заполнено/)
    input('Заметка дня', 'История'); await save()
    expect(api.saved.get(past)?.note).toBe('История')
    view.rerender(<DailyStatePanel date={addDays(TODAY, 1)} />)
    await screen.findByText('Состояние будущего дня нельзя заполнять')
    expect(screen.getByLabelText('Заметка дня')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Сохранить состояние' })).toBeDisabled()
    expect(screen.queryByDisplayValue('История')).not.toBeInTheDocument()
  })

  it('ignores delayed reads when navigating between dates', async () => {
    let release!: () => void
    const past = addDays(TODAY, -1)
    stubFetch(async (url) => {
      const old = String(url).includes(TODAY)
      if (old) await new Promise<void>((resolve) => { release = resolve })
      return jsonResponse({ state_date: old ? TODAY : past, today: TODAY, state: old ? record(TODAY, { note: 'Старый ответ' }) : null })
    })
    const view = render(<DailyStatePanel date={TODAY} />)
    view.rerender(<DailyStatePanel date={past} />)
    await screen.findByText(/Состояние пока не заполнено/)
    input('Заметка дня', 'Новый черновик')
    await act(async () => { release() })
    expect(screen.getByLabelText('Заметка дня')).toHaveValue('Новый черновик')
  })

  it.each(['PUT', 'DELETE'])('ignores a delayed %s after leaving and returning to a date', async (method) => {
    let release!: () => void
    const past = addDays(TODAY, -1)
    stubFetch(async (url, init) => {
      const date = String(url).includes(TODAY) ? TODAY : past
      if (init?.method === method) {
        await new Promise<void>((resolve) => { release = resolve })
        return method === 'DELETE' ? emptyResponse() : jsonResponse(record(TODAY, { note: 'Поздняя запись' }))
      }
      return jsonResponse({ state_date: date, today: TODAY, state: record(date, { note: 'Сохранено ранее' }) })
    })
    const view = render(<DailyStatePanel date={TODAY} />)
    await screen.findByDisplayValue('Сохранено ранее')
    fireEvent.click(screen.getByRole('button', { name: method === 'PUT' ? 'Сохранить состояние' : 'Очистить состояние' }))
    await waitFor(() => expect(release).toBeDefined())
    view.rerender(<DailyStatePanel date={past} />)
    await screen.findByDisplayValue('Сохранено ранее')
    view.rerender(<DailyStatePanel date={TODAY} />)
    await screen.findByDisplayValue('Сохранено ранее')
    input('Заметка дня', 'Новый черновик')
    await act(async () => { release() })
    expect(screen.getByLabelText('Заметка дня')).toHaveValue('Новый черновик')
  })

  it('keeps drafts after a failed write and offers a Russian retry after failed read', async () => {
    let fails = true
    stubApi({
      [`GET /api/days/${TODAY}/state`]: () => fails ? jsonResponse({ error: { code: 'internal_error', message: 'English error' } }, 500) : jsonResponse({ state_date: TODAY, today: TODAY, state: null }),
      [`PUT /api/days/${TODAY}/state`]: () => jsonResponse({ error: { code: 'invalid_daily_state', message: 'English error' } }, 422),
    })
    render(<DailyStatePanel date={TODAY} />)
    const retry = await screen.findByRole('button', { name: 'Повторить загрузку состояния' })
    fails = false; fireEvent.click(retry)
    await screen.findByText(/Состояние пока не заполнено/)
    input('Заметка дня', 'Не потерять')
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить состояние' }))
    await screen.findByText(/Проверьте состояние дня/)
    expect(screen.getByLabelText('Заметка дня')).toHaveValue('Не потерять')
    expect(screen.queryByText('English error')).not.toBeInTheDocument()
  })
})

/**
 * HabitCard — targeted tests for autosave, OK timer, and error handling.
 *
 * We fake rAF so countdown behaviour is deterministic, and stub fetch so API
 * calls succeed or fail on demand.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { DailyEntry, DayItem } from '../../api/types'
import { jsonResponse, stubApi } from '../../test/fetchStub'
import { dayItemFixture, dailyEntryFixture } from '../../test/fixtures'
import { HabitCard } from './HabitCard'

// ---------------------------------------------------------------------------
// Fake rAF
// ---------------------------------------------------------------------------

let rafCallbacks: Array<(t: number) => void> = []
let fakeTime = 0

function installFakeRaf() {
  rafCallbacks = []
  fakeTime = 0
  vi.stubGlobal('requestAnimationFrame', (cb: (t: number) => void) => {
    rafCallbacks.push(cb)
    return rafCallbacks.length
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    rafCallbacks[id - 1] = () => {}
  })
  vi.stubGlobal('performance', { now: () => fakeTime })
}

function tickRaf(time: number) {
  fakeTime = time
  const pending = [...rafCallbacks]
  rafCallbacks = []
  for (const cb of pending) cb(time)
}

afterEach(() => vi.unstubAllGlobals())

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TODAY = '2026-09-27'

function makeEntry(id = 1, status: DailyEntry['status'] = 'done'): DailyEntry {
  return dailyEntryFixture({ id, habit_id: 1, entry_date: TODAY, status })
}

function renderCard(
  itemOverrides: Partial<DayItem> = {},
  opts: { onSettled?: (id: number, e: DailyEntry | null) => void; onTimerDone?: (id: number) => void } = {},
) {
  const item = dayItemFixture({ habit_id: 1, name: 'Чтение', ...itemOverrides })
  const onSettled = opts.onSettled ?? vi.fn()
  const onTimerDone = opts.onTimerDone ?? vi.fn()
  return { onSettled, onTimerDone, ...render(
    <HabitCard
      item={item}
      entryDate={TODAY}
      isFuture={false}
      inCompletedSection={false}
      onSettled={onSettled}
      onTimerDone={onTimerDone}
    />,
  ) }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('HabitCard', () => {
  beforeEach(installFakeRaf)

  it('renders the habit name and a "—" pill when no entry', () => {
    stubApi({})
    renderCard()
    expect(screen.getByText('Чтение')).toBeInTheDocument()
    expect(screen.getByLabelText('Нет отметки')).toBeInTheDocument()
  })

  it('autosaves when a status button is clicked', async () => {
    const entry = makeEntry()
    const stub = stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(entry),
      [`GET /api/days/${TODAY}`]: () => jsonResponse({ entry_date: TODAY, today: TODAY, is_future: false, items: [] }),
    })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))

    await waitFor(() => {
      expect(stub).toHaveBeenCalledWith(
        expect.stringContaining(`/api/habits/1/entries/${TODAY}`),
        expect.objectContaining({ method: 'PUT' }),
      )
    })
  })

  it('calls onSettled with the entry after a successful save', async () => {
    const entry = makeEntry()
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(entry) })
    const { onSettled } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))

    await waitFor(() => expect(onSettled).toHaveBeenCalledWith(1, entry))
  })

  it('shows the OK button and starts the countdown after a successful save', async () => {
    const entry = makeEntry()
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(entry) })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })

    // Simulate the countdown progressing
    act(() => tickRaf(2_500))
    expect(screen.getByRole('button', { name: /ОК/ })).toBeInTheDocument()
  })

  it('calls onTimerDone when 5 seconds elapse', async () => {
    const entry = makeEntry()
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(entry) })
    const { onTimerDone } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })

    act(() => tickRaf(5_000))

    await waitFor(() => expect(onTimerDone).toHaveBeenCalledWith(1))
  })

  it('calls onTimerDone immediately when OK is clicked', async () => {
    const entry = makeEntry()
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(entry) })
    const { onTimerDone } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    const okBtn = await screen.findByRole('button', { name: /ОК/ })

    act(() => tickRaf(1_000))  // partway
    fireEvent.click(okBtn)

    expect(onTimerDone).toHaveBeenCalledWith(1)
  })

  it('does NOT start the countdown if the save request fails', async () => {
    stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () =>
        jsonResponse({ error: { code: 'server_error', message: 'Ошибка' } }, 500),
    })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))

    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: /ОК/ })).not.toBeInTheDocument()
  })

  it('shows a local error on save failure without hiding the card', async () => {
    stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () =>
        jsonResponse({ error: { code: 'server_error', message: 'Сервер недоступен' } }, 500),
    })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Сервер не смог выполнить запрос')
    // Card is still visible and actionable
    expect(screen.getByText('Чтение')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Выполнено' })).toBeInTheDocument()
  })

  it('resets the countdown when the user changes the value while counting', async () => {
    let callCount = 0
    stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () => {
        callCount++
        return jsonResponse(makeEntry(callCount))
      },
    })
    const { onTimerDone } = renderCard()

    // First save
    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })
    act(() => tickRaf(3_000))   // 3 s in

    // Change value — should reset timer
    fireEvent.click(screen.getByRole('button', { name: 'Пропущено' }))
    await screen.findByRole('button', { name: /ОК/ })

    // The old timer's tick should NOT fire onTimerDone
    act(() => tickRaf(5_000))   // would have been 5 s from first save
    expect(onTimerDone).not.toHaveBeenCalled()

    // After a full 5 s from the second save, it fires
    act(() => tickRaf(10_000))
    await waitFor(() => expect(onTimerDone).toHaveBeenCalledWith(1))
  })

  it('calls onSettled with null and clears the entry when the clear button is clicked', async () => {
    const entry = makeEntry()
    stubApi({
      [`DELETE /api/habits/1/entries/${TODAY}`]: () => ({
        ok: true, status: 204, text: async () => '',
      } as unknown as Response),
    })
    const { onSettled } = renderCard({ entry })

    fireEvent.click(screen.getByRole('button', { name: 'Убрать отметку' }))

    await waitFor(() => expect(onSettled).toHaveBeenCalledWith(1, null))
  })

  it('does not offer clear button when there is no entry', () => {
    stubApi({})
    renderCard({ entry: null })
    expect(screen.queryByRole('button', { name: 'Убрать отметку' })).not.toBeInTheDocument()
  })

  it('blocks done/missed buttons for future dates', () => {
    stubApi({})

    const item = dayItemFixture({ habit_id: 1, is_archived: false })
    render(
      <HabitCard
        item={item}
        entryDate="2099-01-01"
        isFuture={true}
        inCompletedSection={false}
        onSettled={vi.fn()}
        onTimerDone={vi.fn()}
      />,
    )

    expect(screen.getAllByRole('button', { name: 'Выполнено' })[0]).toBeDisabled()
    expect(screen.getAllByRole('button', { name: 'Пропущено' })[0]).toBeDisabled()
  })

  it('shows skip-reason input when skipped is chosen', async () => {
    stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () =>
        jsonResponse(makeEntry(1, 'skipped')),
    })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Осознанный пропуск' }))
    expect(screen.getByPlaceholderText('Причина пропуска')).toBeInTheDocument()
  })

  it('does not save a skipped entry until a reason is typed', async () => {
    const stub = stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () =>
        jsonResponse(makeEntry(1, 'skipped')),
    })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Осознанный пропуск' }))
    // Without a reason, no PUT should fire
    await new Promise((r) => setTimeout(r, 50))
    expect(stub).not.toHaveBeenCalledWith(
      expect.stringContaining('/entries/'),
      expect.anything(),
    )
  })
})

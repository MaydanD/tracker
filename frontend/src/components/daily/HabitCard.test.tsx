/**
 * HabitCard — targeted tests for autosave, OK timer, and error handling.
 *
 * We fake rAF so countdown behaviour is deterministic, and stub fetch so API
 * calls succeed or fail on demand.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { DailyEntry, DailyEntryInput, DayItem } from '../../api/types'
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

/**
 * Advance the fake clock *relative* to where it already is.
 *
 * The countdown captures its start from `performance.now()` at the moment the
 * readiness effect arms it. Jumping the clock to an absolute timestamp would
 * therefore be meaningless for a timer armed after the jump: it would start
 * counting from the jumped value, and the next fixed tick would fall short of
 * five seconds and never complete.
 */
function advanceRaf(ms: number) {
  tickRaf(fakeTime + ms)
}

afterEach(() => vi.unstubAllGlobals())

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TODAY = '2026-09-27'

function makeEntry(id = 1, status: DailyEntry['status'] = 'done'): DailyEntry {
  return dailyEntryFixture({ id, habit_id: 1, entry_date: TODAY, status })
}

/** The card's «ОК» control (rendered as soon as a value is stored). */
const okButton = () => screen.getByRole('button', { name: /ОК/ })
/**
 * The countdown is armed by a React effect, which flushes *after* the commit
 * that first puts «ОК» on screen. The button can therefore be visible (and
 * enabled) while the timer has not started yet, so tests that reason about the
 * five seconds must wait for the armed state — visible in the button's own
 * label — instead of assuming the effect has already run.
 */
const countdownArmed = () => /до автоподтверждения/.test(okButton().getAttribute('aria-label') ?? '')

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

  it('renders a day item without scale metadata as a completion habit, never as digits', () => {
    // An API that predates value scales sends no `value_type`. Such an item is a
    // completion habit: inventing a 0 / 1 / 2 / 3 scale would ask a question the
    // habit never had.
    stubApi({})
    renderCard({ value_type: undefined as unknown as null, value_labels: null, direction: null })

    expect(screen.getByRole('button', { name: 'Выполнено' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Пропущено' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '0' })).toBeNull()
    expect(screen.queryByRole('button', { name: '3' })).toBeNull()
  })

  it('saves only the newest of a rapid 1 → 2 → 3 sequence', async () => {
    const bodies: DailyEntryInput[] = []
    const releases: Array<() => void> = []
    stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: (request) => {
        const input = request.body as DailyEntryInput
        bodies.push(input)
        return new Promise<Response>((resolve) => {
          releases.push(() => resolve(jsonResponse(dailyEntryFixture({
            habit_id: 1, entry_date: TODAY, status: 'done', value: input.value ?? null,
          }))))
        }) as unknown as Response
      },
    })
    renderCard({
      value_type: 'ordinal_4',
      value_labels: ['0', 'мало', 'нормально', 'много'],
      direction: 'positive',
    })

    // Three answers chosen before any write settles: the serialized queue makes
    // the earlier ones stale, so only the last one ever reaches the server.
    fireEvent.click(screen.getByRole('button', { name: 'мало' }))
    fireEvent.click(screen.getByRole('button', { name: 'нормально' }))
    fireEvent.click(screen.getByRole('button', { name: 'много' }))
    await waitFor(() => expect(bodies.length).toBeGreaterThan(0))
    expect(bodies.at(-1)?.value).toBe(3)

    await act(async () => releases.forEach((release) => release()))
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('много'),
    )
  })

  it('keeps a value card without a value open, and treats a stored 0 as an answer', () => {
    // A row recorded before the habit became a scale says "done" but holds no
    // value: the card still needs answering, so «ОК» must not be offered.
    const unanswered = renderCard({
      value_type: 'ordinal_4',
      value_labels: ['0', 'мало', 'нормально', 'много'],
      direction: 'positive',
      entry: dailyEntryFixture({ habit_id: 1, entry_date: TODAY, value: null }),
    })
    expect(screen.queryByRole('button', { name: /ОК/ })).toBeNull()
    unanswered.unmount()

    // Zero is a real answer, so the card is filled and «ОК» is on screen.
    renderCard({
      value_type: 'ordinal_4',
      value_labels: ['0', 'мало', 'нормально', 'много'],
      direction: 'positive',
      entry: dailyEntryFixture({ habit_id: 1, entry_date: TODAY, value: 0 }),
    })
    expect(screen.getByRole('button', { name: /ОК/ })).toBeInTheDocument()
  })

  it('shows the OK button and starts the countdown after a successful save', async () => {
    const entry = makeEntry()
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(entry) })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })
    await waitFor(() => expect(countdownArmed()).toBe(true))

    // Simulate the countdown progressing
    act(() => advanceRaf(2_500))
    expect(screen.getByRole('button', { name: /ОК/ })).toBeInTheDocument()
  })

  it('calls onTimerDone when 5 seconds elapse', async () => {
    const entry = makeEntry()
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(entry) })
    const { onTimerDone } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })
    await waitFor(() => expect(countdownArmed()).toBe(true))

    act(() => advanceRaf(5_000))

    await waitFor(() => expect(onTimerDone).toHaveBeenCalledWith(1))
  })

  it('calls onTimerDone immediately when OK is clicked', async () => {
    const entry = makeEntry()
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(entry) })
    const { onTimerDone } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    const okBtn = await screen.findByRole('button', { name: /ОК/ })
    // Wait for the countdown to be armed: a click that races the arming effect
    // would have its confirmation reset by the very effect that starts it.
    await waitFor(() => expect(countdownArmed()).toBe(true))

    act(() => advanceRaf(1_000))  // partway
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
    await waitFor(() => expect(countdownArmed()).toBe(true))
    act(() => advanceRaf(3_000))   // 3 s in

    // Change value — should reset timer. The button stays on screen while the
    // new value is written, so wait for it to become confirmable *and* for the
    // fresh countdown to be armed before advancing the clock.
    fireEvent.click(screen.getByRole('button', { name: 'Пропущено' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /ОК/ })).toBeEnabled())
    await waitFor(() => expect(countdownArmed()).toBe(true))

    // Two seconds into the *new* countdown: the old timer must not have fired.
    act(() => advanceRaf(2_000))
    expect(onTimerDone).not.toHaveBeenCalled()

    // Five seconds after the second save, it fires
    act(() => advanceRaf(3_000))
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

  // -------------------------------------------------------------------------
  // Layout stability — the card must not grow a row when the habit is marked.
  // jsdom cannot measure heights, so these guard the structural cause of the
  // jump: the number of direct rows inside `.ccard` used to change on mark.
  // -------------------------------------------------------------------------

  /** The direct rows of a card, in order — the card's vertical skeleton. */
  function rows(card: HTMLElement) {
    return [...card.children].map((node) => node.className)
  }

  it('marks a habit without adding or removing a card row', async () => {
    stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(makeEntry()),
    })
    renderCard()
    const card = screen.getByRole('group', { name: 'Чтение' })
    const before = rows(card)

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })

    // The OK countdown shares the footer row instead of appending a new one.
    expect(rows(card)).toEqual(before)
    expect(screen.getByPlaceholderText('Заметка (необязательно)').parentElement)
      .toHaveClass('ccard__footer')
  })

  it('keeps the note field in place, disabled until a status is chosen', async () => {
    stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(makeEntry()),
    })
    renderCard()
    const note = screen.getByPlaceholderText('Заметка (необязательно)')
    expect(note).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))

    await waitFor(() => expect(note).toBeEnabled())
  })

  it('reveals the skip reason inside the existing footer row', () => {
    stubApi({})
    renderCard()
    const card = screen.getByRole('group', { name: 'Чтение' })
    const before = rows(card).length

    fireEvent.click(screen.getByRole('button', { name: 'Осознанный пропуск' }))

    const reason = screen.getByPlaceholderText('Причина пропуска')
    const note = screen.getByPlaceholderText('Заметка (необязательно)')
    expect(reason.parentElement).toHaveClass('ccard__footer')
    expect(reason.parentElement).toBe(note.parentElement)
    expect(rows(card)).toHaveLength(before)
  })

  it('reserves the quantity row for a quantity habit before it is marked', async () => {
    stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(makeEntry()),
    })
    renderCard({ tracking_mode: 'binary_quantity', quantity_unit: 'страниц' })
    const card = screen.getByRole('group', { name: 'Чтение' })
    const quantity = screen.getByLabelText('Количество')
    expect(quantity).toBeDisabled()
    const before = rows(card)

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))

    await waitFor(() => expect(quantity).toBeEnabled())
    expect(rows(card)).toEqual(before)
  })
})

// ---------------------------------------------------------------------------
// OK visibility vs. countdown eligibility.
//
// A field being in use may pause the automatic countdown, but it must never
// take the manual «ОК» control away: the user has to be able to confirm a
// card by hand at any moment.
// ---------------------------------------------------------------------------

describe('HabitCard — «ОК» stays while a field is in use', () => {
  beforeEach(installFakeRaf)

  /** The card element for the default «Чтение» habit. */
  const card = () => screen.getByRole('group', { name: 'Чтение' })
  const okButton = () => screen.getByRole('button', { name: /ОК/ })
  const note = () => screen.getByPlaceholderText('Заметка (необязательно)')
  const counting = () => card().classList.contains('ccard--counting')

  function stubOneSave() {
    let calls = 0
    const stub = stubApi({
      [`PUT /api/habits/1/entries/${TODAY}`]: () => {
        calls += 1
        return jsonResponse(makeEntry(calls))
      },
    })
    return { stub, calls: () => calls }
  }

  it('offers «ОК» as soon as the status is stored', async () => {
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(makeEntry()) })
    renderCard()

    expect(screen.queryByRole('button', { name: /ОК/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))

    expect(await screen.findByRole('button', { name: /ОК/ })).toBeInTheDocument()
  })

  it('keeps «ОК» when the note field takes focus', async () => {
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(makeEntry()) })
    renderCard()
    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })

    fireEvent.focus(note())

    expect(okButton()).toBeInTheDocument()
  })

  it('keeps the same «ОК» node while the user types a note', async () => {
    const { calls } = stubOneSave()
    renderCard()
    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await waitFor(() => expect(okButton()).toBeEnabled())
    const button = okButton()

    const field = note()
    fireEvent.focus(field)
    fireEvent.change(field, { target: { value: 'прочитал главу' } })
    await waitFor(() => expect(calls()).toBe(2))

    // The keystroke's autosave settles: the very same node is still there and
    // becomes confirmable again, while the field keeps the typed text.
    expect(okButton()).toBe(button)
    await waitFor(() => expect(okButton()).toBeEnabled())
    expect(field).toHaveValue('прочитал главу')
    expect(counting()).toBe(false)
  })

  it('does not count down while the note is in use and starts once focus leaves', async () => {
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(makeEntry()) })
    const { onTimerDone } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    // Focus the field before the first save settles, so no countdown ever arms.
    fireEvent.focus(note())
    await screen.findByRole('button', { name: /ОК/ })

    act(() => advanceRaf(5_000))
    expect(counting()).toBe(false)
    expect(onTimerDone).not.toHaveBeenCalled()

    fireEvent.blur(note(), { relatedTarget: null })
    await waitFor(() => expect(counting()).toBe(true))
    act(() => advanceRaf(5_000))
    await waitFor(() => expect(onTimerDone).toHaveBeenCalledWith(1))
  })

  it('cancels a running countdown when the user returns to the note, keeping «ОК»', async () => {
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(makeEntry()) })
    const { onTimerDone } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })
    await waitFor(() => expect(counting()).toBe(true))
    act(() => advanceRaf(3_000))

    fireEvent.focus(note())

    expect(counting()).toBe(false)
    expect(okButton()).toBeInTheDocument()
    act(() => advanceRaf(10_000))
    expect(onTimerDone).not.toHaveBeenCalled()
  })

  it('confirms by hand with «ОК» when a note is already filled and in focus', async () => {
    const { calls } = stubOneSave()
    const { onTimerDone } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })
    const field = note()
    fireEvent.focus(field)
    fireEvent.change(field, { target: { value: 'заметка' } })
    await waitFor(() => expect(calls()).toBe(2))
    // Confirming becomes possible again only once the new value is stored.
    await waitFor(() => expect(okButton()).toBeEnabled())

    fireEvent.click(okButton())

    expect(onTimerDone).toHaveBeenCalledWith(1)
  })

  it('keeps a hand-confirm when the readiness effect runs afterwards', async () => {
    // The «ОК» button is on screen (and enabled) before the effect that arms the
    // countdown has flushed. A click in that window must win: the pending
    // effect must not reset the card back out of its completed state.
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(makeEntry()) })
    const { onTimerDone } = renderCard()

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    const ok = await screen.findByRole('button', { name: /ОК/ })
    await waitFor(() => expect(ok).toBeEnabled())
    await waitFor(() => expect(counting()).toBe(true))

    // A field is in use, so the countdown is paused — the user confirms anyway.
    fireEvent.focus(note())
    fireEvent.click(ok)
    expect(onTimerDone).toHaveBeenCalledTimes(1)

    // Leaving the field re-runs the arming effect for the same revision; a
    // re-armed countdown would complete a second time right here.
    fireEvent.blur(note(), { relatedTarget: null })
    act(() => advanceRaf(10_000))

    expect(onTimerDone).toHaveBeenCalledTimes(1)
    expect(counting()).toBe(false)
  })

  it('keeps «ОК» through lock and unlock, even with the note in focus', async () => {
    stubApi({ [`PUT /api/habits/1/entries/${TODAY}`]: () => jsonResponse(makeEntry()) })
    renderCard()
    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })
    fireEvent.focus(note())

    fireEvent.click(screen.getByRole('button', { name: 'Закрыть замок — оставить карточку' }))
    expect(okButton()).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Открыть замок — запустить отсчёт' }))
    expect(okButton()).toBeInTheDocument()
  })

  it('keeps «ОК» while a quantity habit\u2019s number field is in use', async () => {
    const { calls } = stubOneSave()
    renderCard({ tracking_mode: 'binary_quantity', quantity_unit: 'страниц' })

    fireEvent.click(screen.getByRole('button', { name: 'Выполнено' }))
    await screen.findByRole('button', { name: /ОК/ })
    const quantity = screen.getByLabelText('Количество')

    fireEvent.focus(quantity)
    fireEvent.change(quantity, { target: { value: '12' } })
    await waitFor(() => expect(calls()).toBe(2))

    expect(await screen.findByRole('button', { name: /ОК/ })).toBeInTheDocument()
    expect(quantity).toHaveValue(12)
    expect(counting()).toBe(false)
  })
})

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { DailyEntry } from '../api/types'
import { addDays, localTodayIso } from '../components/daily/dates'
import { jsonResponse, stubApi } from '../test/fetchStub'
import { createFakeApi, stubFakeApi } from '../test/fakeApi'
import { areaFixture, habitFixture } from '../test/fixtures'
import { progressFixture } from '../test/progressFixture'
import { CheckInPage } from './CheckInPage'

const TODAY = localTodayIso()
const YESTERDAY = addDays(TODAY, -1)
const TOMORROW = addDays(TODAY, 1)

const health = areaFixture({ id: 1, name: 'Health', color: '#2f9e5f' })

function binaryHabit(overrides: Record<string, unknown> = {}) {
  return habitFixture({
    id: 1,
    name: 'Reading',
    area_id: 1,
    area: { id: 1, name: 'Health', color: '#2f9e5f', is_archived: false },
    current_version: {
      version_number: 1,
      effective_from: addDays(TODAY, -30),
      created_at: '2026-09-01T10:00:00',
    },
    ...overrides,
  })
}

function quantityHabit() {
  return binaryHabit({
    id: 2,
    name: 'Walking',
    tracking_mode: 'binary_quantity',
    quantity_unit: 'km',
    quantity_allows_decimal: true,
  })
}

function entryFixture(overrides: Partial<DailyEntry> = {}): DailyEntry {
  return {
    id: 1,
    habit_id: 1,
    entry_date: TODAY,
    status: 'skipped',
    quantity_value: null,
    quantity_unit: null,
    skip_reason: 'Отпуск',
    note: null,
    created_at: '2026-09-20T10:00:00',
    updated_at: '2026-09-20T10:00:00',
    ...overrides,
  }
}

/** A day payload with one binary habit, as the API returns it. */
function dayPayload(entryDate: string, isFuture: boolean) {
  return {
    entry_date: entryDate,
    today: TODAY,
    is_future: isFuture,
    items: [
      {
        habit_id: 1,
        name: 'Reading',
        area: { id: 1, name: 'Health', color: '#2f9e5f', is_archived: false },
        weight: 1,
        tracking_mode: 'binary',
        quantity_unit: null,
        quantity_allows_decimal: false,
        schedule: {
          type: 'daily',
          weekdays: [],
          times_per_week: null,
          weekly_required_count: 7,
          summary: 'Every day',
        },
        is_archived: false,
        entry: null,
      },
    ],
  }
}

/** A response whose body is only released when the test says so. */
function stalledResponse(body: unknown): { response: Response; release: () => void } {
  let release: () => void = () => undefined
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  return {
    response: {
      ok: true,
      status: 200,
      text: async () => {
        await gate
        return JSON.stringify(body)
      },
    } as unknown as Response,
    release,
  }
}

/** The row for one habit, so assertions stay scoped to it. */
function row(name: string): HTMLElement {
  const item = screen.getByText(name).closest('li')
  if (item === null) throw new Error(`No row for ${name}`)
  return item
}

/**
 * The recorded state of a habit — the `role="status"` badge, not the buttons,
 * which deliberately carry the same words as the states they set.
 */
function stateOf(name: string): HTMLElement {
  return within(row(name)).getByRole('status')
}

function chooseStatus(name: string, label: string): void {
  fireEvent.click(within(row(name)).getByRole('button', { name: label }))
}

function save(name: string): void {
  fireEvent.click(within(row(name)).getByRole('button', { name: 'Сохранить' }))
}

async function waitForHabits(...names: string[]): Promise<void> {
  for (const name of names) {
    await screen.findByText(name)
  }
}

describe('CheckInPage', () => {
  it('is written in Russian and explains what the states mean', async () => {
    stubFakeApi(createFakeApi({ areas: [health], habits: [binaryHabit()] }))

    render(<CheckInPage />)

    expect(await screen.findByRole('heading', { name: 'Итоги дня' })).toBeInTheDocument()
    expect(screen.getByText(/Отсутствие отметки не превращается в пропуск/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Выполнено' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Пропущено' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Осознанный пропуск' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '← Предыдущий день' })).toBeInTheDocument()
    expect(screen.getByLabelText('Дата')).toBeInTheDocument()
  })

  it('shows «Нет отметки» for a day with nothing recorded', async () => {
    const api = createFakeApi({ areas: [health], habits: [binaryHabit()] })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')

    expect(stateOf('Reading')).toHaveTextContent('Нет отметки')
    expect(stateOf('Reading')).not.toHaveTextContent('Пропущено')
    expect(api.entries).toHaveLength(0)
  })

  it('marks a habit done, replacing «Нет отметки» with «Выполнено»', async () => {
    const api = createFakeApi({ areas: [health], habits: [binaryHabit()] })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')

    chooseStatus('Reading', 'Выполнено')
    save('Reading')

    await waitFor(() => expect(api.entries).toHaveLength(1))
    expect(api.entries[0]?.status).toBe('done')
    expect(api.entries[0]?.entry_date).toBe(TODAY)
    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Выполнено'))
    expect(stateOf('Reading')).not.toHaveTextContent('Нет отметки')
  })

  it('keeps «Пропущено» distinct from an unrecorded day', async () => {
    const api = createFakeApi({ areas: [health], habits: [binaryHabit()] })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')

    chooseStatus('Reading', 'Пропущено')
    save('Reading')

    await waitFor(() => expect(api.entries[0]?.status).toBe('missed'))
    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Пропущено'))
    expect(stateOf('Reading')).not.toHaveTextContent('Нет отметки')
  })

  it('edits the status of an existing record', async () => {
    const api = createFakeApi({ areas: [health], habits: [binaryHabit()] })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')
    chooseStatus('Reading', 'Выполнено')
    save('Reading')
    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Выполнено'))

    chooseStatus('Reading', 'Пропущено')
    save('Reading')

    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Пропущено'))
    expect(api.entries).toHaveLength(1)
    expect(api.entries[0]?.status).toBe('missed')
  })

  it('offers a quantity field and the unit only for quantity habits', async () => {
    const api = createFakeApi({
      areas: [health],
      habits: [binaryHabit(), quantityHabit()],
    })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading', 'Walking')

    // No state chosen yet, so there is nothing to fill in.
    expect(screen.queryByLabelText('Количество')).toBeNull()

    // A binary habit never offers a quantity.
    chooseStatus('Reading', 'Выполнено')
    expect(within(row('Reading')).queryByLabelText('Количество')).toBeNull()

    chooseStatus('Walking', 'Выполнено')
    const quantity = within(row('Walking')).getByLabelText('Количество')
    expect(screen.getByText(/Единица измерения на эту дату: km/)).toBeInTheDocument()

    fireEvent.change(quantity, { target: { value: '6.4' } })
    save('Walking')

    await waitFor(() => expect(api.entries).toHaveLength(1))
    expect(api.entries[0]?.quantity_value).toBe(6.4)
    expect(api.entries[0]?.quantity_unit).toBe('km')
    await waitFor(() => expect(stateOf('Walking')).toHaveTextContent('6.4 km'))
  })

  it('requires a whole number when the habit forbids decimals', async () => {
    const api = createFakeApi({
      areas: [health],
      habits: [binaryHabit({ tracking_mode: 'binary_quantity', quantity_unit: 'pages' })],
    })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')
    chooseStatus('Reading', 'Выполнено')
    fireEvent.change(within(row('Reading')).getByLabelText('Количество'), {
      target: { value: '6.4' },
    })
    save('Reading')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Для этой привычки допустимы только целые значения.',
    )
    expect(api.entries).toHaveLength(0)
  })

  it('asks for a skip reason and keeps it separate from the note', async () => {
    const api = createFakeApi({ areas: [health], habits: [binaryHabit()] })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')

    chooseStatus('Reading', 'Осознанный пропуск')
    expect(within(row('Reading')).getByLabelText('Причина пропуска')).toBeInTheDocument()

    save('Reading')
    expect(await screen.findByRole('alert')).toHaveTextContent('Укажите причину пропуска.')
    expect(api.entries).toHaveLength(0)

    fireEvent.change(within(row('Reading')).getByLabelText('Причина пропуска'), {
      target: { value: 'Отпуск' },
    })
    fireEvent.change(within(row('Reading')).getByLabelText('Заметка (необязательно)'), {
      target: { value: 'вернулся поздно' },
    })
    save('Reading')

    await waitFor(() => expect(api.entries).toHaveLength(1))
    expect(api.entries[0]?.status).toBe('skipped')
    expect(api.entries[0]?.skip_reason).toBe('Отпуск')
    expect(api.entries[0]?.note).toBe('вернулся поздно')
    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Причина: Отпуск'))
    expect(stateOf('Reading')).toHaveTextContent('вернулся поздно')
  })

  it('hides the skip reason field for a non-skipped status', async () => {
    stubFakeApi(createFakeApi({ areas: [health], habits: [binaryHabit()] }))

    render(<CheckInPage />)
    await waitForHabits('Reading')

    chooseStatus('Reading', 'Осознанный пропуск')
    expect(screen.getByLabelText('Причина пропуска')).toBeInTheDocument()

    chooseStatus('Reading', 'Выполнено')
    expect(screen.queryByLabelText('Причина пропуска')).toBeNull()
  })

  it('edits a note on its own', async () => {
    const api = createFakeApi({ areas: [health], habits: [binaryHabit()] })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')
    chooseStatus('Reading', 'Выполнено')

    fireEvent.change(within(row('Reading')).getByLabelText('Заметка (необязательно)'), {
      target: { value: 'тяжело пошло' },
    })
    save('Reading')

    await waitFor(() => expect(api.entries[0]?.note).toBe('тяжело пошло'))
    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('тяжело пошло'))

    // Saving without the note clears it.
    fireEvent.change(within(row('Reading')).getByLabelText('Заметка (необязательно)'), {
      target: { value: '' },
    })
    save('Reading')

    await waitFor(() => expect(api.entries[0]?.note).toBeNull())
    await waitFor(() => expect(stateOf('Reading')).not.toHaveTextContent('тяжело пошло'))
  })

  it('clears a record back to «Нет отметки» instead of a miss', async () => {
    const api = createFakeApi({ areas: [health], habits: [binaryHabit()] })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')
    chooseStatus('Reading', 'Выполнено')
    save('Reading')
    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Выполнено'))

    fireEvent.click(within(row('Reading')).getByRole('button', { name: 'Очистить' }))

    await waitFor(() => expect(api.entries).toHaveLength(0))
    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Нет отметки'))
    // Clearing must not turn the day into a miss.
    expect(stateOf('Reading')).not.toHaveTextContent('Пропущено')
  })

  it('navigates to previous and next days and picks a date', async () => {
    stubFakeApi(createFakeApi({ areas: [health], habits: [binaryHabit()] }))

    render(<CheckInPage />)
    await waitForHabits('Reading')
    expect(screen.getByLabelText('Дата')).toHaveValue(TODAY)

    fireEvent.click(screen.getByRole('button', { name: '← Предыдущий день' }))
    await waitFor(() => expect(screen.getByLabelText('Дата')).toHaveValue(YESTERDAY))
    expect(screen.getByText('Вчера')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Следующий день →' }))
    await waitFor(() => expect(screen.getByLabelText('Дата')).toHaveValue(TODAY))

    fireEvent.click(screen.getByRole('button', { name: 'Следующий день →' }))
    await waitFor(() => expect(screen.getByLabelText('Дата')).toHaveValue(TOMORROW))
    expect(screen.getByText('Завтра')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Дата'), { target: { value: YESTERDAY } })
    await waitFor(() => expect(screen.getByLabelText('Дата')).toHaveValue(YESTERDAY))

    fireEvent.click(screen.getByRole('button', { name: 'Сегодня' }))
    await waitFor(() => expect(screen.getByLabelText('Дата')).toHaveValue(TODAY))
  })

  it('records a past day', async () => {
    const api = createFakeApi({ areas: [health], habits: [binaryHabit()] })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')

    fireEvent.click(screen.getByRole('button', { name: '← Предыдущий день' }))
    await waitFor(() => expect(screen.getByLabelText('Дата')).toHaveValue(YESTERDAY))

    chooseStatus('Reading', 'Пропущено')
    save('Reading')

    await waitFor(() => expect(api.entries).toHaveLength(1))
    expect(api.entries[0]?.entry_date).toBe(YESTERDAY)
    expect(api.entries[0]?.status).toBe('missed')
  })

  it('offers only a planned skip on a future day', async () => {
    const api = createFakeApi({ areas: [health], habits: [binaryHabit()] })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')
    fireEvent.click(screen.getByRole('button', { name: 'Следующий день →' }))

    expect(await screen.findByText(/Будущий день/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Дата')).toHaveValue(TOMORROW))

    expect(screen.getByRole('button', { name: 'Выполнено' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Пропущено' })).toBeDisabled()
    const plannedSkip = screen.getByRole('button', { name: 'Запланировать пропуск' })
    expect(plannedSkip).toBeEnabled()

    fireEvent.click(plannedSkip)
    fireEvent.change(within(row('Reading')).getByLabelText('Причина пропуска'), {
      target: { value: 'Отпуск' },
    })
    save('Reading')

    await waitFor(() => expect(api.entries).toHaveLength(1))
    expect(api.entries[0]?.entry_date).toBe(TOMORROW)
    expect(api.entries[0]?.status).toBe('skipped')
    expect(api.entries[0]?.skip_reason).toBe('Отпуск')
  })

  it('lets an existing future planned skip be changed and removed', async () => {
    const api = createFakeApi({
      areas: [health],
      habits: [binaryHabit()],
      entries: [entryFixture({ entry_date: TOMORROW })],
    })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')
    fireEvent.click(screen.getByRole('button', { name: 'Следующий день →' }))

    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Причина: Отпуск'))

    fireEvent.change(within(row('Reading')).getByLabelText('Причина пропуска'), {
      target: { value: 'Поездка' },
    })
    save('Reading')

    await waitFor(() => expect(api.entries[0]?.skip_reason).toBe('Поездка'))
    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Причина: Поездка'))

    fireEvent.click(within(row('Reading')).getByRole('button', { name: 'Очистить' }))

    await waitFor(() => expect(api.entries).toHaveLength(0))
    await waitFor(() => expect(stateOf('Reading')).toHaveTextContent('Нет отметки'))
  })

  it('shows the schedule as information without acting on it', async () => {
    stubFakeApi(
      createFakeApi({
        areas: [health],
        habits: [
          binaryHabit({
            schedule: {
              type: 'weekdays',
              weekdays: [0, 2, 4],
              times_per_week: null,
              weekly_required_count: 3,
              summary: 'Mon, Wed, Fri (3 per week)',
            },
          }),
        ],
      }),
    )

    render(<CheckInPage />)

    expect(await screen.findByText('Пн, Ср, Пт (3 раза в неделю)')).toBeInTheDocument()
  })

  it('keeps an archived habit’s recorded day editable', async () => {
    const api = createFakeApi({
      areas: [health],
      habits: [
        binaryHabit({
          id: 1,
          name: 'Reading',
          is_archived: true,
          archived_at: '2026-09-20T10:00:00',
        }),
      ],
      entries: [entryFixture({ status: 'done', skip_reason: null, note: 'до архива' })],
    })
    stubFakeApi(api)

    render(<CheckInPage />)
    await waitForHabits('Reading')

    expect(await screen.findByText('до архива')).toBeInTheDocument()
    expect(screen.getByText('В архиве')).toBeInTheDocument()

    chooseStatus('Reading', 'Пропущено')
    save('Reading')

    await waitFor(() => expect(api.entries[0]?.status).toBe('missed'))
  })

  it('shows the server’s rejection in Russian', async () => {
    stubApi({
      [`GET /api/progress/days/${TODAY}`]: () => jsonResponse(progressFixture(TODAY)),
      [`GET /api/days/${TODAY}`]: () =>
        jsonResponse({
          entry_date: TODAY,
          today: TODAY,
          is_future: false,
          items: [
            {
              habit_id: 1,
              name: 'Reading',
              area: { id: 1, name: 'Health', color: '#2f9e5f', is_archived: false },
              weight: 1,
              tracking_mode: 'binary_quantity',
              quantity_unit: 'pages',
              quantity_allows_decimal: false,
              schedule: {
                type: 'daily',
                weekdays: [],
                times_per_week: null,
                weekly_required_count: 7,
                summary: 'Every day',
              },
              is_archived: false,
              entry: null,
            },
          ],
        }),
      [`PUT /api/habits/1/entries/${TODAY}`]: () =>
        jsonResponse(
          {
            error: {
              code: 'quantity_decimal_not_allowed',
              message: 'This habit is configured for whole numbers only.',
            },
          },
          422,
        ),
    })

    render(<CheckInPage />)
    await waitForHabits('Reading')
    chooseStatus('Reading', 'Выполнено')

    // The client accepts the value; the server is the authority and refuses it.
    fireEvent.change(within(row('Reading')).getByLabelText('Количество'), {
      target: { value: '35' },
    })
    save('Reading')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Для этой привычки допустимы только целые значения.',
    )
  })

  it('never shows one day’s controls under another day’s date', async () => {
    const tomorrow = stalledResponse(dayPayload(TOMORROW, true))
    stubApi({
      [`GET /api/progress/days/${TODAY}`]: () => jsonResponse(progressFixture(TODAY)),
      [`GET /api/progress/days/${TOMORROW}`]: () => jsonResponse(progressFixture(TOMORROW)),
      [`GET /api/days/${TODAY}`]: () => jsonResponse(dayPayload(TODAY, false)),
      [`GET /api/days/${TOMORROW}`]: () => tomorrow.response,
    })

    render(<CheckInPage />)
    await waitForHabits('Reading')

    fireEvent.click(screen.getByRole('button', { name: 'Следующий день →' }))

    // The navigator has moved on but tomorrow has not answered: today's rows and
    // today's enabled actions must not stand in for it.
    await waitFor(() => expect(screen.getByLabelText('Дата')).toHaveValue(TOMORROW))
    expect(screen.queryByText('Reading')).toBeNull()
    expect(screen.getByText(/Загрузка отметок/)).toBeInTheDocument()

    tomorrow.release()

    await waitForHabits('Reading')
    expect(screen.getByRole('button', { name: 'Выполнено' })).toBeDisabled()
  })

  it('explains a date with no habits at all', async () => {
    stubFakeApi(createFakeApi({ areas: [health], habits: [binaryHabit()] }))

    render(<CheckInPage />)
    await waitForHabits('Reading')

    fireEvent.change(screen.getByLabelText('Дата'), {
      target: { value: addDays(TODAY, -60) },
    })

    expect(await screen.findByText(/На эту дату ещё нет привычек/)).toBeInTheDocument()
  })
})

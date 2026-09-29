import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { addDays, localTodayIso } from '../components/daily/dates'
import { jsonResponse, stubApi } from '../test/fetchStub'
import { createFakeApi, stubFakeApi } from '../test/fakeApi'
import { canonicalAreas, canonicalHabits, canonicalHabitId } from '../test/canonicalFixtures'
import { progressFixture } from '../test/progressFixture'
import { CheckInPage } from './CheckInPage'

const TODAY = localTodayIso()
const YESTERDAY = addDays(TODAY, -1)
const TOMORROW = addDays(TODAY, 1)

/** The row for one habit, so assertions stay scoped to it. */
function row(name: string): HTMLElement {
  const card = screen.getByText(name).closest<HTMLElement>('.ccard')
  if (card === null) throw new Error(`No card for ${name}`)
  return card
}

function sphere(name: string): HTMLElement {
  return screen.getByRole('region', { name })
}

/** The shipped set, as a fake API serves it. */
function shippedApi() {
  return createFakeApi({ areas: canonicalAreas(), habits: canonicalHabits() })
}

describe('CheckInPage — the day’s habits', () => {
  it('shows the 24 shipped habits grouped into the four spheres', async () => {
    stubFakeApi(shippedApi())

    const { container } = render(<CheckInPage />)
    await screen.findByText('Прогулка')

    expect(sphere('Тело')).toBeInTheDocument()
    expect(sphere('Развитие')).toBeInTheDocument()
    expect(sphere('Досуг')).toBeInTheDocument()
    expect(sphere('Питание')).toBeInTheDocument()

    // Every sphere holds exactly its own habits, in the order they arrived in.
    expect(within(sphere('Тело')).getByText('Зарядка')).toBeInTheDocument()
    expect(within(sphere('Тело')).getByText('Прогулка')).toBeInTheDocument()
    expect(within(sphere('Тело')).getByText('Настроение')).toBeInTheDocument()
    expect(within(sphere('Тело')).getByText('Секс')).toBeInTheDocument()
    expect(within(sphere('Тело')).queryByText('Чтение')).toBeNull()
    expect(within(sphere('Развитие')).getByText('Чтение')).toBeInTheDocument()
    expect(within(sphere('Развитие')).getByText('Работа')).toBeInTheDocument()
    expect(within(sphere('Досуг')).getByText('Игры')).toBeInTheDocument()
    expect(within(sphere('Питание')).getByText('Кофе')).toBeInTheDocument()
    expect(within(sphere('Питание')).getByText('Алкоголь')).toBeInTheDocument()

    expect(container.querySelectorAll('.ccard[data-habit-id]')).toHaveLength(24)
  })

  it('uses нет/да for a two-value habit and four labels for a four-value one', async () => {
    stubFakeApi(shippedApi())
    render(<CheckInPage />)
    await screen.findByText('Прогулка')

    // Two values: two options, and no completion buttons at all.
    const exercise = row('Зарядка')
    expect(within(exercise).getByRole('button', { name: 'нет' })).toBeInTheDocument()
    expect(within(exercise).getByRole('button', { name: 'да' })).toBeInTheDocument()
    expect(within(exercise).queryByRole('button', { name: /Выполнено/ })).toBeNull()
    expect(within(exercise).queryByRole('button', { name: 'Пропуск' })).toBeNull()

    // Four values, whose words are the habit's own configuration.
    for (const label of ['ужас', 'плохо', 'норм', 'хорошо']) {
      expect(within(row('Настроение')).getByRole('button', { name: label })).toBeInTheDocument()
    }
    expect(within(row('Симптомы заболевания')).getByRole('button', { name: 'сильные' })).toBeInTheDocument()
    expect(within(row('Кофе')).getByRole('button', { name: '3+ кофе' })).toBeInTheDocument()
  })

  it('autosaves a chosen value', async () => {
    const api = shippedApi()
    stubFakeApi(api)
    render(<CheckInPage />)
    await screen.findByText('Прогулка')

    fireEvent.click(within(row('Настроение')).getByRole('button', { name: 'хорошо' }))

    await waitFor(() => expect(api.entries).toHaveLength(1))
    expect(api.entries[0]!.value).toBe(3)
    expect(api.entries[0]!.status).toBe('done')
    expect(api.entries[0]!.entry_date).toBe(TODAY)
    await waitFor(() =>
      expect(within(row('Настроение')).getByRole('status')).toHaveTextContent('хорошо'),
    )
  })

  it('persists a recorded 0 and keeps it distinct from «Нет отметки»', async () => {
    const api = shippedApi()
    stubFakeApi(api)
    render(<CheckInPage />)
    await screen.findByText('Прогулка')

    // «0» is the first position of the four-value scale.
    fireEvent.click(within(row('Прогулка')).getByRole('button', { name: '0' }))

    await waitFor(() => expect(api.entries).toHaveLength(1))
    expect(api.entries[0]!.value).toBe(0)
    await waitFor(() =>
      expect(within(row('Прогулка')).getByRole('status')).toHaveTextContent('0'),
    )
    expect(within(row('Прогулка')).getByRole('status')).not.toHaveTextContent('Нет отметки')
    expect(within(row('Алкоголь')).getByRole('status')).toHaveTextContent('Нет отметки')
  })

  it('autosaves an optional comment without affecting the value', async () => {
    const api = shippedApi()
    stubFakeApi(api)
    render(<CheckInPage />)
    await screen.findByText('Прогулка')

    fireEvent.click(within(row('Прогулка')).getByRole('button', { name: 'нормально' }))
    await waitFor(() => expect(api.entries).toHaveLength(1))
    const note = within(row('Прогулка')).getByLabelText('Заметка (необязательно)')
    fireEvent.change(note, { target: { value: 'с утра' } })

    await waitFor(() => expect(api.entries[0]!.note).toBe('с утра'))
    expect(api.entries[0]!.value).toBe(2)
  })

  it('clears an answer back to «Нет отметки»', async () => {
    const api = shippedApi()
    stubFakeApi(api)
    render(<CheckInPage />)
    await screen.findByText('Прогулка')

    fireEvent.click(within(row('Прогулка')).getByRole('button', { name: 'мало' }))
    await waitFor(() => expect(api.entries).toHaveLength(1))

    fireEvent.click(within(row('Прогулка')).getByRole('button', { name: 'Убрать отметку' }))

    await waitFor(() => expect(api.entries).toHaveLength(0))
    await waitFor(() =>
      expect(within(row('Прогулка')).getByRole('status')).toHaveTextContent('Нет отметки'),
    )
  })

  it('disables answering on a future day', async () => {
    stubFakeApi(shippedApi())
    render(<CheckInPage />)
    await screen.findByText('Прогулка')

    fireEvent.click(screen.getByRole('button', { name: 'Следующий день' }))
    await waitFor(() => expect(screen.getByLabelText('Выбрать дату')).toHaveValue(TOMORROW))

    expect(await screen.findByText(/Будущий день/)).toBeInTheDocument()
    expect(within(row('Прогулка')).getByRole('button', { name: 'мало' })).toBeDisabled()
  })

  it('navigates to previous and next days and picks a date', async () => {
    stubFakeApi(shippedApi())
    render(<CheckInPage />)
    await screen.findByText('Прогулка')
    expect(screen.getByLabelText('Выбрать дату')).toHaveValue(TODAY)

    fireEvent.click(screen.getByRole('button', { name: 'Предыдущий день' }))
    await waitFor(() => expect(screen.getByLabelText('Выбрать дату')).toHaveValue(YESTERDAY))
    expect(screen.getByText('Вчера')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Сегодня' }))
    await waitFor(() => expect(screen.getByLabelText('Выбрать дату')).toHaveValue(TODAY))
  })

  it('explains a date with no habits', async () => {
    stubApi({
      [`GET /api/days/${TODAY}`]: () =>
        jsonResponse({ entry_date: TODAY, today: TODAY, is_future: false, items: [] }),
      [`GET /api/progress/days/${TODAY}`]: () => jsonResponse(progressFixture(TODAY)),
    })
    render(<CheckInPage />)

    expect(await screen.findByText(/привычек ещё нет/)).toBeInTheDocument()
  })

  it('offers a Russian retry when the derived score fails', async () => {
    let fails = true
    const api = shippedApi()
    stubApi(
      {
        [`GET /api/progress/days/${TODAY}`]: () =>
          fails
            ? jsonResponse({ error: { code: 'internal_error', message: 'Internal error' } }, 500)
            : jsonResponse({ ...progressFixture(TODAY), day: { ...progressFixture(TODAY).day, score: 40 } }),
      },
      { fallback: api.handle },
    )
    render(<CheckInPage />)
    await screen.findByText('Прогулка')

    const retry = await screen.findByRole('button', { name: 'Повторить расчёт' })
    expect(screen.queryByText('Internal error')).not.toBeInTheDocument()
    fails = false
    fireEvent.click(retry)
    expect(await screen.findByText('40%')).toBeInTheDocument()
  })

  it('shows recorded values with their configured label, including zero', async () => {
    const api = shippedApi()
    const habits = api.habits
    api.entries.push(
      entryFor(habits, 'body.mood', 3),
      entryFor(habits, 'nutrition.alcohol', 0),
    )
    stubFakeApi(api)
    render(<CheckInPage />)
    await screen.findByText('Настроение')

    await waitFor(() =>
      expect(within(row('Настроение')).getByRole('status')).toHaveTextContent('хорошо'),
    )
    // A recorded alcohol 0 shows as a value, not as missing.
    expect(within(row('Алкоголь')).getByRole('status')).toHaveTextContent('0')
  })
})

/** A stored answer for one shipped habit, as the API would return it. */
function entryFor(habits: { id: number; key: string | null }[], key: string, value: number) {
  const habit = habits.find((row) => row.key === key)!
  return {
    id: canonicalHabitId(key) * 10,
    habit_id: habit.id,
    entry_date: TODAY,
    status: 'done' as const,
    value,
    quantity_value: null,
    quantity_unit: null,
    skip_reason: null,
    note: null,
    created_at: '2026-09-28T10:00:00',
    updated_at: '2026-09-28T10:00:00',
  }
}

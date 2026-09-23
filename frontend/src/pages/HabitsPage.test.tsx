import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { jsonResponse, stubApi } from '../test/fetchStub'
import { createFakeApi, stubFakeApi } from '../test/fakeApi'
import { areaFixture, habitFixture } from '../test/fixtures'
import { HabitsPage } from './HabitsPage'

const health = areaFixture({ id: 1, name: 'Health', color: '#2f9e5f' })
const development = areaFixture({ id: 2, name: 'Development', color: '#4a7cc7' })

// Radio labels include their hint text, so match on the start of the label.
const BINARY = /^Отметка выполнения/
const QUANTITY = /^Отметка и количество/
const WEEKDAYS = /^По дням недели/
const TIMES_PER_WEEK = /^Несколько раз в неделю/

async function openCreateForm(): Promise<void> {
  fireEvent.click(screen.getByRole('button', { name: 'Новая привычка' }))
  await screen.findByLabelText('Название')
}

function chooseArea(areaId: number): void {
  fireEvent.change(screen.getByLabelText('Сфера'), { target: { value: String(areaId) } })
}

function chooseSchedule(label: RegExp): void {
  fireEvent.click(screen.getByLabelText(label))
}

describe('HabitsPage', () => {
  it('shows server field validation in Russian and preserves the draft', async () => {
    stubApi({
      'GET /api/areas': () => jsonResponse([health]),
      'GET /api/habits': () => jsonResponse([]),
      'POST /api/habits': () => jsonResponse({ error: {
        code: 'validation_error', message: 'The request payload is invalid.',
        details: { errors: [{ loc: ['body', 'quantity_unit'], type: 'string_too_long',
          msg: 'String should have at most 32 characters', ctx: { max_length: 32 } }] },
      } }, 422),
    })
    render(<HabitsPage />)
    await openCreateForm()
    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Чтение' } })
    chooseArea(1)
    chooseSchedule(QUANTITY)
    fireEvent.change(screen.getByLabelText('Единица измерения'), { target: { value: 'страницы' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать привычку' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Проверьте заполненные поля. Единица измерения: не более 32 символов.',
    )
    expect(screen.getByLabelText('Название')).toHaveValue('Чтение')
    expect(screen.getByLabelText('Единица измерения')).toHaveValue('страницы')
  })

  it('lists habits grouped by area with weight, tracking and schedule', async () => {
    const api = createFakeApi({
      areas: [health, development],
      habits: [
        habitFixture({
          id: 1,
          name: 'Reading',
          area: { id: 2, name: 'Development', color: '#4a7cc7', is_archived: false },
          area_id: 2,
          weight: 2,
          tracking_mode: 'binary_quantity',
          quantity_unit: 'pages',
          schedule: {
            type: 'weekdays',
            weekdays: [0, 2, 4],
            times_per_week: null,
            weekly_required_count: 3,
            summary: 'Mon, Wed, Fri (3 per week)',
          },
        }),
        habitFixture({
          id: 2,
          name: 'Exercise',
          area: { id: 1, name: 'Health', color: '#2f9e5f', is_archived: false },
        }),
      ],
    })
    stubFakeApi(api)

    render(<HabitsPage />)

    expect(await screen.findByText('Reading')).toBeInTheDocument()
    expect(screen.getByText('Exercise')).toBeInTheDocument()
    expect(screen.getByText('Важность 2 · Важная')).toBeInTheDocument()
    expect(screen.getByText('Количество (pages)')).toBeInTheDocument()
    expect(screen.getByText('Пн, Ср, Пт (3 раза в неделю)')).toBeInTheDocument()
    expect(screen.getAllByText(/Версия 1 с 01.09.2026/).length).toBeGreaterThan(0)
    // Grouped: one heading per area. (Area names also appear as filter options.)
    expect(screen.getByRole('heading', { name: /Development/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Health/ })).toBeInTheDocument()
  })

  it('creates a binary daily habit', async () => {
    const api = createFakeApi({ areas: [health] })
    stubFakeApi(api)

    render(<HabitsPage />)
    await openCreateForm()

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Meditate' } })
    chooseArea(1)
    fireEvent.click(screen.getByRole('button', { name: 'Создать привычку' }))

    expect(await screen.findByText('Meditate')).toBeInTheDocument()
    const created = api.habits[0]
    expect(created?.tracking_mode).toBe('binary')
    expect(created?.quantity_unit).toBeNull()
    expect(created?.schedule.type).toBe('daily')
    expect(created?.area_id).toBe(1)
  })

  it('creates a quantity habit with a unit', async () => {
    const api = createFakeApi({ areas: [health] })
    stubFakeApi(api)

    render(<HabitsPage />)
    await openCreateForm()

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Walking' } })
    chooseArea(1)
    chooseSchedule(QUANTITY)

    const unit = screen.getByLabelText('Единица измерения')
    fireEvent.change(unit, { target: { value: 'km' } })
    fireEvent.click(screen.getByLabelText('Разрешить дробные значения'))
    fireEvent.click(screen.getByRole('button', { name: 'Создать привычку' }))

    await waitFor(() => expect(api.habits).toHaveLength(1))
    expect(api.habits[0]?.tracking_mode).toBe('binary_quantity')
    expect(api.habits[0]?.quantity_unit).toBe('km')
    expect(api.habits[0]?.quantity_allows_decimal).toBe(true)
    expect(await screen.findByText('Количество (km)')).toBeInTheDocument()
  })

  it('requires a unit for quantity habits', async () => {
    const api = createFakeApi({ areas: [health] })
    stubFakeApi(api)

    render(<HabitsPage />)
    await openCreateForm()

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Walking' } })
    chooseArea(1)
    chooseSchedule(QUANTITY)
    fireEvent.click(screen.getByRole('button', { name: 'Создать привычку' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Укажите единицу измерения',
    )
    expect(api.habits).toHaveLength(0)
  })

  it('does not show quantity fields for binary habits', async () => {
    const api = createFakeApi({ areas: [health] })
    stubFakeApi(api)

    render(<HabitsPage />)
    await openCreateForm()

    expect(screen.queryByLabelText('Единица измерения')).toBeNull()
    chooseSchedule(QUANTITY)
    expect(screen.getByLabelText('Единица измерения')).toBeInTheDocument()
    chooseSchedule(BINARY)
    expect(screen.queryByLabelText('Единица измерения')).toBeNull()
  })

  it('creates a weekday schedule from the preferred-day picker', async () => {
    const api = createFakeApi({ areas: [health] })
    stubFakeApi(api)

    render(<HabitsPage />)
    await openCreateForm()

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Reading' } })
    chooseArea(1)
    chooseSchedule(WEEKDAYS)

    // Monday-Friday start selected; narrow it to Mon/Wed/Fri.
    for (const day of ['Вт', 'Чт']) {
      fireEvent.click(screen.getByRole('button', { name: day }))
    }
    expect(screen.getByText(/Выполнений в неделю — по числу выбранных дней \(3\)/))
      .toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Создать привычку' }))

    await waitFor(() => expect(api.habits).toHaveLength(1))
    expect(api.habits[0]?.schedule.type).toBe('weekdays')
    expect(api.habits[0]?.schedule.weekdays).toEqual([0, 2, 4])
  })

  it('requires at least one preferred weekday', async () => {
    const api = createFakeApi({ areas: [health] })
    stubFakeApi(api)

    render(<HabitsPage />)
    await openCreateForm()

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Reading' } })
    chooseArea(1)
    chooseSchedule(WEEKDAYS)

    for (const day of ['Пн', 'Вт', 'Ср', 'Чт', 'Пт']) {
      fireEvent.click(screen.getByRole('button', { name: day }))
    }
    fireEvent.click(screen.getByRole('button', { name: 'Создать привычку' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Выберите хотя бы один день недели.',
    )
    expect(api.habits).toHaveLength(0)
  })

  it('creates a times-per-week schedule', async () => {
    const api = createFakeApi({ areas: [health] })
    stubFakeApi(api)

    render(<HabitsPage />)
    await openCreateForm()

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Exercise' } })
    chooseArea(1)
    chooseSchedule(TIMES_PER_WEEK)
    fireEvent.change(screen.getByLabelText('Выполнений в неделю'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать привычку' }))

    await waitFor(() => expect(api.habits).toHaveLength(1))
    expect(api.habits[0]?.schedule.type).toBe('times_per_week')
    expect(api.habits[0]?.schedule.times_per_week).toBe(2)
    expect(await screen.findByText('2 раза в неделю')).toBeInTheDocument()
  })

  it('rejects a weekly quota outside 1 to 7', async () => {
    const api = createFakeApi({ areas: [health] })
    stubFakeApi(api)

    render(<HabitsPage />)
    await openCreateForm()

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Exercise' } })
    chooseArea(1)
    chooseSchedule(TIMES_PER_WEEK)
    fireEvent.change(screen.getByLabelText('Выполнений в неделю'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать привычку' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Укажите число выполнений в неделю от 1 до 7.',
    )
    expect(api.habits).toHaveLength(0)
  })

  it('requires an area', async () => {
    const api = createFakeApi({ areas: [health] })
    stubFakeApi(api)

    render(<HabitsPage />)
    await openCreateForm()

    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Reading' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать привычку' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Выберите сферу.')
    expect(api.habits).toHaveLength(0)
  })

  it('tells the user to create an area first when there are none', async () => {
    stubFakeApi(createFakeApi())

    render(<HabitsPage />)
    await openCreateForm()

    expect(screen.getByText('Сначала создайте сферу — каждая привычка относится к одной сфере.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Создать привычку' })).toBeDisabled()
  })

  it('edits a habit and reflects the new version', async () => {
    const api = createFakeApi({
      areas: [health],
      habits: [habitFixture({ id: 1, name: 'Reading', area_id: 1, weight: 1 })],
    })
    stubFakeApi(api)

    render(<HabitsPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Изменить' }))

    expect(screen.getByLabelText('Название')).toHaveValue('Reading')
    fireEvent.change(screen.getByLabelText('Название'), { target: { value: 'Deep reading' } })
    fireEvent.change(screen.getByLabelText('Важность'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }))

    expect(await screen.findByText('Deep reading')).toBeInTheDocument()
    expect(api.habits[0]?.weight).toBe(3)
    expect(api.habits[0]?.current_version.version_number).toBe(2)
    expect(screen.getByText('Важность 3 · Ключевая')).toBeInTheDocument()
  })

  it('archives a habit', async () => {
    const api = createFakeApi({
      areas: [health],
      habits: [habitFixture({ id: 1, name: 'Reading', area_id: 1 })],
    })
    stubFakeApi(api)

    render(<HabitsPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'В архив' }))

    expect(await screen.findByText(/Привычек пока нет/)).toBeInTheDocument()
    expect(api.habits[0]?.is_archived).toBe(true)
  })

  it('restores an archived habit, showing it when requested', async () => {
    const api = createFakeApi({
      areas: [health],
      habits: [
        habitFixture({
          id: 1,
          name: 'Reading',
          area_id: 1,
          is_archived: true,
          archived_at: '2026-09-20T10:00:00',
        }),
      ],
    })
    stubFakeApi(api)

    render(<HabitsPage />)
    fireEvent.click(screen.getByLabelText('Показывать архивные'))

    expect(await screen.findByText('В архиве')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Восстановить' }))

    await waitFor(() => expect(api.habits[0]?.is_archived).toBe(false))
    await waitFor(() =>
      expect(screen.queryByText('В архиве')).not.toBeInTheDocument(),
    )
  })

  it('filters habits by area', async () => {
    const api = createFakeApi({
      areas: [health, development],
      habits: [
        habitFixture({ id: 1, name: 'Reading', area_id: 2, area: { id: 2, name: 'Development', color: '#4a7cc7', is_archived: false } }),
        habitFixture({ id: 2, name: 'Exercise', area_id: 1 }),
      ],
    })
    stubFakeApi(api)

    render(<HabitsPage />)
    expect(await screen.findByText('Reading')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Фильтр по сфере'), { target: { value: '1' } })

    await waitFor(() => expect(screen.queryByText('Reading')).toBeNull())
    expect(screen.getByText('Exercise')).toBeInTheDocument()
  })

  it('shows configuration history on demand', async () => {
    const api = createFakeApi({
      areas: [health],
      habits: [habitFixture({ id: 1, name: 'Reading', area_id: 1 })],
    })
    stubFakeApi(api)

    render(<HabitsPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'История' }))

    const panel = await screen.findByText('История настроек')
    expect(panel).toBeInTheDocument()
    expect(await screen.findByText('Версия 2')).toBeInTheDocument()
    expect(screen.getByText('Действует с 20.09.2026')).toBeInTheDocument()
    expect(screen.getByText(/Original name/)).toBeInTheDocument()
  })

  it('reports a backend failure while loading habits', async () => {
    stubApi({
      'GET /api/areas': () => jsonResponse([health]),
      'GET /api/habits': () =>
        jsonResponse(
          { error: { code: 'internal_error', message: 'An unexpected error occurred.' } },
          500,
        ),
    })

    render(<HabitsPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'На сервере произошла ошибка. Попробуйте ещё раз.',
    )
  })

  it('groups multiple habits under their area heading', async () => {
    const api = createFakeApi({
      areas: [health, development],
      habits: [
        habitFixture({ id: 1, name: 'Reading', area_id: 2, area: { id: 2, name: 'Development', color: '#4a7cc7', is_archived: false } }),
        habitFixture({ id: 2, name: 'Exercise', area_id: 1 }),
        habitFixture({ id: 3, name: 'Sleep', area_id: 1 }),
      ],
    })
    stubFakeApi(api)

    render(<HabitsPage />)

    const healthHeading = await screen.findByRole('heading', { name: /Health/ })
    const healthSection = healthHeading.closest('section')
    expect(healthSection).not.toBeNull()
    expect(within(healthSection as HTMLElement).getByText('Exercise')).toBeInTheDocument()
    expect(within(healthSection as HTMLElement).getByText('Sleep')).toBeInTheDocument()
    expect(within(healthSection as HTMLElement).getByText('Привычек: 2')).toBeInTheDocument()
  })
})

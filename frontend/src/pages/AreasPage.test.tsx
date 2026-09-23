import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { jsonResponse, stubApi } from '../test/fetchStub'
import { createFakeApi, stubFakeApi } from '../test/fakeApi'
import { areaFixture } from '../test/fixtures'
import { AreasPage } from './AreasPage'

function list(): HTMLElement {
  return screen.getByRole('list')
}

async function openCreateForm(): Promise<void> {
  fireEvent.click(screen.getByRole('button', { name: 'Новая сфера' }))
  await screen.findByLabelText('Название')
}

describe('AreasPage', () => {
  it('lists areas with their colours', async () => {
    const api = createFakeApi({
      areas: [
        areaFixture({ id: 1, name: 'Health', color: '#2f9e5f' }),
        areaFixture({ id: 2, name: 'Work', color: '#4a7cc7' }),
      ],
    })
    stubFakeApi(api)

    render(<AreasPage />)

    expect(await screen.findByText('Health')).toBeInTheDocument()
    expect(screen.getByText('Work')).toBeInTheDocument()
    expect(screen.getByText('#2f9e5f')).toBeInTheDocument()
  })

  it('shows an empty state when there are no areas', async () => {
    stubFakeApi(createFakeApi())

    render(<AreasPage />)

    expect(await screen.findByText(/Нет активных сфер/)).toBeInTheDocument()
  })

  it('creates an area', async () => {
    const api = createFakeApi()
    stubFakeApi(api)

    render(<AreasPage />)
    await openCreateForm()

    fireEvent.change(screen.getByLabelText('Название'), {
      target: { value: 'Development' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Создать сферу' }))

    expect(await screen.findByText('Development')).toBeInTheDocument()
    expect(api.areas.map((area) => area.name)).toEqual(['Development'])
  })

  it('refuses to submit an empty name', async () => {
    const api = createFakeApi()
    stubFakeApi(api)

    render(<AreasPage />)
    await openCreateForm()

    fireEvent.click(screen.getByRole('button', { name: 'Создать сферу' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Введите название сферы.')
    expect(api.areas).toHaveLength(0)
  })

  it('surfaces a duplicate-name conflict and keeps the typed name', async () => {
    const api = createFakeApi({ areas: [areaFixture({ name: 'Health' })] })
    stubFakeApi(api)

    render(<AreasPage />)
    await openCreateForm()

    const nameInput = screen.getByLabelText('Название')
    fireEvent.change(nameInput, { target: { value: 'Health' } })
    fireEvent.click(screen.getByRole('button', { name: 'Создать сферу' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Активная сфера с таким названием уже существует.',
    )
    expect(nameInput).toHaveValue('Health')
  })

  it('edits an area name', async () => {
    const api = createFakeApi({ areas: [areaFixture({ name: 'Health' })] })
    stubFakeApi(api)

    render(<AreasPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Изменить' }))

    const nameInput = screen.getByLabelText('Название')
    expect(nameInput).toHaveValue('Health')
    fireEvent.change(nameInput, { target: { value: 'Wellbeing' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }))

    expect(await screen.findByText('Wellbeing')).toBeInTheDocument()
    expect(api.areas[0]?.name).toBe('Wellbeing')
  })

  it('archives an area and hides it from the active list', async () => {
    const api = createFakeApi({
      areas: [areaFixture({ name: 'Health' }), areaFixture({ id: 2, name: 'Work' })],
    })
    stubFakeApi(api)

    render(<AreasPage />)
    const healthRow = (await screen.findByText('Health')).closest('li')
    expect(healthRow).not.toBeNull()

    fireEvent.click(within(healthRow as HTMLElement).getByRole('button', { name: 'В архив' }))

    await waitFor(() => expect(within(list()).queryByText('Health')).toBeNull())
    expect(api.areas[0]?.is_archived).toBe(true)
    expect(screen.getByText('Work')).toBeInTheDocument()
  })

  it('explains why an area with active habits cannot be archived', async () => {
    // The area looks archivable on screen, but the backend refuses.
    stubApi({
      'GET /api/areas': () => jsonResponse([areaFixture({ name: 'Health' })]),
      'POST /api/areas/1/archive': () =>
        jsonResponse(
          {
            error: {
              code: 'area_has_active_habits',
              message: 'This area still has active habits. Archive or move them first.',
            },
          },
          409,
        ),
    })

    render(<AreasPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'В архив' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'В этой сфере есть активные привычки.',
    )
  })

  it('reveals archived areas on request and restores them', async () => {
    const api = createFakeApi({
      areas: [
        areaFixture({ name: 'Health', is_archived: true, archived_at: '2026-09-20T10:00:00' }),
      ],
    })
    stubFakeApi(api)

    render(<AreasPage />)
    expect(await screen.findByText(/Нет активных сфер/)).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Показывать архивные'))

    expect(await screen.findByText('Health')).toBeInTheDocument()
    expect(within(list()).getByText(/в архиве/)).toBeInTheDocument()

    fireEvent.click(within(list()).getByRole('button', { name: 'Восстановить' }))

    await waitFor(() => expect(api.areas[0]?.is_archived).toBe(false))
    await waitFor(() =>
      expect(within(list()).getByRole('button', { name: 'В архив' })).toBeInTheDocument(),
    )
    expect(within(list()).queryByText(/в архиве/)).toBeNull()
  })

  it('shows a backend failure instead of pretending the list is empty', async () => {
    stubApi({
      'GET /api/areas': () =>
        jsonResponse(
          { error: { code: 'internal_error', message: 'An unexpected error occurred.' } },
          500,
        ),
    })

    render(<AreasPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'На сервере произошла ошибка. Попробуйте ещё раз.',
    )
  })
})

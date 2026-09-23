import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'
import { NAVIGATION_ITEMS } from './navigation'
import {
  jsonResponse,
  stubFetch,
  stubHealthyBackend,
  stubUnreachableBackend,
} from './test/fetchStub'

describe('App shell', () => {
  it('renders the Tracker shell with every navigation destination', () => {
    stubHealthyBackend()

    render(<App />)

    expect(screen.getByText('Tracker', { selector: '.sidebar__name' })).toBeInTheDocument()
    for (const item of NAVIGATION_ITEMS) {
      expect(screen.getByRole('link', { name: new RegExp(item.label, 'i') })).toBeInTheDocument()
    }
  })

  it('shows the dashboard placeholder by default', () => {
    stubHealthyBackend()

    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'Обзор', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByText('Раздел пока в разработке')).toBeInTheDocument()
  })

  it('reports a connected backend with the reported version', async () => {
    stubHealthyBackend()

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('Подключено')).toBeInTheDocument(),
    )
    expect(screen.getByText('Tracker 0.1.0 · тестирование')).toBeInTheDocument()
    // Database and schema both report ok.
    expect(screen.getAllByText('В порядке')).toHaveLength(2)
  })

  it('reports a running backend whose database is unavailable', async () => {
    stubHealthyBackend({
      readiness: { status: 'unavailable', checks: { database: 'error' } },
    })

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('База данных недоступна')).toBeInTheDocument(),
    )
    expect(screen.getByText('Ошибка')).toBeInTheDocument()
  })

  it('explains a database whose schema is behind, with the migration command', async () => {
    stubHealthyBackend({
      readiness: {
        status: 'unavailable',
        checks: { database: 'ok', migrations: 'pending' },
      },
    })

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('Требуется обновление базы')).toBeInTheDocument(),
    )
    expect(screen.getByRole('status')).toHaveTextContent('alembic upgrade head')
  })

  it('reports an unreachable backend with a hint', async () => {
    stubUnreachableBackend()

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('Сервер недоступен')).toBeInTheDocument(),
    )
    expect(screen.getByRole('status')).toHaveTextContent('python -m app')
  })

  it('explains a dev-proxy gateway error as an unreachable backend', async () => {
    // With the backend down, the Vite proxy answers 502 instead of failing.
    stubFetch(async () => jsonResponse('', 502))

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('Сервер недоступен')).toBeInTheDocument(),
    )
    expect(screen.getByRole('status')).toHaveTextContent('python -m app')
  })

  it('navigates to a placeholder screen', async () => {
    stubHealthyBackend()

    render(<App />)
    fireEvent.click(screen.getByRole('link', { name: /инсайты/i }))

    expect(
      await screen.findByRole('heading', { name: 'Инсайты', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByText('Запланировано: Этап 8')).toBeInTheDocument()
  })

  it('rechecks the backend when asked', async () => {
    const fetchMock = stubHealthyBackend()

    render(<App />)
    await waitFor(() => expect(screen.getByText('Подключено')).toBeInTheDocument())

    const callsBefore = fetchMock.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: 'Проверить снова' }))

    await waitFor(() =>
      expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })
})

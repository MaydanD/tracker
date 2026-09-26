import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'
import { NAVIGATION_ITEMS } from './navigation'
import {
  jsonResponse,
  stubApi,
  stubFetch,
  stubHealthyBackend,
  stubUnreachableBackend,
} from './test/fetchStub'
import { detailFixture, experimentFixture } from './test/experimentsFixture'

describe('App shell', () => {
  it('renders the Tracker shell with every navigation destination', () => {
    stubHealthyBackend()

    render(<App />)

    expect(screen.getByText('Tracker', { selector: '.sidebar__name' })).toBeInTheDocument()
    for (const item of NAVIGATION_ITEMS) {
      expect(screen.getByRole('link', { name: new RegExp(item.label, 'i') })).toBeInTheDocument()
    }
  })

  it('shows the main dashboard by default', async () => {
    stubHealthyBackend()

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: 'Главный обзор', level: 1 }),
    ).toBeInTheDocument()
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

  it('navigates to the implemented analytics screen', async () => {
    stubHealthyBackend()

    render(<App />)
    fireEvent.click(screen.getByRole('link', { name: /инсайты/i }))

    expect(
      await screen.findByRole('heading', { name: 'Аналитика', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Статистические проверки')).toBeInTheDocument()
    expect(screen.queryByText('Запланировано: Этап 8')).not.toBeInTheDocument()
  })

  it('keeps the section title on an experiment detail page', async () => {
    stubApi({
      'GET /api/health': () =>
        jsonResponse({
          status: 'ok',
          app: 'Tracker',
          version: '0.1.0',
          environment: 'test',
        }),
      'GET /api/ready': () =>
        jsonResponse({ status: 'ready', checks: { database: 'ok', migrations: 'ok' } }),
      'GET /api/dashboard': () =>
        jsonResponse({
          today: '2026-09-26',
          today_progress: {
            score: null, completed_weight: 0, required_weight: 0,
            entry_date: '2026-09-26', obligations: [],
          },
          week_progress: {
            score: null, completed_weight: 0, required_weight: 0,
            week_start: '2026-09-21', week_end: '2026-09-27', habits: [],
          },
          streaks: [], yesterday_state: null, today_items: [], owl: null,
        }),
      'GET /api/experiments': () =>
        jsonResponse({ experiments: [experimentFixture({ id: 1 })], owl: null }),
      'GET /api/experiments/1': () =>
        jsonResponse(detailFixture({ experiment: experimentFixture({ id: 1 }) })),
    })

    render(<App />)
    fireEvent.click(screen.getByRole('link', { name: /эксперименты/i }))
    fireEvent.click(await screen.findByRole('link', { name: 'Открыть' }))

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Без алкоголя 14 дней', level: 1 }),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText('Эксперименты', { selector: '.topbar__title' })).toBeInTheDocument()
    expect(screen.queryByText('Неизвестный раздел')).toBeNull()
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

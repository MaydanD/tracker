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
      screen.getByRole('heading', { name: 'Dashboard', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByText('Not implemented yet')).toBeInTheDocument()
  })

  it('reports a connected backend with the reported version', async () => {
    stubHealthyBackend()

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('Connected')).toBeInTheDocument(),
    )
    expect(screen.getByText('Tracker 0.1.0 · test')).toBeInTheDocument()
    expect(screen.getByText('ok')).toBeInTheDocument()
  })

  it('reports a running backend whose database is unavailable', async () => {
    stubHealthyBackend({
      readiness: { status: 'unavailable', checks: { database: 'error' } },
    })

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('Database unavailable')).toBeInTheDocument(),
    )
    expect(screen.getByText('error')).toBeInTheDocument()
  })

  it('reports an unreachable backend with a hint', async () => {
    stubUnreachableBackend()

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('Backend unreachable')).toBeInTheDocument(),
    )
    expect(screen.getByRole('status')).toHaveTextContent('python -m app')
  })

  it('explains a dev-proxy gateway error as an unreachable backend', async () => {
    // With the backend down, the Vite proxy answers 502 instead of failing.
    stubFetch(async () => jsonResponse('', 502))

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('Backend unreachable')).toBeInTheDocument(),
    )
    expect(screen.getByRole('status')).toHaveTextContent('python -m app')
  })

  it('navigates to a placeholder screen', async () => {
    stubHealthyBackend()

    render(<App />)
    fireEvent.click(screen.getByRole('link', { name: /habits/i }))

    expect(
      await screen.findByRole('heading', { name: 'Habits and areas', level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByText('Planned for Stage 2')).toBeInTheDocument()
  })

  it('rechecks the backend when asked', async () => {
    const fetchMock = stubHealthyBackend()

    render(<App />)
    await waitFor(() => expect(screen.getByText('Connected')).toBeInTheDocument())

    const callsBefore = fetchMock.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: 'Recheck' }))

    await waitFor(() =>
      expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })
})

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { jsonResponse, stubApi } from '../../test/fetchStub'
import { RecentDays } from './RecentDays'

const today = '2026-10-03'
const summaries = [
  { entry_date: '2026-09-30', total_items: 0, answered_items: 0, is_future: false },
  { entry_date: '2026-10-01', total_items: 2, answered_items: 2, is_future: false },
  { entry_date: '2026-10-02', total_items: 2, answered_items: 1, is_future: false },
  { entry_date: today, total_items: 2, answered_items: 0, is_future: false },
]

describe('RecentDays', () => {
  it('colors completion, partial and empty days and selects a date', async () => {
    stubApi({ 'GET /api/calendar': ({ query }) => {
      expect(query.get('start')).toBe('2026-09-24')
      expect(query.get('end')).toBe(today)
      return jsonResponse(summaries)
    } })
    const onSelect = vi.fn()
    render(<RecentDays today={today} selectedDate={today} onSelect={onSelect} />)
    expect(await screen.findByRole('button', { name: /1 октября.*Заполнено/ })).toHaveClass('recent-day--complete')
    const partial = screen.getByRole('button', { name: /2 октября.*Отмечено 1 из 2/ })
    expect(partial).toHaveClass('recent-day--incomplete')
    expect(screen.getByRole('button', { name: /30 сентября.*Нет привычек/ })).toHaveClass('recent-day--empty')
    expect(screen.getByRole('button', { name: /3 октября/ })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(partial)
    expect(onSelect).toHaveBeenCalledWith('2026-10-02')
  })

  it('shows only past incomplete days as dashboard links', async () => {
    stubApi({ 'GET /api/calendar': ({ query }) => {
      expect(query.get('start')).toBe('2026-09-03')
      expect(query.get('end')).toBe('2026-10-02')
      return jsonResponse(summaries)
    } })
    render(<RecentDays today={today} missedOnly />)
    const link = await screen.findByRole('link', { name: /2 октября/ })
    expect(link).toHaveAttribute('href', '#/check-in?date=2026-10-02')
    expect(screen.getAllByRole('link')).toHaveLength(1)
  })

  it('refreshes completion after saving and clearing an answer', async () => {
    let answered = 1
    stubApi({ 'GET /api/calendar': () => jsonResponse([
      { entry_date: today, total_items: 2, answered_items: answered, is_future: false },
    ]) })
    const view = render(<RecentDays today={today} revision={0} />)
    expect(await screen.findByRole('button', { name: /Отмечено 1 из 2/ })).toHaveClass('recent-day--incomplete')
    answered = 2
    view.rerender(<RecentDays today={today} revision={1} />)
    expect(await screen.findByRole('button', { name: /Заполнено/ })).toHaveClass('recent-day--complete')
    answered = 1
    view.rerender(<RecentDays today={today} revision={2} />)
    expect(await screen.findByRole('button', { name: /Отмечено 1 из 2/ })).toHaveClass('recent-day--incomplete')
  })

  it('hides the dashboard block when no days are incomplete', async () => {
    stubApi({ 'GET /api/calendar': () => jsonResponse([summaries[1]]) })
    render(<RecentDays today={today} missedOnly />)
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Незаполненные дни' })).not.toBeInTheDocument())
  })

  it('offers a retry on failure instead of claiming there are no missing days', async () => {
    let failed = true
    stubApi({ 'GET /api/calendar': () => failed
      ? jsonResponse({ error: { code: 'internal_error', message: 'Unavailable' } }, 500)
      : jsonResponse(summaries) })
    render(<RecentDays today={today} missedOnly />)
    const retry = await screen.findByRole('button', { name: 'Повторить загрузку дней' })
    failed = false
    fireEvent.click(retry)
    expect(await screen.findByRole('link', { name: /2 октября/ })).toBeInTheDocument()
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Незаполненные дни' })).queryByRole('alert')).toBeNull())
  })
})

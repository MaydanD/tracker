import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BackupReminder } from './BackupReminder'

const FIRST = '2026-10-01'
const NOT_FIRST = '2026-09-25'

function backupResponse(): Response {
  return {
    ok: true,
    status: 200,
    blob: async () => new Blob(['zip']),
    headers: { get: () => null },
  } as unknown as Response
}

describe('BackupReminder', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
    URL.createObjectURL = vi.fn(() => 'blob:test')
    URL.revokeObjectURL = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async () => backupResponse()))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('stays hidden on any day that is not the first of the month', () => {
    const { container } = render(<BackupReminder today={NOT_FIRST} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('offers a backup on the first of the month', () => {
    render(<BackupReminder today={FIRST} />)
    expect(
      screen.getByText('Начало месяца — самое время сохранить резервную копию.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сделать backup' })).toBeInTheDocument()
  })

  it('downloads the existing backup export and then stops asking', async () => {
    render(<BackupReminder today={FIRST} />)

    fireEvent.click(screen.getByRole('button', { name: 'Сделать backup' }))

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Сделать backup' })).not.toBeInTheDocument(),
    )
    expect(window.localStorage.getItem('tracker:backup-done')).toBe(FIRST)
  })

  it('goes quiet for the session when postponed, without a real backup', () => {
    render(<BackupReminder today={FIRST} />)

    fireEvent.click(screen.getByRole('button', { name: 'Позже' }))
    expect(screen.queryByRole('button', { name: 'Сделать backup' })).not.toBeInTheDocument()
    expect(window.sessionStorage.getItem('tracker:backup-postponed')).toBe(FIRST)

    // A fresh mount in the same session (e.g. navigating away and back) stays quiet.
    const { container } = render(<BackupReminder today={FIRST} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('does not ask again once a backup was already taken that day', () => {
    window.localStorage.setItem('tracker:backup-done', FIRST)
    const { container } = render(<BackupReminder today={FIRST} />)
    expect(container).toBeEmptyDOMElement()
  })
})

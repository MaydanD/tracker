import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { BackupReminder } from './BackupReminder'
import { backupStatusFixture } from '../test/backupFixture'

let status = { ...backupStatusFixture }
let fail = false
beforeEach(() => {
  status = { ...backupStatusFixture }; fail = false
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  vi.stubGlobal('fetch', vi.fn(async (input) => {
    if (String(input) === '/api/backup') {
      if (fail) return { ok: false, json: async () => ({}) }
      status = { ...status, reminder_due: false }
      return { ok: true, blob: async () => new Blob(['zip']), headers: new Headers() }
    }
    return { ok: true, json: async () => ({ ...status }) }
  }))
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('offers a monthly backup on the eighth, with a settings link', async () => {
  render(<BackupReminder today="2026-10-08" />)
  expect(await screen.findByText('Пора сделать резервную копию')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Настроить резервные копии' })).toHaveAttribute('href', '#/settings?section=backups')
})
it('hides after successful download without reload or localStorage', async () => {
  render(<BackupReminder today="2026-10-08" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Сделать резервную копию' }))
  await waitFor(() => expect(screen.queryByText('Пора сделать резервную копию')).not.toBeInTheDocument())
  expect(localStorage.getItem('tracker:backup-done')).toBeNull()
})
it('does not offer when the backend reports a successful backup this month', async () => {
  status.reminder_due = false
  render(<BackupReminder today="2026-10-08" />)
  await waitFor(() => expect(fetch).toHaveBeenCalled())
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})
it('keeps the reminder on download failure and shows the error', async () => {
  fail = true
  render(<BackupReminder today="2026-10-08" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Сделать резервную копию' }))
  expect(await screen.findByRole('alert')).toBeInTheDocument()
  expect(screen.getByText('Пора сделать резервную копию')).toBeInTheDocument()
})
it('disables downloading while automatic sending is in progress', async () => {
  status.in_progress = true
  render(<BackupReminder today="2026-10-08" />)
  expect(await screen.findByRole('button')).toBeDisabled()
})
it('updates after an external backup event and checks the new calendar date', async () => {
  const view = render(<BackupReminder today="2026-10-08" />)
  await screen.findByRole('button')
  status.reminder_due = false
  window.dispatchEvent(new Event('tracker:backup-updated'))
  await waitFor(() => expect(screen.queryByRole('button')).not.toBeInTheDocument())
  status.reminder_due = true
  view.rerender(<BackupReminder today="2026-11-08" />)
  expect(await screen.findByRole('button')).toBeEnabled()
})

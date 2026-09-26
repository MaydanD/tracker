import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as backupApi from '../api/backup'
import { SettingsPage } from './SettingsPage'

vi.mock('../api/backup', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/backup')>(), reloadAfterRestore: vi.fn(),
}))

const preview = {
  manifest: { format: 'tracker-backup', version: 1, application_backup_version: 1,
    created_at: '2026-09-26T12:00:00', alembic_revision: 'c3f1a7b24d90',
    counts: { areas: 2, habits: 12, habit_versions: 25, habit_entries: 834, daily_states: 102, experiments: 3, insight_snapshots: 48 } },
  validation_token: 'signed-token', expires_in_seconds: 1800,
}

function response(body: unknown, status = 200): Response {
  return { ok: status < 400, status, json: async () => body,
    blob: async () => new Blob(['archive']),
    headers: new Headers({ 'Content-Disposition': 'attachment; filename="tracker-download.zip"' }),
  } as Response
}

function renderPage() { return render(<MemoryRouter><SettingsPage /></MemoryRouter>) }
function choose(name = 'backup.zip') {
  const file = new File(['archive'], name, { type: 'application/zip' })
  fireEvent.change(screen.getByLabelText('Выбрать файл резервной копии'), { target: { files: [file] } })
  return file
}
async function confirmPreview() {
  choose()
  await screen.findByText('834')
  fireEvent.click(screen.getByRole('button', { name: 'Восстановить данные' }))
}

beforeEach(() => {
  sessionStorage.clear()
  vi.mocked(backupApi.reloadAfterRestore).mockClear()
  vi.stubGlobal('fetch', vi.fn(async () => response(preview)))
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('Данные и резервные копии', () => {
  it('renders the Russian data page and disables restore before validation', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: 'Данные и резервные копии' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Восстановить данные' })).toBeDisabled()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it.each([
    ['Скачать резервную копию', '/api/backup'],
    ['Экспортировать JSON', '/api/export/json'],
    ['Экспортировать CSV', '/api/export/csv'],
  ])('downloads via %s', async (label, path) => {
    const create = vi.fn(() => 'blob:download')
    const revoke = vi.fn()
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: label }))
    expect(await screen.findByRole('status')).toHaveTextContent('передан браузеру')
    expect(fetch).toHaveBeenCalledWith(path, undefined)
    expect(create).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    const anchor = click.mock.instances[0] as HTMLAnchorElement
    expect(anchor.download).toBe('tracker-download.zip')
  })

  it('uploads the file as binary and displays all preview counts and replacement warning', async () => {
    renderPage()
    const file = choose()
    await screen.findByText('834')
    expect(fetch).toHaveBeenCalledWith('/api/backup/validate', expect.objectContaining({ body: file, method: 'POST' }))
    expect(screen.getByText(/Версия: 1 · Схема: c3f1a7b24d90/)).toBeInTheDocument()
    for (const label of ['Сферы', 'Привычки', 'Версии настроек', 'Записи привычек', 'Состояния дня', 'Эксперименты', 'Снимки инсайтов']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getByText('Текущие данные Tracker будут заменены данными из резервной копии.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Восстановить данные' })).toBeEnabled()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('requires a separate confirmation and reloads application data on success', async () => {
    renderPage()
    await confirmPreview()
    expect(screen.getByRole('alertdialog')).toHaveTextContent('Текущие данные будут заменены.')
    expect(fetch).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Да, восстановить' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Данные восстановлены'))
    expect(fetch).toHaveBeenLastCalledWith('/api/backup/restore', expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({
        'X-Tracker-Validation-Token': 'signed-token', 'X-Tracker-Confirm-Restore': 'replace',
      }),
    }))
    expect(backupApi.reloadAfterRestore).toHaveBeenCalledOnce()
    expect(screen.getByRole('link', { name: 'Перейти на главный обзор' })).toHaveAttribute('href', '/')
    expect(screen.queryByText('834')).not.toBeInTheDocument()
  })

  it('allows cancelling before application without a restore request', async () => {
    renderPage()
    await confirmPreview()
    fireEvent.click(screen.getByRole('button', { name: 'Вернуться к проверке' }))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(screen.getByText('834')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Отменить' }))
    expect(screen.queryByText('834')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Восстановить данные' })).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('shows the exact invalid backup reason', async () => {
    vi.mocked(fetch).mockResolvedValue(response({ error: { code: 'invalid_backup', message: 'Резервная копия создана более новой версией Tracker.' } }, 422))
    renderPage(); choose()
    expect(await screen.findByRole('alert')).toHaveTextContent('более новой версией')
    expect(screen.getByRole('button', { name: 'Восстановить данные' })).toBeDisabled()
  })

  it('reports restore failure and keeps the file available for retry', async () => {
    renderPage()
    await confirmPreview()
    vi.mocked(fetch).mockResolvedValue(response({ error: { code: 'restore_failed', message: 'Текущие данные сохранены.' } }, 500))
    fireEvent.click(screen.getByRole('button', { name: 'Да, восстановить' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Текущие данные сохранены.')
    expect(screen.getByText('834')).toBeInTheDocument()
    expect(backupApi.reloadAfterRestore).not.toHaveBeenCalled()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('discards an old preview immediately when another file is selected', async () => {
    renderPage(); choose()
    await screen.findByText('834')
    vi.mocked(fetch).mockImplementation(() => new Promise(() => {}))
    choose('other.zip')
    expect(screen.queryByText('834')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Восстановить данные' })).toBeDisabled()
  })

  it('ignores a late validation result from a previous file', async () => {
    let resolveFirst!: (value: Response) => void
    vi.mocked(fetch).mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
    renderPage(); choose('first.zip'); choose('second.zip')
    await screen.findByText('834')
    await act(async () => resolveFirst(response({ ...preview, manifest: { ...preview.manifest, counts: { habits: 999 } } })))
    expect(screen.queryByText('999')).not.toBeInTheDocument()
    expect(screen.getByText('834')).toBeInTheDocument()
  })

  it('ignores a validation result after cancellation', async () => {
    let finish!: (value: Response) => void
    vi.mocked(fetch).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    renderPage(); choose()
    fireEvent.click(screen.getByRole('button', { name: 'Отменить' }))
    await act(async () => finish(response(preview)))
    expect(screen.queryByText('834')).not.toBeInTheDocument()
  })

  it('blocks double restore and file replacement during application', async () => {
    renderPage(); await confirmPreview()
    vi.mocked(fetch).mockImplementation(() => new Promise(() => {}))
    fireEvent.click(screen.getByRole('button', { name: 'Да, восстановить' }))
    expect(screen.getByRole('button', { name: 'Да, восстановить' })).toBeDisabled()
    expect(screen.getByLabelText('Выбрать файл резервной копии')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Отменить' })).toBeDisabled()
  })

  it('shows a persisted success message after reload', () => {
    sessionStorage.setItem('tracker:restore-success', '1')
    renderPage()
    expect(screen.getByRole('status')).toHaveTextContent('Данные восстановлены')
    expect(sessionStorage.getItem('tracker:restore-success')).toBeNull()
  })

  it('does not expose raw server errors and recovers download controls', async () => {
    vi.mocked(fetch).mockResolvedValue(response({ error: { code: 'internal_error', message: 'Traceback secret path' } }, 500))
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Скачать резервную копию' }))
    expect(await screen.findByRole('alert')).not.toHaveTextContent('Traceback')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Скачать резервную копию' })).toBeEnabled())
  })
})

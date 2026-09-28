/**
 * TelegramBackupSettings — targeted tests for the status badge, action flow,
 * auto-check, and error semantics.
 *
 * The useTelegramAutoCheck hook is mocked out so tests never fire a real
 * background check.  Individual auto-check behaviour is covered in its own
 * unit file (useTelegramAutoCheck.test.ts).
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { TelegramBackupSettings } from './TelegramBackupSettings'
import { backupStatusFixture } from '../test/backupFixture'
import * as api from '../api/backup'
import { useTelegramAutoCheck } from '../hooks/useTelegramAutoCheck'

// Silence the auto-check hook so it never fires telegramAction automatically.
vi.mock('../hooks/useTelegramAutoCheck', () => ({ useTelegramAutoCheck: vi.fn() }))
vi.mock('../api/backup', () => ({ telegramAction: vi.fn(), updateBackupSettings: vi.fn() }))

const configured = {
  ...backupStatusFixture,
  configured: true, token_saved: true, chat_id: '123',
  telegram_verified_at: null, verified: false,
}
const verifiedAt = '2026-09-28T10:00:00Z'
const verified = {
  ...configured,
  verified: true, connected: true, telegram_verified_at: verifiedAt,
}

beforeEach(() => {
  vi.mocked(api.telegramAction).mockResolvedValue(verified)
  vi.mocked(api.updateBackupSettings).mockResolvedValue(configured)
})
afterEach(() => vi.resetAllMocks())

// ─── Helper: find the badge label text ──────────────────────────────────────

/** Returns the text content of the .tg-status__label span. */
function badgeLabel() {
  return screen.getByText(/Не настроено|Настроено, подключение не проверено|Подключено|Ошибка подключения|Проверяем/i, {
    selector: '.tg-status__label',
  }).textContent
}

// ─── Existing tests (updated for badge structure) ────────────────────────────

it('shows not configured and disables sending and checking', () => {
  render(<TelegramBackupSettings status={backupStatusFixture} disabled={false} onBusy={vi.fn()} />)
  expect(badgeLabel()).toBe('Не настроено')
  expect(screen.getByRole('button', { name: 'Отправить резервную копию сейчас' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Проверить подключение' })).toBeDisabled()
})

it('saves and clears the token, without displaying the saved secret', async () => {
  const { rerender } = render(<TelegramBackupSettings status={backupStatusFixture} disabled={false} onBusy={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('Токен бота'), { target: { value: 'test-secret' } })
  fireEvent.change(screen.getByLabelText('Идентификатор чата'), { target: { value: '123' } })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить настройки' }))
  await screen.findByText('Настройки сохранены.')
  expect(api.updateBackupSettings).toHaveBeenCalledWith({ token: 'test-secret', chat_id: '123', auto_enabled: true })
  expect(screen.getByLabelText('Токен бота')).toHaveValue('')
  rerender(<TelegramBackupSettings status={configured} disabled={false} onBusy={vi.fn()} />)
  expect(screen.getByPlaceholderText('Токен сохранён')).toHaveValue('')
})

it('sends now, disables controls while sending, then shows success', async () => {
  let finish!: (value: typeof verified) => void
  vi.mocked(api.telegramAction).mockReturnValue(new Promise(resolve => { finish = resolve }))
  const onBusy = vi.fn()
  render(<TelegramBackupSettings status={configured} disabled={false} onBusy={onBusy} />)
  fireEvent.click(screen.getByRole('button', { name: 'Отправить резервную копию сейчас' }))
  expect(screen.getByRole('status')).toHaveTextContent('Создаём и отправляем')
  expect(screen.getByLabelText('Токен бота')).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Проверить подключение' })).toBeDisabled()
  finish(verified)
  expect(await screen.findByText('Резервная копия отправлена в Telegram.')).toBeInTheDocument()
  expect(onBusy).toHaveBeenLastCalledWith(false)
})

it('shows a Russian Telegram error and restores controls', async () => {
  vi.mocked(api.telegramAction).mockRejectedValue(new Error('Telegram отклонил токен бота.'))
  render(<TelegramBackupSettings status={configured} disabled={false} onBusy={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Отправить резервную копию сейчас' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Telegram отклонил токен бота.')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Отправить резервную копию сейчас' })).toBeEnabled())
})

it('checks saved settings without sending backup and shows connected', async () => {
  render(<TelegramBackupSettings status={verified} disabled={false} onBusy={vi.fn()} />)
  expect(badgeLabel()).toBe('Подключено')
  fireEvent.click(screen.getByRole('button', { name: 'Проверить подключение' }))
  expect(await screen.findByText('Подключено. Личный чат доступен.')).toBeInTheDocument()
  expect(api.telegramAction).toHaveBeenCalledWith('check')
})

it('shows automatic failure and retry time and blocks during restore', () => {
  render(<TelegramBackupSettings
    status={{ ...configured, auto_enabled: true, last_error: 'Нет ответа Telegram.', next_auto_attempt_at: '2026-10-09T12:00:00Z' }}
    disabled onBusy={vi.fn()}
  />)
  expect(screen.getByRole('alert')).toHaveTextContent('Нет ответа Telegram.')
  expect(screen.getByText(/Следующая автоматическая попытка возможна/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Отправить резервную копию сейчас' })).toBeDisabled()
})

// ─── Regression tests: status badge semantics ────────────────────────────────

it('shows Не настроено when credentials are absent', () => {
  render(<TelegramBackupSettings status={backupStatusFixture} disabled={false} onBusy={vi.fn()} />)
  expect(badgeLabel()).toBe('Не настроено')
})

it('shows not-yet-verified label when configured but not verified', () => {
  render(<TelegramBackupSettings status={configured} disabled={false} onBusy={vi.fn()} />)
  expect(badgeLabel()).toBe('Настроено, подключение не проверено')
})

it('shows Подключено when connected is true', () => {
  render(<TelegramBackupSettings status={{ ...configured, connected: true }} disabled={false} onBusy={vi.fn()} />)
  expect(badgeLabel()).toBe('Подключено')
})

it('shows Подключено when verified is true even if connected is false (after reload)', () => {
  render(<TelegramBackupSettings
    status={{ ...configured, connected: false, verified: true, telegram_verified_at: verifiedAt }}
    disabled={false} onBusy={vi.fn()}
  />)
  expect(badgeLabel()).toBe('Подключено')
})

it('shows error state when last_error set and never verified', () => {
  render(<TelegramBackupSettings
    status={{ ...configured, last_error: 'Telegram отклонил токен бота.' }}
    disabled={false} onBusy={vi.fn()}
  />)
  expect(badgeLabel()).toBe('Ошибка подключения')
  expect(screen.getByRole('alert')).toHaveTextContent('Telegram отклонил токен бота.')
})

it('keeps Подключено badge when last_error set but verified history exists', () => {
  // Transient error after previous successful verify — badge stays green,
  // error shown as sub-note only.
  render(<TelegramBackupSettings
    status={{ ...verified, last_error: 'Таймаут Telegram.' }}
    disabled={false} onBusy={vi.fn()}
  />)
  expect(badgeLabel()).toBe('Подключено')
  // The sub-note alert is inside the badge, not the full-page alert, and its
  // wording stays operation-neutral: `last_error` may come from a check *or*
  // from a backup send.
  expect(screen.getByText('Последняя операция Telegram завершилась с ошибкой: Таймаут Telegram.')).toBeInTheDocument()
})

it('shows a neutral note beside the green badge while a background check runs', () => {
  render(<TelegramBackupSettings status={verified} disabled={false} onBusy={vi.fn()} />)
  const start = vi.mocked(useTelegramAutoCheck).mock.calls[0]![2]!
  expect(badgeLabel()).toBe('Подключено')

  act(() => start(true))

  // The persisted green state is not replaced — only a small note is added.
  expect(badgeLabel()).toBe('Подключено')
  expect(screen.getByText('· Проверяем…')).toBeInTheDocument()

  act(() => start(false))
  expect(screen.queryByText('· Проверяем…')).not.toBeInTheDocument()
})

it('shows «Проверяем подключение…» while a background check runs on an unverified card', () => {
  render(<TelegramBackupSettings status={configured} disabled={false} onBusy={vi.fn()} />)
  const start = vi.mocked(useTelegramAutoCheck).mock.calls[0]![2]!
  expect(badgeLabel()).toBe('Настроено, подключение не проверено')

  act(() => start(true))
  expect(badgeLabel()).toBe('Проверяем подключение…')

  act(() => start(false))
  expect(badgeLabel()).toBe('Настроено, подключение не проверено')
})

it('calls onStatusUpdate immediately after successful check', async () => {
  const onStatusUpdate = vi.fn()
  render(<TelegramBackupSettings status={configured} disabled={false} onBusy={vi.fn()} onStatusUpdate={onStatusUpdate} />)
  fireEvent.click(screen.getByRole('button', { name: 'Проверить подключение' }))
  await screen.findByText('Подключено. Личный чат доступен.')
  expect(onStatusUpdate).toHaveBeenCalledWith(verified)
})

it('calls onStatusUpdate immediately after successful backup send', async () => {
  const onStatusUpdate = vi.fn()
  render(<TelegramBackupSettings status={configured} disabled={false} onBusy={vi.fn()} onStatusUpdate={onStatusUpdate} />)
  fireEvent.click(screen.getByRole('button', { name: 'Отправить резервную копию сейчас' }))
  await screen.findByText('Резервная копия отправлена в Telegram.')
  expect(onStatusUpdate).toHaveBeenCalledWith(verified)
})

it('does not call onStatusUpdate when send fails', async () => {
  const onStatusUpdate = vi.fn()
  vi.mocked(api.telegramAction).mockRejectedValue(new Error('Нет ответа Telegram.'))
  render(<TelegramBackupSettings status={configured} disabled={false} onBusy={vi.fn()} onStatusUpdate={onStatusUpdate} />)
  fireEvent.click(screen.getByRole('button', { name: 'Отправить резервную копию сейчас' }))
  await screen.findByRole('alert')
  expect(onStatusUpdate).not.toHaveBeenCalled()
})

it('check error does not replace verified badge — only adds sub-note', async () => {
  // Was previously verified; now check fails.
  vi.mocked(api.telegramAction).mockRejectedValue(new Error('Таймаут Telegram.'))
  const onStatusUpdate = vi.fn()
  render(<TelegramBackupSettings status={verified} disabled={false} onBusy={vi.fn()} onStatusUpdate={onStatusUpdate} />)
  fireEvent.click(screen.getByRole('button', { name: 'Проверить подключение' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Проверить подключение' })).toBeEnabled())
  // Badge stays green — error is a sub-note, not a full page alert
  expect(badgeLabel()).toBe('Подключено')
  expect(onStatusUpdate).not.toHaveBeenCalled()
})

it('reports an auto-check result upward without any button press', async () => {
  const onStatusUpdate = vi.fn()
  const { rerender } = render(
    <TelegramBackupSettings status={configured} disabled={false} onBusy={vi.fn()} onStatusUpdate={onStatusUpdate} />,
  )
  // The hook receives the current status and a callback the background check feeds.
  const hookCall = vi.mocked(useTelegramAutoCheck).mock.calls[0]
  expect(hookCall).toBeDefined()
  const [hookStatus, onResult] = hookCall!
  expect(hookStatus).toEqual(configured)

  act(() => onResult(verified))

  expect(onStatusUpdate).toHaveBeenCalledWith(verified)
  // The page owns the status: once it re-renders with the fresh value the badge
  // is green without the user having pressed anything.
  const applied = onStatusUpdate.mock.calls[0]![0] as typeof verified
  rerender(
    <TelegramBackupSettings status={applied} disabled={false} onBusy={vi.fn()} onStatusUpdate={onStatusUpdate} />,
  )
  expect(badgeLabel()).toBe('Подключено')
})

it('token input value is never readable after save (no echo of secret)', async () => {
  vi.mocked(api.updateBackupSettings).mockResolvedValue(configured)
  render(<TelegramBackupSettings status={backupStatusFixture} disabled={false} onBusy={vi.fn()} />)
  const tokenInput = screen.getByLabelText('Токен бота')
  fireEvent.change(tokenInput, { target: { value: 'super-secret-token' } })
  fireEvent.change(screen.getByLabelText('Идентификатор чата'), { target: { value: '123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить настройки' }))
  await screen.findByText('Настройки сохранены.')
  expect(tokenInput).toHaveValue('')
  expect(screen.queryByText('super-secret-token')).not.toBeInTheDocument()
})

it('verified_at timestamp is shown in the badge when connected', () => {
  render(<TelegramBackupSettings status={verified} disabled={false} onBusy={vi.fn()} />)
  const badgeEl = document.querySelector('.tg-status')
  expect(badgeEl).toBeTruthy()
  expect(badgeEl?.textContent).toContain('Проверено:')
})

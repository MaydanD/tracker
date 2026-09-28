/**
 * useTelegramAutoCheck — unit tests for the background auto-check logic.
 *
 * Covers: not-yet-checked, stale, fresh, in-progress guard, no-retry-storm.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { resetTelegramAutoCheck, useTelegramAutoCheck } from './useTelegramAutoCheck'
import * as api from '../api/backup'
import type { BackupStatus } from '../api/backup'
import { backupStatusFixture } from '../test/backupFixture'

vi.mock('../api/backup', () => ({ telegramAction: vi.fn() }))

const configured = {
  ...backupStatusFixture,
  configured: true, token_saved: true, chat_id: '123',
  telegram_verified_at: null, verified: false,
}
const verifiedAt = '2026-09-28T10:00:00Z'
const freshVerified = {
  ...configured,
  verified: true, connected: true, telegram_verified_at: new Date().toISOString(),
}

beforeEach(() => {
  // The in-flight guard is module state shared by every mounted hook, so it
  // has to be reset between tests, otherwise one test could silence the next.
  resetTelegramAutoCheck()
  vi.mocked(api.telegramAction).mockResolvedValue({ ...configured, verified: true, connected: true, telegram_verified_at: verifiedAt })
})
afterEach(() => vi.resetAllMocks())

it('fires auto-check when configured and never verified', async () => {
  const onResult = vi.fn()
  renderHook(() => useTelegramAutoCheck(configured, onResult))
  await waitFor(() => expect(api.telegramAction).toHaveBeenCalledWith('check'))
  await waitFor(() => expect(onResult).toHaveBeenCalled())
})

it('skips auto-check when not configured', async () => {
  const onResult = vi.fn()
  renderHook(() => useTelegramAutoCheck(backupStatusFixture, onResult))
  await new Promise(r => setTimeout(r, 50))
  expect(api.telegramAction).not.toHaveBeenCalled()
})

it('skips auto-check when recently verified (within TTL)', async () => {
  const onResult = vi.fn()
  renderHook(() => useTelegramAutoCheck(freshVerified, onResult))
  await new Promise(r => setTimeout(r, 50))
  expect(api.telegramAction).not.toHaveBeenCalled()
})

it('fires auto-check when verified_at is stale (older than TTL)', async () => {
  const onResult = vi.fn()
  const staleVerifiedAt = new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString() // 5h ago
  const stale = { ...configured, verified: true, telegram_verified_at: staleVerifiedAt }
  renderHook(() => useTelegramAutoCheck(stale, onResult))
  await waitFor(() => expect(api.telegramAction).toHaveBeenCalledWith('check'))
})

it('skips auto-check when status is null', async () => {
  const onResult = vi.fn()
  renderHook(() => useTelegramAutoCheck(null, onResult))
  await new Promise(r => setTimeout(r, 50))
  expect(api.telegramAction).not.toHaveBeenCalled()
})

it('skips auto-check when in_progress', async () => {
  const onResult = vi.fn()
  renderHook(() => useTelegramAutoCheck({ ...configured, in_progress: true }, onResult))
  await new Promise(r => setTimeout(r, 50))
  expect(api.telegramAction).not.toHaveBeenCalled()
})

it('does not call onResult when auto-check fails silently', async () => {
  vi.mocked(api.telegramAction).mockRejectedValue(new Error('Network error'))
  const onResult = vi.fn()
  renderHook(() => useTelegramAutoCheck(configured, onResult))
  await waitFor(() => expect(api.telegramAction).toHaveBeenCalled())
  await new Promise(r => setTimeout(r, 50))
  expect(onResult).not.toHaveBeenCalled()
})

it('does not retry after a failure, even when the status prop changes', async () => {
  vi.mocked(api.telegramAction).mockRejectedValue(new Error('Network error'))
  const onResult = vi.fn()
  const { rerender } = renderHook(
    ({ status }: { status: BackupStatus }) => useTelegramAutoCheck(status, onResult),
    { initialProps: { status: configured } },
  )
  await waitFor(() => expect(api.telegramAction).toHaveBeenCalledTimes(1))
  rerender({ status: { ...configured, last_error: 'Нет ответа Telegram.' } })
  rerender({ status: { ...configured, in_progress: true } })
  rerender({ status: configured })
  await new Promise(r => setTimeout(r, 50))
  expect(api.telegramAction).toHaveBeenCalledTimes(1)
})

it('starts a single check when two cards mount at the same time', async () => {
  const first = vi.fn()
  const second = vi.fn()
  renderHook(() => useTelegramAutoCheck(configured, first))
  renderHook(() => useTelegramAutoCheck(configured, second))
  await waitFor(() => expect(api.telegramAction).toHaveBeenCalledTimes(1))
  await new Promise(r => setTimeout(r, 50))
  expect(api.telegramAction).toHaveBeenCalledTimes(1)
  expect(second).not.toHaveBeenCalled()
})

it('reports the fresh status through the latest callback after a rerender', async () => {
  const stale = vi.fn()
  const latest = vi.fn()
  const { rerender } = renderHook(
    ({ callback }: { callback: (updated: BackupStatus) => void }) =>
      useTelegramAutoCheck(configured, callback),
    { initialProps: { callback: stale } },
  )
  rerender({ callback: latest })
  await waitFor(() => expect(latest).toHaveBeenCalledWith(expect.objectContaining({ verified: true })))
  expect(stale).not.toHaveBeenCalled()
})

it('reports when the background check starts and finishes', async () => {
  const onChecking = vi.fn()
  renderHook(() => useTelegramAutoCheck(configured, vi.fn(), onChecking))
  await waitFor(() => expect(api.telegramAction).toHaveBeenCalled())
  expect(onChecking).toHaveBeenCalledWith(true)
  await waitFor(() => expect(onChecking).toHaveBeenCalledWith(false))
})

it('reports nothing when no check runs', async () => {
  const onChecking = vi.fn()
  renderHook(() => useTelegramAutoCheck(freshVerified, vi.fn(), onChecking))
  await new Promise(r => setTimeout(r, 50))
  expect(onChecking).not.toHaveBeenCalled()
})

it('does not report a finish after unmount', async () => {
  let finish!: (updated: BackupStatus) => void
  vi.mocked(api.telegramAction).mockReturnValue(new Promise(resolve => { finish = resolve }))
  const onChecking = vi.fn()
  const { unmount } = renderHook(() => useTelegramAutoCheck(configured, vi.fn(), onChecking))
  await waitFor(() => expect(api.telegramAction).toHaveBeenCalled())
  expect(onChecking).toHaveBeenCalledWith(true)

  unmount()
  finish({ ...configured, verified: true, connected: true, telegram_verified_at: verifiedAt })
  await new Promise(r => setTimeout(r, 50))
  // Only the "started" call — the page is gone.
  expect(onChecking).toHaveBeenCalledTimes(1)
})

it('drops a result that arrives after unmount', async () => {
  let finish!: (updated: BackupStatus) => void
  vi.mocked(api.telegramAction).mockReturnValue(new Promise(resolve => { finish = resolve }))
  const onResult = vi.fn()
  const { unmount } = renderHook(() => useTelegramAutoCheck(configured, onResult))
  await waitFor(() => expect(api.telegramAction).toHaveBeenCalled())

  unmount()
  finish({ ...configured, verified: true, connected: true, telegram_verified_at: verifiedAt })
  await new Promise(r => setTimeout(r, 50))
  expect(onResult).not.toHaveBeenCalled()
})

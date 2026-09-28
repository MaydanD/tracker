import { API_BASE_URL } from './client'

export interface BackupPreview {
  manifest: {
    format: 'tracker-backup'
    version: number
    application_backup_version: number
    created_at: string
    alembic_revision: string
    counts: Record<string, number>
  }
  validation_token: string
  expires_in_seconds: number
}

async function transfer(path: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init)
  } catch {
    throw new Error('Нет ответа сервера. Если восстановление уже было запущено, проверьте данные после подключения перед повторной попыткой.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { code?: string; message?: string } } | null
    const error = body?.error
    throw new Error(error?.code && ['invalid_backup', 'restore_failed', 'telegram_error'].includes(error.code)
      ? error.message : 'Не удалось выполнить операцию с данными. Попробуйте ещё раз.')
  }
  return response
}

export async function downloadData(kind: 'backup' | 'json' | 'csv'): Promise<void> {
  const response = await transfer(kind === 'backup' ? '/api/backup' : `/api/export/${kind}`)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  const filename = response.headers.get('Content-Disposition')?.match(/filename="([a-zA-Z0-9_.-]+)"/)?.[1]
  anchor.href = url
  anchor.download = filename ?? `tracker-${kind}.${kind === 'json' ? 'json' : 'zip'}`
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  if (kind === 'backup') window.dispatchEvent(new Event('tracker:backup-updated'))
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function validateBackup(file: File): Promise<BackupPreview> {
  const response = await transfer('/api/backup/validate', {
    method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file,
  })
  return response.json() as Promise<BackupPreview>
}

export async function restoreBackup(file: File, token: string): Promise<void> {
  await transfer('/api/backup/restore', {
    method: 'POST', body: file,
    headers: {
      'Content-Type': 'application/zip',
      'X-Tracker-Validation-Token': token,
      'X-Tracker-Confirm-Restore': 'replace',
    },
  })
}

export function reloadAfterRestore(): void {
  try { sessionStorage.setItem('tracker:restore-success', '1') } catch { /* storage may be unavailable */ }
  window.location.reload()
}

export interface BackupStatus {
  last_successful_backup_at: string | null
  last_backup_kind: 'download' | 'telegram' | 'auto-telegram' | null
  last_telegram_backup_at: string | null
  chat_id: string
  auto_enabled: boolean
  connected: boolean
  last_error: string | null
  next_auto_attempt_at: string | null
  token_saved: boolean
  configured: boolean
  /** ISO timestamp of the last successful check or send for the current credentials. */
  telegram_verified_at: string | null
  /** true when configured AND telegram_verified_at is set — survives page reload. */
  verified: boolean
  reminder_due: boolean
  in_progress: boolean
}

export async function fetchBackupStatus(): Promise<BackupStatus> {
  return (await transfer('/api/backup/settings')).json() as Promise<BackupStatus>
}

export async function updateBackupSettings(settings: { token?: string; chat_id: string; auto_enabled: boolean }): Promise<BackupStatus> {
  return (await transfer('/api/backup/settings', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
  })).json() as Promise<BackupStatus>
}

export async function telegramAction(action: 'check' | 'send' | 'auto'): Promise<BackupStatus> {
  const response = await transfer(action === 'auto' ? '/api/backup/auto' : `/api/backup/telegram/${action}`, { method: 'POST' })
  window.dispatchEvent(new Event('tracker:backup-updated'))
  return response.json() as Promise<BackupStatus>
}

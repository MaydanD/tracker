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
    throw new Error(error?.code && ['invalid_backup', 'restore_failed'].includes(error.code)
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

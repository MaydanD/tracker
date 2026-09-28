import { useEffect, useState } from 'react'
import { fetchBackupStatus, type BackupStatus } from '../api/backup'

export function useBackupStatus(calendarDate?: string) {
  const [status, setStatus] = useState<BackupStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    let generation = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    async function refresh() {
      const current = ++generation
      try {
        const result = await fetchBackupStatus()
        if (!active || current !== generation) return
        setStatus(result); setError(null)
        clearTimeout(timer)
        if (result.in_progress) timer = setTimeout(() => void refresh(), 2000)
      } catch {
        if (active && current === generation) setError('Не удалось загрузить состояние резервных копий.')
      }
    }
    void refresh()
    window.addEventListener('focus', refresh)
    window.addEventListener('tracker:backup-updated', refresh)
    return () => {
      active = false; clearTimeout(timer)
      window.removeEventListener('focus', refresh)
      window.removeEventListener('tracker:backup-updated', refresh)
    }
  }, [calendarDate])
  // Allows callers to immediately apply a fresh status received directly from
  // an API response (check / send / save) without waiting for the next fetch
  // triggered by the tracker:backup-updated event.
  return { status, error, applyStatus: setStatus }
}

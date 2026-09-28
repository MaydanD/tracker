import { useState } from 'react'
import { downloadData } from '../api/backup'
import { useBackupStatus } from '../hooks/useBackupStatus'
import { ErrorBanner } from './Feedback'

export function BackupReminder({ today }: { today: string }) {
  const { status } = useBackupStatus(today)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!status?.reminder_due) return null

  async function handleBackup() {
    setBusy(true); setError(null)
    try { await downloadData('backup') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось создать резервную копию.') }
    finally { setBusy(false) }
  }

  return <section className="backup-reminder" aria-label="Резервная копия">
    <div className="backup-reminder__body">
      <p className="backup-reminder__title">Пора сделать резервную копию</p>
      <p className="backup-reminder__text">В этом месяце ещё нет успешной резервной копии.</p>
      <ErrorBanner message={error} />
    </div>
    <div className="backup-reminder__actions">
      <button className="button button--primary" disabled={busy || status.in_progress} onClick={() => void handleBackup()}>
        {busy || status.in_progress ? 'Создаём резервную копию…' : 'Сделать резервную копию'}
      </button>
      <a className="button" href="#/settings?section=backups">Настроить резервные копии</a>
    </div>
  </section>
}

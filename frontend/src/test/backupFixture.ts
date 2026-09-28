import type { BackupStatus } from '../api/backup'
export const backupStatusFixture: BackupStatus = {
  last_successful_backup_at: null, last_backup_kind: null, last_telegram_backup_at: null,
  chat_id: '', auto_enabled: false, connected: false, last_error: null,
  next_auto_attempt_at: null, token_saved: false, configured: false,
  telegram_verified_at: null, verified: false,
  reminder_due: true, in_progress: false,
}

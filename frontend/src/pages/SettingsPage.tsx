import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadData, reloadAfterRestore, restoreBackup, validateBackup, type BackupPreview } from '../api/backup'
import { BackendStatus } from '../components/BackendStatus'
import { useBackendStatus } from '../hooks/useBackendStatus'
import { useBackupStatus } from '../hooks/useBackupStatus'
import { TelegramBackupSettings } from '../components/TelegramBackupSettings'

const labels: Record<string, string> = {
  areas: 'Сферы', habits: 'Привычки', habit_versions: 'Версии настроек',
  habit_entries: 'Записи привычек', daily_states: 'Состояния дня',
  experiments: 'Эксперименты', insight_snapshots: 'Снимки инсайтов',
}

function wasRestored() {
  try { return sessionStorage.getItem('tracker:restore-success') === '1' } catch { return false }
}

export function SettingsPage() {
  // Moved out of the top bar: the connection state is diagnostics, so it lives
  // here where a broken install is actually looked at.
  const backend = useBackendStatus()
  const { status: backupStatus, error: backupError, applyStatus: applyBackupStatus } = useBackupStatus()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<BackupPreview | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState<'checking' | 'restoring' | 'download' | 'telegram' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [restored, setRestored] = useState(wasRestored)
  const generation = useRef(0)
  const picker = useRef<HTMLInputElement>(null)
  // The native input keeps its file-dialog behaviour and stays keyboard
  // reachable; only the visible control around it is styled like the rest of
  // the app, so the restore card never shows a bare browser file widget.
  const pickerDisabled = busy === 'restoring' || busy === 'download' || busy === 'telegram' || backupStatus?.in_progress
  useEffect(() => {
    try { sessionStorage.removeItem('tracker:restore-success') } catch { /* optional flash */ }
    return () => { generation.current += 1 }
  }, [])

  function reset() {
    generation.current += 1
    setFile(null); setPreview(null); setConfirming(false); setError(null); setBusy(null)
    if (picker.current) picker.current.value = ''
  }

  async function selectFile(selected: File | null) {
    reset(); setMessage(null); setRestored(false)
    if (!selected) return
    setFile(selected); setBusy('checking')
    const current = generation.current
    try {
      const result = await validateBackup(selected)
      if (current === generation.current) setPreview(result)
    } catch (cause) {
      if (current === generation.current) setError(cause instanceof Error ? cause.message : 'Не удалось проверить файл.')
    } finally {
      if (current === generation.current) setBusy(null)
    }
  }

  async function download(kind: 'backup' | 'json' | 'csv') {
    setBusy('download'); setError(null); setMessage(null)
    try {
      await downloadData(kind)
      setMessage('Файл подготовлен и передан браузеру для сохранения.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось скачать файл.')
    } finally { setBusy(null) }
  }

  async function apply() {
    if (!file || !preview || !confirming || busy || backupStatus?.in_progress) return
    setBusy('restoring'); setError(null)
    try {
      await restoreBackup(file, preview.validation_token)
      reset(); setRestored(true)
      // Full reload discards all component caches and pending reads.
      reloadAfterRestore()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось восстановить данные.')
      setConfirming(false)
    } finally { setBusy(null) }
  }

  return (
    <section className="page data-settings">
      <h1>Данные и резервные копии</h1>
      <p>Сохраните историю Tracker на своём устройстве или перенесите её на другую установку.</p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {restored && <div>
        <p role="status">Данные восстановлены. Предыдущая копия сохранена на сервере.</p>
        <Link className="button button--primary" to="/">Перейти на главный обзор</Link>
      </div>}
      {/* Cards flow into columns, so the page uses the window instead of one narrow stack. */}
      <div className="data-settings__grid">
        <section className="card card--wide" id="backups" aria-labelledby="backup-title">
          <h2 id="backup-title">Резервные копии</h2>
          <p>Полная история: сферы, привычки и их настройки, отметки, состояния дня, эксперименты и снимки аналитики. Рекорды пересчитаются после восстановления.</p>
          {backupError && <p role="alert">{backupError}</p>}
          {!backupStatus && !backupError && <p>Загружаем настройки резервных копий…</p>}
          {backupStatus && <p>Последняя резервная копия: {backupStatus.last_successful_backup_at ? new Date(backupStatus.last_successful_backup_at).toLocaleString('ru-RU') : 'ещё не создавалась'}</p>}
          {backupStatus?.last_telegram_backup_at && <p>Последняя копия отправлена в Telegram: {new Date(backupStatus.last_telegram_backup_at).toLocaleString('ru-RU')}</p>}
          <button className="button" disabled={busy !== null || backupStatus?.in_progress} onClick={() => void download('backup')}>Создать резервную копию</button>
          {backupStatus && <TelegramBackupSettings status={backupStatus} disabled={busy !== null} onBusy={value => setBusy(value ? 'telegram' : null)} onStatusUpdate={applyBackupStatus} />}
        </section>
        <section className="card card--wide" aria-labelledby="restore-title" aria-busy={busy === 'restoring'}>
          <h2 id="restore-title">Восстановление</h2>
          <p>Выберите ZIP-файл резервной копии Tracker. Содержимое проверяется до замены данных.</p>
          <div className={pickerDisabled ? 'file-picker file-picker--disabled' : 'file-picker'}>
            <input ref={picker} id="restore-backup-file" className="file-picker__input" type="file"
              accept=".zip,application/zip" disabled={pickerDisabled}
              aria-label="Выбрать файл резервной копии"
              onChange={(event) => void selectFile(event.target.files?.[0] ?? null)} />
            <label className="button file-picker__button" htmlFor="restore-backup-file">Выбрать файл</label>
            <span className="file-picker__name" aria-live="polite">{file ? file.name : 'Файл не выбран'}</span>
          </div>
          {busy === 'checking' && <p role="status">Проверяем резервную копию…</p>}
          {preview && <div>
            <h3>Резервная копия от {new Date(preview.manifest.created_at + (/Z|[+-]\d\d:\d\d$/.test(preview.manifest.created_at) ? '' : 'Z')).toLocaleString('ru-RU')}</h3>
            <p>Версия: {preview.manifest.version} · Схема: {preview.manifest.alembic_revision}</p>
            <dl>{Object.entries(labels).map(([key, label]) => <div className="data-count" key={key}>
              <dt>{label}</dt><dd>{preview.manifest.counts[key]}</dd>
            </div>)}</dl>
            <p>Текущие данные Tracker будут заменены данными из резервной копии.</p>
            <p>Перед заменой сервер сохранит резервную копию текущих данных.</p>
          </div>}
          <div className="toolbar">
            <button className="button button--primary" disabled={!preview || busy !== null || confirming || backupStatus?.in_progress}
              onClick={() => setConfirming(true)}>Восстановить данные</button>
            {file && <button className="button" disabled={pickerDisabled} onClick={reset}>Отменить</button>}
          </div>
          {confirming && <section className="restore-confirm" role="alertdialog" aria-labelledby="confirm-title" aria-describedby="confirm-description">
            <h3 id="confirm-title">Подтвердите восстановление</h3>
            <p id="confirm-description">Текущие данные будут заменены. Продолжить?</p>
            <div className="toolbar">
              <button className="button button--primary" disabled={busy !== null || backupStatus?.in_progress} onClick={() => void apply()}>Да, восстановить</button>
              <button className="button" disabled={busy !== null} onClick={() => setConfirming(false)}>Вернуться к проверке</button>
            </div>
          </section>}
          {busy === 'restoring' && <p role="status">Восстанавливаем данные. Дождитесь результата…</p>}
        </section>
        <section className="card" aria-labelledby="connection-title">
          <h2 id="connection-title">Подключение</h2>
          <p>Состояние сервера Tracker и его базы данных. Проверка повторяется автоматически.</p>
          <BackendStatus backend={backend} />
        </section>
        <section className="card" aria-labelledby="export-title">
          <h2 id="export-title">Экспорт</h2>
          <p>Для анализа вне Tracker: JSON или ZIP с отдельными CSV-таблицами. Для восстановления используйте резервную копию.</p>
          <div className="toolbar">
            <button className="button" disabled={busy !== null} onClick={() => void download('json')}>Экспортировать JSON</button>
            <button className="button" disabled={busy !== null} onClick={() => void download('csv')}>Экспортировать CSV</button>
          </div>
        </section>
      </div>
    </section>
  )
}

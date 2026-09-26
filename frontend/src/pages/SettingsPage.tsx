import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadData, reloadAfterRestore, restoreBackup, validateBackup, type BackupPreview } from '../api/backup'

const labels: Record<string, string> = {
  areas: 'Сферы', habits: 'Привычки', habit_versions: 'Версии настроек',
  habit_entries: 'Записи привычек', daily_states: 'Состояния дня',
  experiments: 'Эксперименты', insight_snapshots: 'Снимки инсайтов',
}

function wasRestored() {
  try { return sessionStorage.getItem('tracker:restore-success') === '1' } catch { return false }
}

export function SettingsPage() {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<BackupPreview | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState<'checking' | 'restoring' | 'download' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [restored, setRestored] = useState(wasRestored)
  const generation = useRef(0)
  const picker = useRef<HTMLInputElement>(null)
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
    if (!file || !preview || !confirming || busy) return
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
      <section className="card" aria-labelledby="backup-title">
        <h2 id="backup-title">Резервная копия</h2>
        <p>Полная история: сферы, привычки и их настройки, отметки, состояния дня, эксперименты и снимки инсайтов. Рекорды и достижения пересчитаются после восстановления.</p>
        <button className="button" disabled={busy !== null} onClick={() => void download('backup')}>Скачать резервную копию</button>
      </section>
      <section className="card" aria-labelledby="export-title">
        <h2 id="export-title">Экспорт</h2>
        <p>Для анализа вне Tracker: JSON или ZIP с отдельными CSV-таблицами. Для восстановления используйте резервную копию.</p>
        <div className="toolbar">
          <button className="button" disabled={busy !== null} onClick={() => void download('json')}>Экспортировать JSON</button>
          <button className="button" disabled={busy !== null} onClick={() => void download('csv')}>Экспортировать CSV</button>
        </div>
      </section>
      <section className="card" aria-labelledby="restore-title" aria-busy={busy === 'restoring'}>
        <h2 id="restore-title">Восстановление</h2>
        <label className="field">Выбрать файл резервной копии
          <input ref={picker} type="file" accept=".zip,application/zip" disabled={busy === 'restoring' || busy === 'download'}
            onChange={(event) => void selectFile(event.target.files?.[0] ?? null)} />
        </label>
        {file && <p>Выбран файл: {file.name}</p>}
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
          <button className="button button--primary" disabled={!preview || busy !== null || confirming}
            onClick={() => setConfirming(true)}>Восстановить данные</button>
          {file && <button className="button" disabled={busy === 'restoring'} onClick={reset}>Отменить</button>}
        </div>
        {confirming && <section className="restore-confirm" role="alertdialog" aria-labelledby="confirm-title" aria-describedby="confirm-description">
          <h3 id="confirm-title">Подтвердите восстановление</h3>
          <p id="confirm-description">Текущие данные будут заменены. Продолжить?</p>
          <div className="toolbar">
            <button className="button button--primary" disabled={busy !== null} onClick={() => void apply()}>Да, восстановить</button>
            <button className="button" disabled={busy !== null} onClick={() => setConfirming(false)}>Вернуться к проверке</button>
          </div>
        </section>}
        {busy === 'restoring' && <p role="status">Восстанавливаем данные. Дождитесь результата…</p>}
      </section>
    </section>
  )
}

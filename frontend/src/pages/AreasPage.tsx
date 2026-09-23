import { useState } from 'react'

import { archiveArea, unarchiveArea } from '../api/areas'
import { describeApiError } from '../api/client'
import type { Area } from '../api/types'
import { AreaForm } from '../components/areas/AreaForm'
import { AreaList } from '../components/areas/AreaList'
import { EmptyState, ErrorBanner, LoadingText } from '../components/Feedback'
import { useAreas } from '../hooks/useAreas'

export function AreasPage() {
  const [includeArchived, setIncludeArchived] = useState(false)
  const { areas, loading, error, reload } = useAreas(includeArchived)

  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Area | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  function closeForm() {
    setCreating(false)
    setEditing(null)
  }

  async function handleArchive(area: Area) {
    setBusyId(area.id)
    setActionError(null)
    try {
      await archiveArea(area.id)
      if (editing?.id === area.id) closeForm()
      reload()
    } catch (cause) {
      setActionError(describeApiError(cause))
    } finally {
      setBusyId(null)
    }
  }

  async function handleUnarchive(area: Area) {
    setBusyId(area.id)
    setActionError(null)
    try {
      await unarchiveArea(area.id)
      reload()
    } catch (cause) {
      setActionError(describeApiError(cause))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Сферы</h1>
        <span className="badge">Этап 2</span>
      </header>
      <p className="page__summary">
        Сферы помогают объединять привычки: например, здоровье, развитие, работа
        и быт. Обычно достаточно четырёх–шести сфер. Ненужные сферы можно
        перенести в архив — история сохранится.
      </p>

      <div className="toolbar">
        <button
          type="button"
          className="button button--primary"
          onClick={() => {
            setEditing(null)
            setCreating(true)
          }}
          disabled={creating || editing !== null}
        >
          Новая сфера
        </button>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
          />
          <span>Показывать архивные</span>
        </label>
      </div>

      <ErrorBanner message={actionError} />
      <ErrorBanner message={error} />

      {creating || editing ? (
        <AreaForm
          key={editing?.id ?? 'new'}
          area={editing}
          onSaved={() => {
            closeForm()
            reload()
          }}
          onCancel={closeForm}
        />
      ) : null}

      {loading ? (
        <LoadingText>Загрузка сфер…</LoadingText>
      ) : areas.length === 0 ? (
        <EmptyState>
          {includeArchived
            ? 'Сфер пока нет.'
            : 'Нет активных сфер. Создайте сферу, чтобы добавить привычки.'}
        </EmptyState>
      ) : (
        <AreaList
          areas={areas}
          busyId={busyId}
          editingId={editing?.id ?? null}
          onEdit={(area) => {
            setCreating(false)
            setEditing(area)
          }}
          onArchive={handleArchive}
          onUnarchive={handleUnarchive}
        />
      )}
    </section>
  )
}

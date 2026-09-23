import type { Area } from '../../api/types'

export interface AreaListProps {
  areas: Area[]
  onEdit: (area: Area) => void
  onArchive: (area: Area) => void
  onUnarchive: (area: Area) => void
  /** Area currently being archived/restored, to disable its own buttons. */
  busyId?: number | null
  editingId?: number | null
}

export function AreaList({
  areas,
  onEdit,
  onArchive,
  onUnarchive,
  busyId = null,
  editingId = null,
}: AreaListProps) {
  return (
    <ul className="list">
      {areas.map((area) => {
        const busy = busyId === area.id
        return (
          <li
            key={area.id}
            className={`list__row${editingId === area.id ? ' list__row--active' : ''}`}
          >
            <span
              className="swatch"
              style={{ backgroundColor: area.color }}
              aria-hidden="true"
            />
            <span className="list__main">
              <span className="list__title">{area.name}</span>
              <span className="list__meta">
                {area.color}
                {area.is_archived ? ' · в архиве' : ''}
              </span>
            </span>

            <span className="list__actions">
              <button
                type="button"
                className="button button--small"
                onClick={() => onEdit(area)}
                disabled={busy}
              >
                Изменить
              </button>
              {area.is_archived ? (
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => onUnarchive(area)}
                  disabled={busy}
                >
                  Восстановить
                </button>
              ) : (
                <button
                  type="button"
                  className="button button--small"
                  onClick={() => onArchive(area)}
                  disabled={busy}
                >
                  В архив
                </button>
              )}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

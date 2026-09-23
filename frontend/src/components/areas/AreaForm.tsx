import { useState, type FormEvent } from 'react'

import { createArea, updateArea } from '../../api/areas'
import { describeApiError } from '../../api/client'
import type { Area } from '../../api/types'
import { ErrorBanner } from '../Feedback'

/** Matches the API default so a new area always starts from a visible colour. */
const DEFAULT_COLOR = '#4a7cc7'

export interface AreaFormProps {
  /** The area being edited, or null when creating a new one. */
  area?: Area | null
  onSaved: (area: Area) => void
  onCancel: () => void
}

export function AreaForm({ area = null, onSaved, onCancel }: AreaFormProps) {
  const [name, setName] = useState(area?.name ?? '')
  const [color, setColor] = useState(area?.color ?? DEFAULT_COLOR)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedName = name.trim()
    if (trimmedName === '') {
      setError('Введите название сферы.')
      return
    }

    setSaving(true)
    setError(null)
    try {
      // Values are only cleared on success, so a rejected submission keeps the
      // user's input on screen.
      const saved = area
        ? await updateArea(area.id, { name: trimmedName, color })
        : await createArea({ name: trimmedName, color })
      onSaved(saved)
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit} noValidate>
      <h3 className="card__title">{area ? `Изменить: ${area.name}` : 'Новая сфера'}</h3>

      <div className="field">
        <label className="field__label" htmlFor="area-name">
          Название
        </label>
        <input
          id="area-name"
          className="field__input"
          value={name}
          maxLength={80}
          onChange={(event) => setName(event.target.value)}
        />
      </div>

      <div className="field">
        <label className="field__label" htmlFor="area-color">
          Цвет
        </label>
        <div className="field__row">
          <input
            id="area-color"
            className="field__color"
            type="color"
            value={color}
            onChange={(event) => setColor(event.target.value)}
          />
          <span className="field__hint">{color}</span>
        </div>
      </div>

      <ErrorBanner message={error} />

      <div className="card__actions">
        <button type="submit" className="button button--primary" disabled={saving}>
          {saving ? 'Сохранение…' : area ? 'Сохранить изменения' : 'Создать сферу'}
        </button>
        <button type="button" className="button" onClick={onCancel} disabled={saving}>
          Отмена
        </button>
      </div>
    </form>
  )
}

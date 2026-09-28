/**
 * The "OK" button that doubles as a 5-second progress indicator.
 *
 * A CSS custom property `--ok-progress` drives a linear-gradient fill that
 * grows from left to right as the countdown proceeds. The user sees the button
 * filling with blue — no separate text countdown is needed.
 *
 * Clicking before the fill completes confirms immediately.
 *
 * `disabled` is only ever used while the newest value is still being saved (or
 * that save failed): the button stays on screen at exactly the same size so the
 * card cannot jump, but a click can never complete stale data.
 */
export function OkButton({
  progress,
  counting = false,
  inline = false,
  onConfirm,
  disabled = false,
  locked = false,
  onToggleLock,
}: {
  progress: number
  /** False while the countdown waits for the user to leave the card. */
  counting?: boolean
  /** Share a row with other controls instead of owning a full-width row. */
  inline?: boolean
  onConfirm: () => void
  /** True while a manual confirmation would act on not-yet-stored data. */
  disabled?: boolean
  locked?: boolean
  onToggleLock?: () => void
}) {
  const pct = Math.round(progress * 100)

  return (
    <div
      className={`ccard__readiness${inline ? ' ccard__readiness--inline' : ''}`}
      data-readiness-actions
    >
    <button
      type="button"
      className="ok-btn"
      style={{ '--ok-progress': `${pct}%` } as React.CSSProperties}
      onClick={onConfirm}
      disabled={disabled}
      aria-label={counting
        ? `ОК — подтвердить (${100 - pct}% до автоподтверждения)`
        : 'ОК — подтвердить'}
    >
      ОК
    </button>
    {onToggleLock ? (
      <button type="button" className="ccard__lock" aria-pressed={locked}
        aria-label={locked ? 'Открыть замок — запустить отсчёт' : 'Закрыть замок — оставить карточку'}
        title={locked ? 'Карточка закреплена' : 'Оставить карточку наверху'} onClick={onToggleLock}>
        {locked ? '🔒' : '🔓'}
      </button>
    ) : null}
    </div>
  )
}

/**
 * The "OK" button that doubles as a 5-second progress indicator.
 *
 * A CSS custom property `--ok-progress` drives a linear-gradient fill that
 * grows from left to right as the countdown proceeds. The user sees the button
 * filling with blue — no separate text countdown is needed.
 *
 * Clicking before the fill completes confirms immediately.
 */
export function OkButton({
  progress,
  onConfirm,
  locked = false,
  onToggleLock,
}: {
  progress: number
  onConfirm: () => void
  locked?: boolean
  onToggleLock?: () => void
}) {
  const pct = Math.round(progress * 100)

  return (
    <div className="ccard__readiness" data-readiness-actions>
    <button
      type="button"
      className="ok-btn"
      style={{ '--ok-progress': `${pct}%` } as React.CSSProperties}
      onClick={onConfirm}
      aria-label={`ОК — подтвердить (${100 - pct}% до автоподтверждения)`}
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

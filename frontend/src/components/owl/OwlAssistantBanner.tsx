import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import type { OwlState, OwlTone } from '../../api/owl'
import {
  dismiss as persistDismiss,
  isDismissed,
  recordSarcasm,
  sarcasmCoolingDown,
  type KeyValueStorage,
} from '../../utils/owlSession'
import { resolveOwlAsset } from './owlAssets'

interface Props {
  /** The single state chosen by the backend, or null when nothing applies. */
  state: OwlState | null
  /** Inject a storage for tests; defaults to the browser session storage. */
  storage?: KeyValueStorage
  /** Dashboard keeps the mascot in its own column instead of inside the message. */
  variant?: 'default' | 'hero' | 'dashboard'
  action?: ReactNode
}

interface Shown {
  tone: OwlTone
  line1: string
}

/**
 * The contextual Owl: a non-modal message, optionally paired with its existing PNG.
 */
export function OwlAssistantBanner({ state, storage, variant = 'default', action }: Props) {
  const [dismissed, setDismissed] = useState(false)
  const [coolingDown, setCoolingDown] = useState(false)
  const hasAction = action !== null && action !== undefined

  const fingerprint = state?.fingerprint ?? ''
  const tone = state?.tone ?? null

  useEffect(() => {
    setDismissed(state !== null && state.dismissible && isDismissed(fingerprint, storage))
    if (tone === 'sarcastic') {
      const cooling = sarcasmCoolingDown(Date.now(), storage)
      setCoolingDown(cooling)
      // Showing an aggressive state starts the cooldown for the next one; a
      // re-render (or a downgraded message) must not keep extending it.
      if (!cooling) recordSarcasm(Date.now(), storage)
    } else {
      setCoolingDown(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fingerprint, tone, storage])

  if (state === null || (state.dismissible && dismissed && !hasAction)) return null

  const shown: Shown =
    state.tone === 'sarcastic' && coolingDown
      ? { tone: 'cautionary', line1: state.fallback_line1 ?? state.caption_line1 }
      : { tone: state.tone, line1: state.caption_line1 }

  const handleDismiss = () => {
    if (!state.dismissible) return
    persistDismiss(state.fingerprint, storage)
    setDismissed(true)
  }

  return (
    <section
      className={`owl-banner owl-banner--${shown.tone}${variant === 'hero' ? ' owl-banner--hero' : ''}${variant === 'dashboard' ? ' owl-banner--dashboard' : ''}`}
      aria-label="Сова-помощник"
      data-testid="owl-banner"
      data-tone={shown.tone}
    >
      {variant !== 'dashboard' ? (
        <img className="owl-banner__image" src={resolveOwlAsset(state.asset_key)} alt="Сова-помощник" />
      ) : null}
      <div className="owl-banner__body">
        <p className="owl-banner__lead">{shown.line1}</p>
        <p className="owl-banner__fact">{state.caption_line2}</p>
        {action}
      </div>
      {state.dismissible && !hasAction ? (
        <button type="button" className="owl-banner__dismiss button button--small" onClick={handleDismiss}>
          Скрыть
        </button>
      ) : null}
    </section>
  )
}

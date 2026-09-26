import { useEffect, useState } from 'react'

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
}

interface Shown {
  tone: OwlTone
  line1: string
}

/**
 * The contextual Owl: a compact, non-modal banner at the top of the content
 * area. It shows one existing PNG, one emotional line and one factual line.
 */
export function OwlAssistantBanner({ state, storage }: Props) {
  const [dismissed, setDismissed] = useState(false)
  const [coolingDown, setCoolingDown] = useState(false)

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

  if (state === null || (state.dismissible && dismissed)) return null

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
      className={`owl-banner owl-banner--${shown.tone}`}
      aria-label="Сова-помощник"
      data-testid="owl-banner"
      data-tone={shown.tone}
    >
      <img className="owl-banner__image" src={resolveOwlAsset(state.asset_key)} alt="Сова-помощник" />
      <div className="owl-banner__body">
        <p className="owl-banner__lead">{shown.line1}</p>
        <p className="owl-banner__fact">{state.caption_line2}</p>
      </div>
      {state.dismissible ? (
        <button type="button" className="owl-banner__dismiss button button--small" onClick={handleDismiss}>
          Скрыть
        </button>
      ) : null}
    </section>
  )
}

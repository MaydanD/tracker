import { useEffect, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'

import { resolveOwlAsset } from './owlAssets'
import { getOwlSnapshot, refreshOwl, subscribeOwl } from './owlStore'

/**
 * The always-visible mascot: a small version of the current Owl in the top bar.
 *
 * It uses the same six PNGs and the same backend-chosen state as the contextual
 * banner, so the picture always matches the user's current situation. Clicking
 * it returns to the main screen.
 */
export function OwlLogo() {
  const owl = useSyncExternalStore(subscribeOwl, getOwlSnapshot)

  // If no page has published an Owl yet (a screen without its own Owl), ask the
  // dashboard once so the header is never left with a blank mascot.
  useEffect(() => {
    if (getOwlSnapshot() === null) refreshOwl()
  }, [])

  return (
    <Link to="/" className="owl-logo" title="На главную" aria-label="Сова Tracker — на главную">
      <img
        className="owl-logo__image"
        src={resolveOwlAsset(owl?.asset_key ?? 'owl_pending')}
        alt=""
      />
    </Link>
  )
}

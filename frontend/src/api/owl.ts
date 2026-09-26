/**
 * Stage 9 Owl contract.
 *
 * The backend selects exactly one state; the frontend only *renders* it and
 * owns the light dismiss/cooldown UX. Nothing here recomputes a statistic or
 * picks a scenario from raw numbers.
 */

export type OwlTone = 'celebratory' | 'supportive' | 'neutral' | 'cautionary' | 'sarcastic'
export type OwlContext = 'dashboard' | 'insights' | 'experiments'

/** Asset keys map to the canonical PNGs in the repository `owl/` directory. */
export type OwlAssetKey =
  | 'owl_pending'
  | 'owl_failed'
  | 'owl_all_done'
  | 'owl_insight'
  | 'owl_many_misses'
  | 'owl_record'

export interface OwlState {
  owl_id: string
  asset_key: OwlAssetKey
  tone: OwlTone
  priority: number
  caption_line1: string
  caption_line2: string
  dismissible: boolean
  fingerprint: string
  context: OwlContext
  /** Non-sarcastic replacement used by the local sarcasm cooldown. */
  fallback_line1: string | null
}

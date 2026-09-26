/**
 * The six canonical Owl PNGs, kept once in the repository `owl/` directory.
 *
 * They are imported (not copied) so there is a single source of truth and the
 * bundler emits them with hashed, relative URLs that also work when the desktop
 * build loads the SPA from disk. No new images are generated for this stage:
 * every analysis-quality state reuses `owl_insight`.
 */

import allDone from '../../../../owl/owl_all_done.png'
import failed from '../../../../owl/owl_failed.png'
import insight from '../../../../owl/owl_insight.png'
import manyMisses from '../../../../owl/owl_many_misses.png'
import pending from '../../../../owl/owl_pending.png'
import record from '../../../../owl/owl_record.png'

import type { OwlAssetKey } from '../../api/owl'

export const OWL_ASSETS: Record<OwlAssetKey, string> = {
  owl_pending: pending,
  owl_failed: failed,
  owl_all_done: allDone,
  owl_insight: insight,
  owl_many_misses: manyMisses,
  owl_record: record,
}

/** Resolve a backend asset key; unknown keys fall back to the neutral owl. */
export function resolveOwlAsset(key: string): string {
  return OWL_ASSETS[key as OwlAssetKey] ?? OWL_ASSETS.owl_insight
}

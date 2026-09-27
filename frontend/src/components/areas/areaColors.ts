/**
 * Curated palette for life areas.
 *
 * Areas used to share one default blue, which made a fresh list of areas look
 * nearly identical. New areas now start from this small, hand-picked palette —
 * distinct hues, each readable as a swatch on the light theme — and the user can
 * still change the colour by hand at any time.
 *
 * The choice is made once, when the area is created, and then stored on the
 * area; it is never recomputed on render. No free-form random RGB is generated.
 */
export const AREA_COLOR_PALETTE = [
  '#3f6fd8', // синий
  '#2f9e5f', // зелёный
  '#c2540a', // оранжевый
  '#8b46c9', // фиолетовый
  '#c23b6e', // малиновый
  '#0f8a8a', // бирюзовый
  '#b5891b', // золотистый
  '#5b6b7a', // графитовый
] as const

/**
 * Pick a palette colour for a new area.
 *
 * `existingColors` are the colours already in use, most recently used last. The
 * most recent colour is excluded from the draw so two areas created in a row do
 * not come out identical; the rest is a real random pick, so the result is
 * varied but always from the palette.
 */
export function pickAreaColor(existingColors: readonly string[] = []): string {
  const last = existingColors.at(-1)?.toLowerCase()
  const candidates = AREA_COLOR_PALETTE.filter((color) => color.toLowerCase() !== last)
  const pool = candidates.length > 0 ? candidates : [...AREA_COLOR_PALETTE]
  return pool[Math.floor(Math.random() * pool.length)] ?? AREA_COLOR_PALETTE[0]
}

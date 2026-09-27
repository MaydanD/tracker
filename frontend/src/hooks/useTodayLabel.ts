import { useEffect, useState } from 'react'

import { formatDayMonthLabel } from '../utils/dateUtils'

/** Milliseconds until the next local midnight, plus a small safety margin. */
function untilNextMidnight(now: Date): number {
  const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
  return next.getTime() - now.getTime() + 1000
}

/**
 * Today's date for the header, e.g. «27 сентября».
 *
 * The label is the browser's local date and carries no year: the header answers
 * "what day is it?" and the year is noise there. One timer re-arms for the next
 * local midnight, so the label rolls over on its own — no reload and no backend
 * round-trip. A tab that slept through midnight is re-checked when it is looked
 * at again, because background timers can be throttled.
 */
export function useTodayLabel(): string {
  const [label, setLabel] = useState(() => formatDayMonthLabel())

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined

    const refresh = () => {
      setLabel(formatDayMonthLabel())
      if (timer !== undefined) clearTimeout(timer)
      timer = setTimeout(refresh, untilNextMidnight(new Date()))
    }

    const onVisibilityChange = () => {
      if (!document.hidden) refresh()
    }

    refresh()
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      if (timer !== undefined) clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [])

  return label
}

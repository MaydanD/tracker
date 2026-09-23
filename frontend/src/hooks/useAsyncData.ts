import { useCallback, useEffect, useRef, useState } from 'react'

import { describeApiError } from '../api/client'

export interface AsyncData<T> {
  data: T | null
  error: string | null
  loading: boolean
  /** Refetch, for example after a create, archive or edit. */
  reload: () => void
}

/**
 * Load something from the API and keep it in component state.
 *
 * Этап 2 has two resource types (areas, habits) with identical loading and
 * error handling, which is the whole reason this exists. There is no cache and
 * no global store: reads are cheap and the dataset is one user's configuration.
 *
 * `deps` must have a stable length per call site, exactly like a `useEffect`
 * dependency list, because it is spread into one.
 */
export function useAsyncData<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
): AsyncData<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [token, setToken] = useState(0)

  // Held in a ref so callers can pass an inline loader without re-running the
  // effect on every render.
  const loadRef = useRef(load)
  loadRef.current = load

  const reload = useCallback(() => setToken((value) => value + 1), [])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)

    loadRef.current(controller.signal)
      .then((result) => {
        if (!active) return
        setData(result)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (!active || controller.signal.aborted) return
        setError(describeApiError(cause))
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, ...deps])

  return { data, error, loading, reload }
}

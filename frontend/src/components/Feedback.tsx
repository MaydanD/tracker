import type { ReactNode } from 'react'

/** A failure the user should read before anything else on the screen. */
export function ErrorBanner({ message }: { message: string | null }) {
  if (message === null || message === '') return null
  return (
    <p className="banner banner--error" role="alert">
      {message}
    </p>
  )
}

/** Neutral supporting information, such as "select an area first". */
export function InfoBanner({ children }: { children: ReactNode }) {
  return <p className="banner banner--info">{children}</p>
}

export function LoadingText({ children }: { children: ReactNode }) {
  return <p className="loading">{children}</p>
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>
}

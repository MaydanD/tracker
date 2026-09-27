import { Navigate } from 'react-router-dom'

/** Keep existing bookmarks working; area management now lives with habits. */
export function AreasPage() {
  return <Navigate to="/habits" replace />
}

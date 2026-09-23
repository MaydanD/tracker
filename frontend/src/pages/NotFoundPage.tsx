import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Screen not found</h1>
      </header>
      <p className="page__summary">
        That route does not exist in Tracker yet.
      </p>
      <p>
        <Link to="/">Back to the dashboard</Link>
      </p>
    </section>
  )
}

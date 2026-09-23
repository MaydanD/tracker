import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Страница не найдена</h1>
      </header>
      <p className="page__summary">
        В Tracker пока нет такой страницы.
      </p>
      <p>
        <Link to="/">Вернуться к обзору</Link>
      </p>
    </section>
  )
}

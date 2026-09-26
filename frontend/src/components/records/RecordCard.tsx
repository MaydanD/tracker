export interface RecordCardProps {
  title: string
  /** The headline value, already formatted. */
  value: string
  /** Who or what the record belongs to. */
  context?: string | null
  /** When it happened, or how complete the data is. */
  meta?: string | null
  /** A short extra line, e.g. how many days tied the record. */
  footnote?: string | null
  tone?: 'default' | 'accent'
}

/**
 * One personal record: a name, one big value and the facts behind it. Records are
 * dynamic maxima, so nothing here claims to be permanent.
 */
export function RecordCard({
  title, value, context = null, meta = null, footnote = null, tone = 'default',
}: RecordCardProps) {
  return (
    <article className={`record-card record-card--${tone}`}>
      <h3 className="record-card__title">{title}</h3>
      <p className="record-card__value">{value}</p>
      {context !== null ? <p className="record-card__context">{context}</p> : null}
      {meta !== null ? <p className="record-card__meta">{meta}</p> : null}
      {footnote !== null ? <p className="record-card__footnote">{footnote}</p> : null}
    </article>
  )
}

import type { InsightCandidateRead } from '../../api/insights'
import {
  CONFIDENCE_LABELS,
  STATUS_LABELS,
  VERDICT_LABELS,
  formatCount,
  formatRatio,
} from './labels'

const VISIBLE_CAVEATS = 3

interface Props {
  insight: InsightCandidateRead
  selected: boolean
  onOpen: (insight: InsightCandidateRead) => void
}

/** One relationship family, as the feed shows it: statement, chips, limitations. */
export function InsightCard({ insight, selected, onOpen }: Props) {
  const confidence = insight.confidence.level
  return (
    <article
      className={selected ? 'insight-card insight-card--selected' : 'insight-card'}
      aria-label={`${insight.x.label} — ${insight.y.label}`}
      data-testid={`insight-${insight.fingerprint.slice(0, 8)}`}
    >
      <header className="insight-card__header">
        <h3 className="insight-card__pair">
          <span className="insight-card__variable">{insight.x.label}</span>
          <span aria-hidden="true">{insight.lag === 0 ? ' ↔ ' : insight.lag > 0 ? ' → ' : ' ← '}</span>
          <span className="insight-card__variable">{insight.y.label}</span>
        </h3>
        <span className={`insight-chip insight-chip--status-${insight.status}`}>
          {STATUS_LABELS[insight.status]}
        </span>
      </header>

      <p className="insight-card__statement">{insight.text.full}</p>

      <ul className="insight-card__chips">
        <li className="insight-chip">{insight.text.timing}</li>
        {confidence !== null ? (
          <li className="insight-chip insight-chip--confidence">{CONFIDENCE_LABELS[confidence]}</li>
        ) : null}
        <li className="insight-chip">{VERDICT_LABELS[insight.guardrail.verdict]}</li>
        <li className="insight-chip">
          {`Наблюдений: ${formatCount(insight.evidence.sample.n)}`}
        </li>
        <li className="insight-chip">
          {`Покрытие: ${formatRatio(insight.evidence.coverage.pair_coverage)}`}
        </li>
      </ul>

      {insight.caveats.length > 0 ? (
        <ul className="insight-card__caveats">
          {insight.caveats.slice(0, VISIBLE_CAVEATS).map((caveat) => (
            <li key={caveat.code} className={`insight-caveat insight-caveat--${caveat.severity}`}>
              {caveat.label}
            </li>
          ))}
          {insight.caveats.length > VISIBLE_CAVEATS ? (
            <li className="insight-caveat insight-caveat--info">
              {`И ещё ${insight.caveats.length - VISIBLE_CAVEATS}`}
            </li>
          ) : null}
        </ul>
      ) : null}

      <footer className="insight-card__footer">
        <button
          type="button"
          className="button button--small"
          onClick={() => onOpen(insight)}
          aria-expanded={selected}
        >
          Подробнее о доказательствах
        </button>
        {insight.first_seen !== null ? (
          <span className="insight-card__first-seen">{`Наблюдается с ${insight.first_seen}`}</span>
        ) : null}
      </footer>
    </article>
  )
}

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

/**
 * One relationship family, as the feed shows it.
 *
 * The layout reads in the order a person does: the human conclusion first, then
 * the linked variables and evidence level as quiet context, then limitations.
 * Numbers never compete with the sentence that explains them.
 */
export function InsightCard({ insight, selected, onOpen }: Props) {
  const confidence = insight.confidence.level
  const direction = insight.lag === 0 ? '↔' : insight.lag > 0 ? '→' : '←'

  return (
    <article
      className={selected ? 'insight-card insight-card--selected' : 'insight-card'}
      aria-label={`${insight.x.label} — ${insight.y.label}`}
      data-testid={`insight-${insight.fingerprint.slice(0, 8)}`}
    >
      <div className="insight-card__topline">
        <p className="insight-card__pair">
          <span className="insight-card__variable">{insight.x.label}</span>
          <span className="insight-card__arrow" aria-hidden="true">{` ${direction} `}</span>
          <span className="insight-card__variable">{insight.y.label}</span>
        </p>
        <span className={`insight-chip insight-chip--status-${insight.status}`}>
          {STATUS_LABELS[insight.status]}
        </span>
      </div>

      <p className="insight-card__statement">{insight.text.full}</p>

      <ul className="insight-card__chips">
        <li className="insight-chip insight-chip--muted">{insight.text.timing}</li>
        {confidence !== null ? (
          <li className="insight-chip insight-chip--confidence">{CONFIDENCE_LABELS[confidence]}</li>
        ) : null}
        <li className="insight-chip insight-chip--muted">{VERDICT_LABELS[insight.guardrail.verdict]}</li>
        <li className="insight-chip insight-chip--muted">{`Наблюдений: ${formatCount(insight.evidence.sample.n)}`}</li>
        <li className="insight-chip insight-chip--muted">{`Покрытие: ${formatRatio(insight.evidence.coverage.pair_coverage)}`}</li>
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
        {insight.first_seen !== null ? (
          <span className="insight-card__first-seen">{`Наблюдается с ${insight.first_seen}`}</span>
        ) : <span />}
        <button
          type="button"
          className="button button--small"
          onClick={() => onOpen(insight)}
          aria-expanded={selected}
        >
          Подробнее о доказательствах
        </button>
      </footer>
    </article>
  )
}

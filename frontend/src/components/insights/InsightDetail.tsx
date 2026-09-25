import type {
  InsightAnalyticsRead,
  InsightCandidateRead,
  InsightDetailRead,
  InsightSnapshotRead,
} from '../../api/insights'
import { LoadingText } from '../Feedback'
import { BooleanStrip, ChartFigure, GroupBars, LagProfileChart, ScatterChart, SegmentChart, SeriesChart } from './charts'
import {
  CHECK_LABELS,
  CHECK_STATUS_LABELS,
  CONFIDENCE_EXPLANATIONS,
  CONFIDENCE_LABELS,
  CONFIDENCE_NONE_EXPLANATION,
  DIRECTION_LABELS,
  METHOD_AGREEMENT_LABELS,
  METHOD_LABELS,
  RELATION_TO_FULL_LABELS,
  SEGMENT_LABELS,
  STATUS_LABELS,
  STRENGTH_LABELS,
  VERDICT_LABELS,
  WEEKDAY_STATUS_LABELS,
  formatCoefficient,
  formatCount,
  formatNumber,
  formatRatio,
} from './labels'

interface Props {
  detail: InsightDetailRead | null
  candidate: InsightCandidateRead
  analytics: InsightAnalyticsRead | null
  loading: boolean
  error: string | null
  refreshing: boolean
  onRefresh: () => void
}

function summaryFor(detail: InsightDetailRead, key: string): string {
  return detail.chart.summaries.find((item) => item.key === key)?.summary ?? ''
}

function HistoryRow({ snapshot }: { snapshot: InsightSnapshotRead }) {
  return (
    <tr>
      <td>{snapshot.evaluated_on}</td>
      <td>
        <span className={`insight-chip insight-chip--status-${snapshot.status}`}>
          {STATUS_LABELS[snapshot.status]}
        </span>
      </td>
      <td>
        {snapshot.confidence !== null
          ? CONFIDENCE_LABELS[snapshot.confidence]
          : 'не определён'}
      </td>
      <td>{VERDICT_LABELS[snapshot.guardrail_verdict]}</td>
      <td>{formatCoefficient(snapshot.coefficient)}</td>
      <td>{formatCount(snapshot.n)}</td>
      <td>{formatRatio(snapshot.pair_coverage)}</td>
      <td>{`${snapshot.x_label}${snapshot.x_archived && !snapshot.x_label.endsWith('(в архиве)') ? ' (в архиве)' : ''} ${snapshot.lag === 0 ? '↔' : snapshot.lag > 0 ? '→' : '←'} ${snapshot.y_label}${snapshot.y_archived && !snapshot.y_label.endsWith('(в архиве)') ? ' (в архиве)' : ''}`}</td>
    </tr>
  )
}

/**
 * Everything a card can honestly show: the same verdict, the whole evidence, the
 * charts and (when a snapshot exists) how the evidence changed over time.
 */
export function InsightDetail({
  detail,
  candidate,
  loading,
  error,
  refreshing,
  onRefresh,
}: Props) {
  const evidence = candidate.evidence
  const group = evidence.effect.group
  const exposure = group?.boolean_side === 'y' ? candidate.y : candidate.x

  return (
    <section className="insight-detail" aria-label="Подробности наблюдения" data-testid="insight-detail">
      <header className="insight-detail__header">
        <h2 className="insight-detail__title">{candidate.text.full}</h2>
        <ul className="insight-card__chips">
          <li className={`insight-chip insight-chip--status-${candidate.status}`}>
            {STATUS_LABELS[candidate.status]}
          </li>
          <li className="insight-chip">{candidate.text.timing}</li>
          <li className="insight-chip">{VERDICT_LABELS[candidate.guardrail.verdict]}</li>
        </ul>
        <button type="button" className="button button--small" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? 'Обновляем историю…' : 'Обновить историю оценок'}
        </button>
      </header>

      {error !== null ? (
        <p className="banner banner--error" role="alert">
          {error}
        </p>
      ) : null}

      {loading && detail === null ? <LoadingText>Загрузка доказательств…</LoadingText> : null}

      <section className="insight-detail__block" aria-label="Уровень подтверждённости">
        <h3 className="card__title">Уровень подтверждённости</h3>
        <p className="insight-detail__text">
          {candidate.confidence.level !== null
            ? CONFIDENCE_EXPLANATIONS[candidate.confidence.level]
            : CONFIDENCE_NONE_EXPLANATION}
        </p>
        <p className="insight-detail__hint">{candidate.guardrail.confidence_capped
          ? 'Уровень ограничен результатом статистических проверок.'
          : 'Уровень рассчитан по вашим данным, а не по общим нормам.'}</p>
      </section>

      <section className="insight-detail__block" aria-label="Доказательная база">
        <h3 className="card__title">Подробнее о доказательствах</h3>
        <dl className="insight-evidence">
          <div>
            <dt>Период</dt>
            <dd>{`${candidate.target_period.start} — ${candidate.target_period.end}`}</dd>
          </div>
          <div>
            <dt>Задержка</dt>
            <dd>{candidate.text.timing}</dd>
          </div>
          <div>
            <dt>Метод</dt>
            <dd>{candidate.relationship.method !== null
              ? METHOD_LABELS[candidate.relationship.method] ?? candidate.relationship.method
              : '—'}</dd>
          </div>
          <div>
            <dt>Величина связи</dt>
            <dd>{`${formatCoefficient(candidate.relationship.coefficient)} (${DIRECTION_LABELS[candidate.relationship.direction ?? ''] ?? '—'})`}</dd>
          </div>
          <div>
            <dt>Сила связи</dt>
            <dd>{candidate.relationship.strength !== null
              ? STRENGTH_LABELS[candidate.relationship.strength] ?? candidate.relationship.strength
              : '—'}</dd>
          </div>
          <div>
            <dt>Наблюдений</dt>
            <dd>{`${formatCount(evidence.sample.n)} из ${formatCount(evidence.sample.eligible_count)} подходящих дней`}</dd>
          </div>
          <div>
            <dt>Покрытие</dt>
            <dd>{`${formatRatio(evidence.coverage.pair_coverage)} (минимум на отрезке: ${formatRatio(evidence.coverage.minimum_segment_coverage)})`}</dd>
          </div>
          <div>
            <dt>Минимальная значимая величина</dt>
            <dd>{formatNumber(evidence.effect.minimum_absolute_effect)}</dd>
          </div>
          <div>
            <dt>Контроль ложных открытий</dt>
            <dd>
              {candidate.guardrail.adjusted_q_value !== null
                ? `поправка ${formatNumber(candidate.guardrail.adjusted_q_value, 4)} при пороге ${formatNumber(candidate.guardrail.threshold)}`
                : 'не применяется'}
              {` · проверено ${formatCount(candidate.guardrail.tested_size)} из ${formatCount(candidate.guardrail.family_size)}`}
            </dd>
          </div>
          <div>
            <dt>Контроль дня недели</dt>
            <dd>
              {`${WEEKDAY_STATUS_LABELS[evidence.weekday.status] ?? evidence.weekday.status}`}
              {evidence.weekday.adjusted_coefficient !== null
                ? ` · с поправкой ${formatCoefficient(evidence.weekday.adjusted_coefficient)}`
                : ''}
            </dd>
          </div>
          <div>
            <dt>Методы расчёта</dt>
            <dd>
              {evidence.methods.methods.length > 0
                ? `${evidence.methods.methods.map((method) => METHOD_LABELS[method] ?? method).join(', ')} (${METHOD_AGREEMENT_LABELS[evidence.methods.agreement] ?? evidence.methods.agreement})`
                : '—'}
            </dd>
          </div>
          <div>
            <dt>Первый снимок</dt>
            <dd>{candidate.first_seen ?? 'ещё не сохранялся'}</dd>
          </div>
          {group !== null ? <>
            <div><dt>Группа «Да»</dt><dd>{`${formatCount(group.true_count)} наблюдений; среднее ${formatNumber(group.true_mean)}; медиана ${formatNumber(group.true_median)}`}</dd></div>
            <div><dt>Группа «Нет»</dt><dd>{`${formatCount(group.false_count)} наблюдений; среднее ${formatNumber(group.false_mean)}; медиана ${formatNumber(group.false_median)}`}</dd></div>
            <div><dt>Баланс групп</dt><dd>{`Меньшая группа: ${formatCount(group.minority_count)}, доля ${formatRatio(group.minority_share)}`}</dd></div>
            <div><dt>Разница средних и размер эффекта</dt><dd>{`${formatNumber(group.absolute_mean_difference)}; стандартизированная разница ${formatNumber(group.cohens_d)}`}</dd></div>
          </> : null}
        </dl>

        <div className="insight-table-scroll" role="region" aria-label="Таблица доказательств" tabIndex={0}><table className="insight-table">
          <caption className="insight-table__caption">Проверки статистических правил</caption>
          <thead>
            <tr>
              <th scope="col">Проверка</th>
              <th scope="col">Результат</th>
              <th scope="col">Значение</th>
              <th scope="col">Порог</th>
            </tr>
          </thead>
          <tbody>
            {evidence.checks.map((check) => (
              <tr key={check.name}>
                <th scope="row">{CHECK_LABELS[check.name] ?? check.name}</th>
                <td>{CHECK_STATUS_LABELS[check.status] ?? check.status}</td>
                <td>{formatNumber(check.observed)}</td>
                <td>{formatNumber(check.threshold)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </section>

      {detail !== null ? (
        <section className="insight-detail__block" aria-label="Графики">
          <h3 className="card__title">Графики</h3>
          <div className="insight-charts">
            {candidate.x.type === 'boolean' ? (
              <BooleanStrip series={detail.chart.x} title={`Отметки: ${candidate.x.label}`}
                summary={summaryFor(detail, 'series')} />
            ) : (
              <SeriesChart series={detail.chart.x} title={`Динамика: ${candidate.x.label}`}
                summary={summaryFor(detail, 'series')} />
            )}
            {candidate.y.type === 'boolean' ? (
              <BooleanStrip series={detail.chart.y} title={`Отметки: ${candidate.y.label}`}
                summary={summaryFor(detail, 'series')} />
            ) : (
              <SeriesChart series={detail.chart.y} title={`Динамика: ${candidate.y.label}`}
                summary={summaryFor(detail, 'series')} />
            )}
            {detail.chart.pairs.length > 0 ? (
              <ScatterChart pairs={detail.chart.pairs} xLabel={candidate.x.label} yLabel={candidate.y.label}
                title="Совместные наблюдения" summary={summaryFor(detail, 'relationship')} />
            ) : null}
            {group !== null ? (
              <GroupBars group={group} exposureLabel={exposure.label} title="Сравнение групп"
                summary={summaryFor(detail, 'groups')} />
            ) : null}
            <LagProfileChart alternatives={candidate.alternatives} title="Профиль задержек"
              summary={summaryFor(detail, 'lag_profile')} />
            {candidate.evidence.segments.length > 0 ? (
              <SegmentChart segments={candidate.evidence.segments} title="Отрезки истории"
                summary={summaryFor(detail, 'segments')} />
            ) : (
              <ChartFigure title="Отрезки истории" summary="История не разделена на отрезки."
                label="Отрезки истории: данных недостаточно">
                <span />
              </ChartFigure>
            )}
          </div>
        </section>
      ) : null}

      <section className="insight-detail__block" aria-label="Задержки">
        <h3 className="card__title">Проверенные задержки</h3>
        <div className="insight-table-scroll" role="region" aria-label="Таблица доказательств" tabIndex={0}><table className="insight-table">
          <caption className="insight-table__caption">
            Показана одна задержка, остальные остаются здесь: сравнивать их можно только после общей поправки.
          </caption>
          <thead>
            <tr>
              <th scope="col">Задержка</th>
              <th scope="col">Проверки</th>
              <th scope="col">Подтверждённость</th>
              <th scope="col">Величина</th>
              <th scope="col">Наблюдений</th>
            </tr>
          </thead>
          <tbody>
            {candidate.alternatives.map((alternative) => (
              <tr key={alternative.fingerprint} className={alternative.is_representative ? 'insight-table__row--lead' : undefined}>
                <th scope="row">
                  {alternative.timing}
                  {alternative.is_representative ? ' (в карточке)' : ''}
                </th>
                <td>{VERDICT_LABELS[alternative.guardrail]}</td>
                <td>{alternative.confidence !== null ? CONFIDENCE_LABELS[alternative.confidence] : 'нет'}</td>
                <td>{formatCoefficient(alternative.coefficient)}</td>
                <td>{formatCount(alternative.n)}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </section>

      {candidate.caveats.length > 0 ? (
        <section className="insight-detail__block" aria-label="Ограничения">
          <h3 className="card__title">Ограничения</h3>
          <ul className="insight-caveat-list">
            {candidate.caveats.map((caveat) => (
              <li key={caveat.code} className={`insight-caveat-list__item insight-caveat--${caveat.severity}`}>
                <strong>{caveat.label}.</strong> {caveat.detail || caveat.message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="insight-detail__block" aria-label="История оценок">
        <h3 className="card__title">История оценок этой связи</h3>
        <p className="insight-detail__hint">{detail?.snapshot_policy ?? 'История загружается вместе с доказательствами.'}</p>
        {detail !== null && detail.history.length > 0 ? (
          <div className="insight-table-scroll" role="region" aria-label="Таблица доказательств" tabIndex={0}><table className="insight-table">
            <caption className="insight-table__caption">
              Как менялись доказательства при прошлых оценках.
            </caption>
            <thead>
              <tr>
                <th scope="col">Дата оценки</th>
                <th scope="col">Статус</th>
                <th scope="col">Подтверждённость</th>
                <th scope="col">Проверки</th>
                <th scope="col">Величина</th>
                <th scope="col">Наблюдений</th>
                <th scope="col">Покрытие</th>
                <th scope="col">Показатели</th>
              </tr>
            </thead>
            <tbody>
              {detail.history.map((snapshot) => (
                <HistoryRow key={snapshot.id} snapshot={snapshot} />
              ))}
            </tbody>
          </table></div>
        ) : detail !== null ? (
          <p className="empty">
            Снимков пока нет. Нажмите «Обновить историю оценок», чтобы сохранить текущее состояние.
          </p>
        ) : null}
        {detail !== null && detail.history.length > 0 ? (
          <details className="insight-detail__notes">
            <summary>Отрезки истории и сохранённые формулировки</summary>
            <ul>
              {detail.history.map((snapshot) => (
                <li key={`note-${snapshot.id}`}>
                  {`${snapshot.evaluated_on}: ${snapshot.statement} (шаблон ${snapshot.template_version}, правила ${snapshot.insight_policy_version}/${snapshot.guardrail_policy_version}/${snapshot.confidence_policy_version})`}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
        {candidate.evidence.segments.length > 0 ? (
          <ul className="insight-detail__segments">
            {candidate.evidence.segments.map((segment) => (
              <li key={segment.name}>
                {`${SEGMENT_LABELS[segment.name] ?? segment.name}: ${formatCoefficient(segment.coefficient)} — ${RELATION_TO_FULL_LABELS[segment.relation_to_full] ?? segment.relation_to_full}`}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </section>
  )
}

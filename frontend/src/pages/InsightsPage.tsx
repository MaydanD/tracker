import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { describeApiError } from '../api/client'
import {
  fetchInsightCatalogue,
  fetchInsightDetail,
  fetchInsights,
  refreshInsights,
} from '../api/insights'
import type {
  InsightAnalyticsRead,
  InsightCandidateRead,
  InsightDetailRead,
  InsightQuery,
} from '../api/insights'
import { EmptyState, ErrorBanner, InfoBanner, LoadingText } from '../components/Feedback'
import { InsightCard } from '../components/insights/InsightCard'
import { InsightDetail } from '../components/insights/InsightDetail'
import { InsightFilters } from '../components/insights/InsightFilters'
import type { FiltersState, ExplorerState, PeriodPreset } from '../components/insights/InsightFilters'
import { AVAILABILITY_HINTS, STATUS_LABELS, formatCount } from '../components/insights/labels'
import { useAsyncData } from '../hooks/useAsyncData'

const DEFAULT_PRESET = '90' as const
const PRESET_DAYS: Record<Exclude<PeriodPreset, 'custom'>, number> = {
  '30': 30,
  '90': 90,
  '180': 180,
  '365': 365,
}
const DAY_MS = 86_400_000

function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function shiftDays(iso: string, days: number): string {
  const start = Date.parse(`${iso}T00:00:00Z`)
  return new Date(start + days * DAY_MS).toISOString().slice(0, 10)
}

function rangeFor(preset: PeriodPreset, today: string): { start: string; end: string } {
  const key: Exclude<PeriodPreset, 'custom'> = preset === 'custom' ? DEFAULT_PRESET : preset
  return { start: shiftDays(today, -(PRESET_DAYS[key] - 1)), end: today }
}


const STATUS_ORDER = [
  'well_supported',
  'stable',
  'preliminary',
  'warning',
  'hidden',
  'not_evaluable',
] as const

interface Props {
  /**
   * The app uses the machine's date, exactly like the backend clock does. Tests
   * pin it so period presets become deterministic.
   */
  today?: string
}

export function InsightsPage({ today: pinnedToday }: Props = {}) {
  const [baseToday] = useState(() => pinnedToday ?? isoDate(new Date()))
  const [range, setRange] = useState(() => rangeFor(DEFAULT_PRESET, baseToday))
  const [filters, setFilters] = useState<FiltersState>({
    preset: DEFAULT_PRESET,
    start: range.start,
    end: range.end,
    confidence: 'all',
    guardrail: 'admissible',
    areaId: 'all',
    variableKey: 'all',
  })
  const [explorer, setExplorer] = useState<ExplorerState>({ x: '', y: '', lag: 0, active: false })
  const [selected, setSelected] = useState<{ candidate: InsightCandidateRead; query: InsightQuery } | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const refreshController = useRef<AbortController | null>(null)

  const catalogue = useAsyncData((signal) => fetchInsightCatalogue(signal), [])

  const query = useMemo<InsightQuery>(() => {
    if (explorer.active && explorer.x !== '' && explorer.y !== '') {
      return { start: range.start, end: range.end, mode: 'explorer', x: explorer.x, y: explorer.y, lag: explorer.lag }
    }
    return {
      start: range.start,
      end: range.end,
      includeHidden: filters.guardrail === 'blocked' || filters.guardrail === 'all',
      verdicts:
        filters.guardrail === 'warnings'
          ? ['pass_with_warnings']
          : filters.guardrail === 'blocked'
            ? ['blocked', 'not_evaluable']
            : undefined,
      confidence: filters.confidence === 'all' ? undefined : [filters.confidence],
      variables: filters.variableKey !== 'all' ? [filters.variableKey]
        : filters.areaId === 'all' ? undefined
          : catalogue.data?.variables.filter((variable) => variable.area_id === filters.areaId && variable.in_default_sweep)
            .map((variable) => variable.key),
    }
  }, [range.start, range.end, filters.guardrail, filters.confidence, filters.variableKey, filters.areaId, catalogue.data, explorer])

  const queryKey = JSON.stringify(query)
  useEffect(() => {
    setRefreshing(false)
    setRefreshMessage(null)
    setRefreshError(null)
    return () => refreshController.current?.abort()
  }, [queryKey])
  const feed = useAsyncData(async (signal) => ({ key: queryKey, value: await fetchInsights(query, signal) }), [queryKey])

  // A detail request only exists while a card is open; otherwise it resolves to null.
  const detailKey = selected === null ? '' : `${selected.candidate.fingerprint}|${queryKey}`
  const detail = useAsyncData<{ key: string; value: InsightDetailRead } | null>(
    async (signal) =>
      selected === null
        ? null
        : { key: detailKey, value: await fetchInsightDetail(selected.candidate.fingerprint, {
            ...selected.query, x: selected.candidate.x.key, y: selected.candidate.y.key,
            lag: selected.candidate.lag, mode: selected.query.mode ?? 'discovery',
          }, signal) },
    [detailKey],
  )

  const applyFilters = useCallback(
    (next: FiltersState) => {
      setSelected(null)
      // Choosing a preset recomputes its dates; editing a date field switches to
      // "Свой период" and keeps the dates the user typed.
      const chosen = next.preset !== 'custom' && next.preset !== filters.preset
      const resolved = chosen ? rangeFor(next.preset, baseToday) : { start: next.start, end: next.end }
      setFilters({ ...next, ...resolved })
      setRange(resolved)
    },
    [baseToday, filters.preset],
  )

  const applyExplorer = useCallback((next: ExplorerState) => {
    setExplorer(next)
    setSelected(null)
  }, [])

  const handleRefresh = useCallback(async () => {
    refreshController.current?.abort()
    const controller = new AbortController()
    refreshController.current = controller
    setRefreshing(true)
    setRefreshError(null)
    setRefreshMessage(null)
    try {
      const result = await refreshInsights({ start: query.start, end: query.end }, controller.signal)
      if (controller.signal.aborted) return
      const { created, updated, unchanged, evaluated_on } = result.snapshots
      setRefreshMessage(
        `Оценка за ${evaluated_on}: новых снимков ${created}, обновлено ${updated}, без изменений ${unchanged}.`,
      )
      feed.reload()
      detail.reload()
    } catch (cause) {
      if (!controller.signal.aborted) setRefreshError(describeApiError(cause))
    } finally {
      if (!controller.signal.aborted) setRefreshing(false)
    }
  }, [query.start, query.end, feed, detail])

  const analytics: InsightAnalyticsRead | null = feed.data?.key === queryKey && feed.error === null ? feed.data.value : null
  const insights = query.variables?.length === 0 ? [] : analytics?.insights ?? []
  const counts = analytics?.summary.counts ?? null
  const labelFor = (key: string) => catalogue.data?.variables.find((variable) => variable.key === key)?.label ?? 'Показатель'
  const explorerPair = explorer.active ? `${labelFor(explorer.x)} — ${labelFor(explorer.y)}` : null
  const currentDetail = detail.data?.key === detailKey && detail.error === null ? detail.data.value : null

  return (
    <section className="page">
      <header className="page__header">
        <h1 className="page__title">Аналитика</h1>
        <span className="badge">Этап 8</span>
      </header>
      <p className="page__summary">
        Связи в ваших данных: что видно в истории, насколько это подтверждено и какие
        ограничения у каждого наблюдения.
      </p>

      <InsightFilters
        state={{ ...filters, start: range.start, end: range.end }}
        explorer={explorer}
        variables={catalogue.data?.variables ?? []}
        areas={catalogue.data?.areas ?? []}
        onState={applyFilters}
        onExplorer={applyExplorer}
      />

      {catalogue.error !== null ? <ErrorBanner message={catalogue.error} /> : null}
      <ErrorBanner message={feed.error} />
      <ErrorBanner message={refreshError} />
      {refreshMessage !== null ? <InfoBanner>{refreshMessage}</InfoBanner> : null}

      <div className="insight-toolbar">
        <p className="insight-toolbar__period">
          {`Период: ${range.start} — ${range.end}`}
          {analytics !== null ? ` · данные загружены с ${analytics.source_range.start}` : ''}
        </p>
        <button type="button" className="button button--small" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? 'Сохраняем снимок…' : 'Обновить историю оценок'}
        </button>
      </div>

      <p className="insight-toolbar__hint">
        Кнопка сохраняет общий обзор: один снимок в день для каждой выбранной обзором связи.
        Повторное обновление в тот же день заменяет снимок, если данные или период изменились.
      </p>

      {explorerPair !== null ? (
        <InfoBanner>
          {`Проверяется одна пара: ${explorerPair}. Сравнение с другими парами к ней не применяется.`}
        </InfoBanner>
      ) : null}

      {analytics !== null && counts !== null ? (
        <div className="insight-summary">
          <p className="insight-summary__line">
            {`Найдено групп связей: ${formatCount(counts.groups)} · показано: ${formatCount(insights.length)}`}
          </p>
          <ul className="insight-card__chips">
            {STATUS_ORDER.filter((status) => counts.by_status[status] > 0).map((status) => (
              <li key={status} className={`insight-chip insight-chip--status-${status}`}>
                {`${STATUS_LABELS[status]}: ${formatCount(counts.by_status[status])}`}
              </li>
            ))}
            <li className="insight-chip">{`Проверено гипотез: ${formatCount(counts.hypotheses)}`}</li>
          </ul>
        </div>
      ) : null}

      {analytics !== null && analytics.summary.availability !== 'ok' ? (
        <InfoBanner>
          {analytics.summary.message}
          {AVAILABILITY_HINTS[analytics.summary.availability]
            ? ` ${AVAILABILITY_HINTS[analytics.summary.availability]}`
            : ''}
        </InfoBanner>
      ) : null}

      {feed.loading && analytics === null ? (
        <LoadingText>Загрузка аналитики…</LoadingText>
      ) : null}

      {analytics !== null && insights.length === 0 ? (
        <EmptyState>{analytics.summary.availability === 'ok' || analytics.summary.availability === 'preliminary_only'
          ? 'Нет наблюдений для выбранных фильтров.' : analytics.summary.message}</EmptyState>
      ) : null}

      {insights.length > 0 ? (
        <div className="insight-layout">
          <div className="insight-feed">
            {insights.map((insight) => (
              <InsightCard
                key={insight.fingerprint}
                insight={insight}
                selected={selected?.candidate.fingerprint === insight.fingerprint}
                onOpen={(candidate) => setSelected({ candidate, query })}
              />
            ))}
          </div>

          {selected !== null ? (
            <div className="insight-panel">
              <button type="button" className="button button--small" onClick={() => setSelected(null)}>
                Закрыть подробности
              </button>
              <InsightDetail
                detail={currentDetail}
                candidate={currentDetail?.candidate ?? selected.candidate}
                analytics={analytics}
                loading={detail.loading}
                error={detail.error}
                refreshing={refreshing}
                onRefresh={() => void handleRefresh()}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

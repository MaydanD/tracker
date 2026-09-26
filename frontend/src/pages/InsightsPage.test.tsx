import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { InsightCandidateRead } from '../api/insights'
import { jsonResponse, stubApi, stubFetch } from '../test/fetchStub'
import {
  PERIOD,
  TODAY,
  analyticsPayload,
  blockedCandidate,
  booleanCandidate,
  candidate,
  cataloguePayload,
  detailPayload,
  historyRows,
} from '../test/insightsFixture'
import { InsightsPage } from './InsightsPage'

const MAIN = candidate()
const BOOLEAN = booleanCandidate()
const BLOCKED = blockedCandidate()

interface SetupResult {
  requests: URLSearchParams[]
}

function setup(insights: InsightCandidateRead[] = [MAIN, BOOLEAN], extra: {
  feed?: Record<string, unknown>
  detailHistory?: boolean
} = {}): SetupResult {
  const requests: URLSearchParams[] = []
  const all = [...insights, BLOCKED]

  const filter = (query: URLSearchParams): InsightCandidateRead[] => {
    const verdicts = query.getAll('verdicts')
    const confidence = query.getAll('confidence')
    const includeHidden = query.get('include_hidden') === 'true'
    let items = all
    if (verdicts.length > 0) {
      items = items.filter((item) => verdicts.includes(item.guardrail.verdict))
    } else if (!includeHidden) {
      items = items.filter((item) => item.in_default_feed)
    }
    if (confidence.length > 0) {
      items = items.filter(
        (item) => item.confidence.level !== null && confidence.includes(item.confidence.level),
      )
    }
    return items
  }

  stubApi(
    {
      'GET /api/analytics/insights/variables': () => jsonResponse(cataloguePayload()),
      'GET /api/analytics/insights': (request) => {
        requests.push(request.query)
        return jsonResponse(analyticsPayload(filter(request.query), extra.feed))
      },
      'POST /api/analytics/insights/refresh': () =>
        jsonResponse({
          analytics: analyticsPayload(insights),
          snapshots: { evaluated_on: TODAY, created: 4, updated: 1, unchanged: 0, total: 5 },
        }),
    },
    {
      fallback: (request) => {
        const fingerprint = request.path.split('/').at(-1) ?? ''
        if (request.path.endsWith('/history')) return jsonResponse([])
        const selected = all.find((item) => item.fingerprint === fingerprint)
        if (selected === undefined) {
          return jsonResponse({ error: { code: 'insight_not_found', message: 'x' } }, 404)
        }
        return jsonResponse(
          detailPayload(selected, extra.detailHistory === false ? [] : historyRows(selected)),
        )
      },
    },
  )
  return { requests }
}

function renderPage(result: SetupResult = setup()) {
  render(<InsightsPage today={TODAY} />)
  return result
}

describe('InsightsPage', () => {
  it('renders the Russian feed with human labels and never a raw variable key', async () => {
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Аналитика' })).toBeInTheDocument()
    expect(
      await screen.findByText(/Эта связь устойчиво повторяется в вашей истории/),
    ).toBeInTheDocument()
    const card = screen.getByTestId(`insight-${MAIN.fingerprint.slice(0, 8)}`)
    expect(within(card).getAllByText('Хорошо подтверждено')).toHaveLength(2)
    expect(screen.getByText('Наблюдений: 90')).toBeInTheDocument()
    expect(screen.getByText('Покрытие: 98%')).toBeInTheDocument()
    expect(within(card).getByText('Энергия')).toBeInTheDocument()
    expect(screen.getByText('Соседние дни могут быть статистически зависимы')).toBeInTheDocument()

    // Internal identifiers and English UI text must never reach the screen.
    const text = document.body.textContent ?? ''
    expect(text).not.toContain('state.energy')
    expect(text).not.toContain('habit.1.daily.completion')
    expect(text).not.toMatch(/Insights|preliminary|well_supported|pass_with_warnings/)
  })

  it('requests the preset range and recomputes it when the preset changes', async () => {
    const { requests } = renderPage()
    await waitFor(() => expect(requests.length).toBeGreaterThan(0))
    expect(requests[0]?.get('start')).toBe('2026-06-28')
    expect(requests[0]?.get('end')).toBe(TODAY)

    fireEvent.change(screen.getByLabelText('Период'), { target: { value: '30' } })
    await waitFor(() => expect(requests.length).toBeGreaterThan(1))
    const last = requests.at(-1)
    expect(last?.get('start')).toBe('2026-08-27')
    expect(last?.get('end')).toBe(TODAY)
  })

  it('supports a custom range through the date fields', async () => {
    const { requests } = renderPage()
    await waitFor(() => expect(requests.length).toBeGreaterThan(0))

    fireEvent.change(screen.getByLabelText('Начало'), { target: { value: '2026-07-01' } })
    fireEvent.change(screen.getByLabelText('Конец'), { target: { value: '2026-08-15' } })

    await waitFor(() => {
      const last = requests.at(-1)
      expect(last?.get('start')).toBe('2026-07-01')
      expect(last?.get('end')).toBe('2026-08-15')
    })
  })

  it('applies the confidence filter through the backend query', async () => {
    const { requests } = renderPage()
    expect(await screen.findByText(/Эта связь устойчиво повторяется/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Уровень подтверждённости'), {
      target: { value: 'preliminary' },
    })

    await waitFor(() => {
      expect(requests.at(-1)?.getAll('confidence')).toEqual(['preliminary'])
    })
    expect(await screen.findByText(/Пока есть предварительный сигнал/)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText(/Эта связь устойчиво повторяется/)).not.toBeInTheDocument()
    })
  })

  it('keeps blocked results out of the default feed and shows them on request', async () => {
    const { requests } = renderPage()
    expect(await screen.findByText(/устойчиво повторяется/)).toBeInTheDocument()
    expect(screen.queryByText(/не прошёл статистические проверки/)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Статистические проверки'), {
      target: { value: 'blocked' },
    })

    await waitFor(() => {
      const last = requests.at(-1)
      expect(last?.get('include_hidden')).toBe('true')
      expect(last?.getAll('verdicts')).toEqual(['blocked', 'not_evaluable'])
    })
    expect(await screen.findByText(/Результат не прошёл статистические проверки/)).toBeInTheDocument()
  })

  it('opens the detail with evidence, charts, limitations and history', async () => {
    const { requests } = renderPage()
    const card = await screen.findByTestId(`insight-${MAIN.fingerprint.slice(0, 8)}`)

    fireEvent.click(within(card).getByRole('button', { name: 'Подробнее о доказательствах' }))

    const panel = await screen.findByTestId('insight-detail')
    expect(within(panel).getByText('Подробнее о доказательствах')).toBeInTheDocument()
    expect(within(panel).getByText('ранговая корреляция (Спирмен)')).toBeInTheDocument()
    expect(within(panel).getByText('+0,62 (положительное)')).toBeInTheDocument()
    expect(within(panel).getByText('90 из 92 подходящих дней')).toBeInTheDocument()
    expect(within(panel).getByText('Период')).toBeInTheDocument()
    expect(within(panel).getByText('Хорошо подтверждено: данных достаточно, покрытие высокое, а направление связи сохраняется на всей истории.')).toBeInTheDocument()

    // Charts, each with its accessible summary from the backend.
    expect(within(panel).getByText('Профиль задержек')).toBeInTheDocument()
    expect(within(panel).getByText('Отрезки истории')).toBeInTheDocument()
    expect(within(panel).getByText('Динамика: Энергия')).toBeInTheDocument()
    expect(within(panel).getByText('Совместные наблюдения')).toBeInTheDocument()
    expect(within(panel).getAllByText(/пропуски оставлены пустыми/).length).toBeGreaterThan(0)

    // Gaps stay gaps: six days, one without data, so five drawn points.
    const seriesPlot = within(panel).getByTestId(`chart-series-${MAIN.x.key}`)
    expect(seriesPlot.querySelectorAll('circle.insight-chart__dot')).toHaveLength(5)

    // Limitations and the persisted history.
    expect(within(panel).getByText('Связь не означает причинность.')).toBeInTheDocument()
    expect(within(panel).getByText('2026-09-20')).toBeInTheDocument()
    expect(within(panel).getByText('2026-09-25')).toBeInTheDocument()
    expect(within(panel).getByText(/Снимок истории создаётся только явным обновлением/)).toBeInTheDocument()

    // The detail request repeats the hypothesis and the feed's mode.
    const detailRequests = requests.length
    expect(detailRequests).toBeGreaterThan(0)
    expect(within(panel).getByText('Подробнее о доказательствах')).toBeInTheDocument()
  })

  it('compares groups for a boolean pair instead of drawing a scatter', async () => {
    renderPage()
    const card = await screen.findByTestId(`insight-${BOOLEAN.fingerprint.slice(0, 8)}`)
    fireEvent.click(within(card).getByRole('button', { name: 'Подробнее о доказательствах' }))

    const panel = await screen.findByTestId('insight-detail')
    expect(within(panel).getByText('Сравнение групп')).toBeInTheDocument()
    expect(within(panel).getByText(/«Да» — 54 наблюдений, «Нет» — 34 наблюдений/)).toBeInTheDocument()
    expect(within(panel).queryByText('Совместные наблюдения')).not.toBeInTheDocument()
    expect(within(panel).getByText('Отметки: Тренировка')).toBeInTheDocument()
  })

  it('explains the whole evidence base with backend numbers only', async () => {
    renderPage()
    const card = await screen.findByTestId(`insight-${MAIN.fingerprint.slice(0, 8)}`)
    fireEvent.click(within(card).getByRole('button', { name: 'Подробнее о доказательствах' }))
    const panel = await screen.findByTestId('insight-detail')

    const checks = within(panel).getByText('Проверки статистических правил').closest('table')
    expect(checks).not.toBeNull()
    expect(within(checks as HTMLElement).getByText('Контроль дня недели')).toBeInTheDocument()
    expect(within(checks as HTMLElement).getByText('Контроль ложных открытий')).toBeInTheDocument()
    // The adjusted q-value and the family size are the backend's own numbers.
    expect(within(panel).getAllByText(/проверено 225 из 225/).length).toBeGreaterThan(0)
  })

  it('stores a history snapshot only when asked and reports the outcome', async () => {
    renderPage()
    await screen.findByText(/устойчиво повторяется/)

    fireEvent.click(screen.getByRole('button', { name: 'Обновить историю оценок' }))

    expect(
      await screen.findByText('Оценка за 2026-09-25: новых снимков 4, обновлено 1, без изменений 0.'),
    ).toBeInTheDocument()
  })

  it('never writes history while only reading', async () => {
    const refresh = vi.fn(() =>
      jsonResponse({ analytics: analyticsPayload([MAIN]), snapshots: {
        evaluated_on: TODAY, created: 0, updated: 0, unchanged: 0, total: 0,
      } }),
    )
    stubApi({
      'GET /api/analytics/insights/variables': () => jsonResponse(cataloguePayload()),
      'GET /api/analytics/insights': () => jsonResponse(analyticsPayload([MAIN])),
      'POST /api/analytics/insights/refresh': refresh,
      [`GET /api/analytics/insights/${MAIN.fingerprint}`]: () => jsonResponse(detailPayload(MAIN)),
    })
    render(<InsightsPage today={TODAY} />)

    const card = await screen.findByTestId(`insight-${MAIN.fingerprint.slice(0, 8)}`)
    fireEvent.click(within(card).getByRole('button', { name: 'Подробнее о доказательствах' }))
    await screen.findByTestId('insight-detail')
    fireEvent.change(screen.getByLabelText('Период'), { target: { value: '30' } })
    await screen.findByText(/устойчиво повторяется/)

    expect(refresh).not.toHaveBeenCalled()
  })

  it('explains an empty period without treating it as an error', async () => {
    setup([], {
      feed: {
        summary: {
          availability: 'insufficient_data',
          message: 'Пока недостаточно совместных наблюдений для устойчивых выводов.',
          counts: analyticsPayload([]).summary.counts,
        },
      },
    })
    render(<InsightsPage today={TODAY} />)

    expect(
      await screen.findByText('Пока недостаточно совместных наблюдений для устойчивых выводов.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Как только появится больше совместных наблюдений/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('reports no data as an empty period, not as a failure', async () => {
    setup([], {
      feed: {
        summary: {
          availability: 'no_data',
          message: 'За выбранный период данных для аналитики нет.',
          counts: analyticsPayload([]).summary.counts,
        },
      },
    })
    render(<InsightsPage today={TODAY} />)

    expect(await screen.findByText('За выбранный период данных для аналитики нет.')).toBeInTheDocument()
  })

  it('shows a Russian message and no raw payload when the backend fails', async () => {
    stubApi(
      {
        'GET /api/analytics/insights/variables': () => jsonResponse(cataloguePayload()),
        'GET /api/analytics/insights': () =>
          jsonResponse({ error: { code: 'internal_error', message: 'Traceback (most recent call last)' } }, 500),
      },
    )
    render(<InsightsPage today={TODAY} />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('На сервере произошла ошибка. Попробуйте ещё раз.')
    expect(alert.textContent ?? '').not.toContain('Traceback')
  })

  it('does not let a slow older response overwrite a newer one', async () => {
    let releaseFirst: () => void = () => {}
    const firstResponse = new Promise<Response>((resolve) => {
      releaseFirst = () => resolve(jsonResponse(analyticsPayload([BLOCKED])))
    })
    let calls = 0

    stubFetch(async (input) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname === '/api/analytics/insights/variables') return jsonResponse(cataloguePayload())
      if (url.pathname === '/api/analytics/insights') {
        calls += 1
        if (calls === 1) return firstResponse
        return jsonResponse(analyticsPayload([MAIN]))
      }
      return jsonResponse({ error: { code: 'not_found', message: 'x' } }, 404)
    })

    render(<InsightsPage today={TODAY} />)
    fireEvent.change(await screen.findByLabelText('Период'), { target: { value: '30' } })

    expect(await screen.findByText(/устойчиво повторяется/)).toBeInTheDocument()
    releaseFirst?.()
    await waitFor(() => expect(calls).toBeGreaterThan(1))
    expect(screen.queryByText(/Результат не прошёл статистические проверки/)).not.toBeInTheDocument()
    expect(screen.getByText(/устойчиво повторяется/)).toBeInTheDocument()
  })

  it('shows the requested period and where the loaded data starts', async () => {
    renderPage()
    expect(
      await screen.findByText(`Период: ${PERIOD.start} — ${PERIOD.end} · данные загружены с 2026-06-21`),
    ).toBeInTheDocument()
  })
})

  it('sends the selected identity and discovery mode to detail, preserving the family', async () => {
    const seen: URLSearchParams[] = []
    stubApi({
      'GET /api/analytics/insights/variables': () => jsonResponse(cataloguePayload()),
      'GET /api/analytics/insights': () => jsonResponse(analyticsPayload([BOOLEAN])),
      [`GET /api/analytics/insights/${BOOLEAN.fingerprint}`]: (request) => {
        seen.push(request.query)
        return jsonResponse(detailPayload(BOOLEAN))
      },
    })
    render(<InsightsPage today={TODAY} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Подробнее о доказательствах' }))
    await waitFor(() => expect(seen).toHaveLength(1))
    expect(seen[0]?.get('x')).toBe(BOOLEAN.x.key)
    expect(seen[0]?.get('y')).toBe(BOOLEAN.y.key)
    expect(seen[0]?.get('lag')).toBe('3')
    expect(seen[0]?.get('mode')).toBe('discovery')
  })

  it('filters an area after discovery and keeps human labels in explorer', async () => {
    const { requests } = renderPage()
    await screen.findByText(/устойчиво повторяется/)
    fireEvent.change(screen.getByLabelText('Сфера'), { target: { value: '1' } })
    await waitFor(() => expect(requests.at(-1)?.getAll('variables')).toEqual(['habit.1.daily.completion']))
    fireEvent.change(screen.getByLabelText('Сфера'), { target: { value: 'all' } })
    fireEvent.change(screen.getByLabelText('Первый показатель'), { target: { value: 'state.energy' } })
    fireEvent.change(screen.getByLabelText('Второй показатель'), { target: { value: 'state.mood' } })
    fireEvent.click(screen.getByRole('button', { name: 'Показать связь' }))
    expect(await screen.findByText(/Проверяется одна пара: Энергия — Настроение/)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('state.energy')
    await waitFor(() => expect(requests.at(-1)?.get('mode')).toBe('explorer'))
  })

  it('clears old evidence immediately and aborts a detail request when another card is selected', async () => {
    let release: (response: Response) => void = () => {}
    let firstSignal: AbortSignal | null | undefined
    const delayed = new Promise<Response>((resolve) => { release = resolve })
    stubFetch(async (input, init) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname.endsWith('/variables')) return jsonResponse(cataloguePayload())
      if (url.pathname === '/api/analytics/insights') return jsonResponse(analyticsPayload([MAIN, BOOLEAN]))
      if (url.pathname.endsWith(MAIN.fingerprint)) { firstSignal = init?.signal; return delayed }
      return jsonResponse(detailPayload(BOOLEAN))
    })
    render(<InsightsPage today={TODAY} />)
    const main = await screen.findByTestId(`insight-${MAIN.fingerprint.slice(0, 8)}`)
    fireEvent.click(within(main).getByRole('button'))
    await waitFor(() => expect(firstSignal).toBeDefined())
    fireEvent.click(within(screen.getByTestId(`insight-${BOOLEAN.fingerprint.slice(0, 8)}`)).getByRole('button'))
    expect(firstSignal?.aborted).toBe(true)
    await screen.findByTestId(`chart-boolean-${BOOLEAN.y.key}`)
    release(jsonResponse(detailPayload(MAIN)))
    await waitFor(() => expect(screen.queryByTestId(`chart-series-${MAIN.x.key}`)).not.toBeInTheDocument())
    expect(screen.getByTestId(`chart-boolean-${BOOLEAN.y.key}`)).toBeInTheDocument()
  })

  it('does not show results from an old period while the new period is loading or fails', async () => {
    let fail: (response: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => { fail = resolve })
    let calls = 0
    stubFetch(async (input) => {
      if (String(input).includes('/variables')) return jsonResponse(cataloguePayload())
      return ++calls === 1 ? jsonResponse(analyticsPayload([MAIN])) : pending
    })
    render(<InsightsPage today={TODAY} />)
    await screen.findByText(/устойчиво повторяется/)
    fireEvent.change(screen.getByLabelText('Период'), { target: { value: '30' } })
    expect(screen.queryByText(/устойчиво повторяется/)).not.toBeInTheDocument()
    expect(screen.getByText('Загрузка аналитики…')).toBeInTheDocument()
    fail(jsonResponse({ error: { code: 'internal_error', message: 'failed' } }, 500))
    await screen.findByRole('alert')
    expect(screen.queryByText(/устойчиво повторяется/)).not.toBeInTheDocument()
  })

  it('shows the contextual Owl banner above the analytics controls', async () => {
    stubApi({
      'GET /api/analytics/insights/variables': () => jsonResponse(cataloguePayload()),
      'GET /api/analytics/insights': () =>
        jsonResponse(analyticsPayload([MAIN], {
          owl: {
            owl_id: 'stable_insight',
            asset_key: 'owl_insight',
            tone: 'neutral',
            priority: 40,
            caption_line1: 'Так. А вот это уже интересно.',
            caption_line2: MAIN.text.full,
            dismissible: true,
            fingerprint: 'fp-insight',
            context: 'insights',
            fallback_line1: null,
          },
        })),
    })
    render(<InsightsPage today={TODAY} />)

    const banner = await screen.findByTestId('owl-banner')
    expect(within(banner).getByText('Так. А вот это уже интересно.')).toBeInTheDocument()
    expect(within(banner).getByRole('img', { name: 'Сова-помощник' })).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('owl_insight')
  })

import { render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { OwlState } from '../api/owl'
import { getAnalyticsOwlSnapshot, getOwlSnapshot, resetOwlStore, setOwl } from '../components/owl/owlStore'
import { jsonResponse, stubApi } from '../test/fetchStub'
import { analyticsPayload, candidate, cataloguePayload } from '../test/insightsFixture'
import { AnalyticsPage } from './AnalyticsPage'

const dashboardOwl: OwlState = {
  owl_id: 'dashboard_state',
  asset_key: 'owl_all_done',
  tone: 'celebratory',
  priority: 70,
  caption_line1: 'Состояние с Главного обзора.',
  caption_line2: 'Состояние с Главного обзора.',
  dismissible: false,
  fingerprint: 'dashboard-fingerprint',
  context: 'dashboard',
  fallback_line1: null,
}

const analyticsOwl: OwlState = {
  owl_id: 'stable_insight',
  asset_key: 'owl_insight',
  tone: 'neutral',
  priority: 40,
  caption_line1: 'Так. А вот это уже интересно.',
  caption_line2: 'Наблюдение из аналитики.',
  dismissible: false,
  fingerprint: 'analytics-fingerprint',
  context: 'insights',
  fallback_line1: null,
}

afterEach(() => resetOwlStore())

describe('AnalyticsPage', () => {
  it('keeps the dashboard Owl hidden until the analytics Owl arrives in the existing response', async () => {
    let insightRequests = 0
    stubApi(
      {
        'GET /api/analytics/insights/variables': () => jsonResponse(cataloguePayload()),
        'GET /api/analytics/insights': () => {
          insightRequests += 1
          return jsonResponse(analyticsPayload([candidate()], { owl: analyticsOwl }))
        },
      },
      { fallback: () => jsonResponse({ error: { code: 'not_found', message: 'x' } }, 404) },
    )
    setOwl(dashboardOwl)

    render(<AnalyticsPage />)

    expect(screen.getByRole('status', { name: 'Загрузка совы-помощника' })).toBeInTheDocument()
    expect(screen.queryByText(dashboardOwl.caption_line1)).not.toBeInTheDocument()

    const banner = await screen.findByTestId('owl-banner')
    expect(within(banner).getByText(analyticsOwl.caption_line1)).toBeInTheDocument()
    expect(screen.queryByText(dashboardOwl.caption_line1)).not.toBeInTheDocument()
    expect(getAnalyticsOwlSnapshot()).toEqual(analyticsOwl)
    expect(getOwlSnapshot()).toEqual(analyticsOwl)
    expect(insightRequests).toBe(1)
  })
})

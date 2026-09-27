import { useSyncExternalStore } from 'react'

import { OwlAssistantBanner } from '../components/owl/OwlAssistantBanner'
import { ActivityTrends } from '../components/insights/ActivityTrends'
import {
  getAnalyticsOwlLoadedSnapshot,
  getAnalyticsOwlSnapshot,
  subscribeOwl,
} from '../components/owl/owlStore'
import { CalendarPage } from './CalendarPage'
import { InsightsPage } from './InsightsPage'
import { HabitRecordsSection } from './RecordsPage'

export function AnalyticsPage() {
  const owl = useSyncExternalStore(subscribeOwl, getAnalyticsOwlSnapshot)
  const owlLoaded = useSyncExternalStore(subscribeOwl, getAnalyticsOwlLoadedSnapshot)

  return (
    <div className="analytics-page">
      <section className="page analytics-heading">
        <header className="page__header">
          <h1 className="page__title">Аналитика</h1>
        </header>
        <div className="analytics-owl-slot">
          {owl !== null ? (
            <OwlAssistantBanner state={owl} />
          ) : owlLoaded ? null : (
            <div className="analytics-owl-placeholder" role="status" aria-label="Загрузка совы-помощника" />
          )}
        </div>
      </section>
      <ActivityTrends />
      <InsightsPage openFirstInsight embedded />
      <HabitRecordsSection />
      <CalendarPage embedded />
    </div>
  )
}

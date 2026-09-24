import { apiRequest } from './client'

export interface DailyStateInput {
  mood: number | null
  energy: number | null
  wellbeing: number | null
  sleep_status: 'underslept' | 'normal' | 'overslept' | null
  sleep_minutes: number | null
  alcohol: boolean | null
  alcohol_detail: string | null
  gaming: boolean | null
  gaming_minutes: number | null
  computer_overuse: boolean | null
  computer_minutes: number | null
  note: string | null
}

export interface DailyStateRecord extends DailyStateInput {
  id: number
  state_date: string
  created_at: string
  updated_at: string
}

export interface DailyStateResponse {
  state_date: string
  today: string
  state: DailyStateRecord | null
}

export const emptyDailyState = (): DailyStateInput => ({
  mood: null, energy: null, wellbeing: null, sleep_status: null, sleep_minutes: null,
  alcohol: null, alcohol_detail: null, gaming: null, gaming_minutes: null,
  computer_overuse: null, computer_minutes: null, note: null,
})

const path = (date: string) => `/api/days/${encodeURIComponent(date)}/state`
export const fetchDailyState = (date: string, signal?: AbortSignal) =>
  apiRequest<DailyStateResponse>(path(date), { signal })
export const saveDailyState = (date: string, body: DailyStateInput) =>
  apiRequest<DailyStateRecord>(path(date), { method: 'PUT', body })
export const deleteDailyState = (date: string) =>
  apiRequest<void>(path(date), { method: 'DELETE' })

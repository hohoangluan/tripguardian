// Đang đi (docs/P5_COMPANION.md): the Today view of a confirmed journey, check-ins, suggestions, and the Google Calendar
// export that always goes preview -> confirm -> apply.
import { json } from './journey'

export type StopStatus = 'planned' | 'arrived' | 'skipped'
export type Stop = { id: string; day: number; seq: number | null; place_id: string; name: string; arrive: string | null; leave: string | null; status: StopStatus; arrived_at: string | null; rating: 1 | -1 | null; skip_reason: string | null; added_on_trip: boolean; off_plan?: boolean }
export type Option = { id: string; text: string }
export type TodayView = {
  trip: { id: string; start_date: string | null; end_date: string | null; status: 'planned' | 'active' | 'done'; starts_in: number }
  day: number
  today: number | null
  days: { day: number; date: string | null; window: [string, string] | null; stops: Stop[] }[]
  extra: (Omit<Stop, 'day'> & { day: number | null })[] // stops outside the plan's days, and off-plan check-ins (off_plan)
  here: { place_id: string; stop_id: string | null; at: string } | null
  tight: { late_min: number; day: number; options: Option[] } | null
  warnings: { code: string; text: string }[]
  conditions: { weather?: string | null; advisories?: string[] } | null
  calendar: 'none' | 'synced' | 'drifted'
}
export type Feature = { feature: string; value: string; status: string; wanted?: boolean }
export type Nearby = { place_id: string; name: string; travel_min: number; estimate: boolean; open: boolean | null; fit: number; matches: string[]; flags: string[]; addable: boolean; meal?: boolean }
export type Suggestions = {
  place_id: string
  play: Feature[]
  practical: Feature[]
  timely: { sunrise?: string; sunset?: string; date?: string; crowd?: { pct: number; bucket: string; day_type: string } }
  nearby: Nearby[]
  similar: Nearby[]
  budget_min: number
  next: Stop | null
}
export type CalChange = { op: 'create' | 'update' | 'delete'; stop: string; event_id?: string; after?: { summary: string; start: { dateTime: string }; end: { dateTime: string } } }
export type CalPreview = { state: 'none' | 'synced' | 'drifted'; connected: boolean; calendar: { create: boolean; summary: string | null }; changes: CalChange[]; preview_hash: string }
export type CalResult = { applied: number; failed: { change: CalChange; error: string } | null; not_done: CalChange[]; state: string }

const base = (id: string) => `/api/harness/sessions/${id}`
const post = <T>(url: string, body: unknown) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(json<T>)

export const loadToday = (id: string, day?: number) => fetch(`${base(id)}/today${day ? `?day=${day}` : ''}`).then(json<TodayView>)
export const loadSuggestions = (id: string, place: string, similar = false) => fetch(`${base(id)}/companion/suggest?place=${encodeURIComponent(place)}${similar ? '&similar=1' : ''}`).then(json<Suggestions>)
export const companion = <T = unknown>(id: string, operation: 'checkin' | 'skip' | 'rate' | 'add' | 'adjust', payload: Record<string, unknown>) => post<T>(`${base(id)}/companion`, { operation, ...payload })
export const searchPlaces = (q: string) => fetch(`/api/harness/places?q=${encodeURIComponent(q)}`).then(json<{ id: string; name: string; category: string | null }[]>)

export const calendarPreview = (journey: string) => fetch(`/api/harness/calendar/preview?journey=${journey}`).then(json<CalPreview>)
export async function calendarApply(journey: string, preview_hash: string): Promise<{ result?: CalResult; stale?: CalPreview }> {
  const res = await fetch('/api/harness/calendar/apply', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ journey, preview_hash }) })
  if (res.status === 409) {
    const body = await res.json().catch(() => ({}))
    if (body.preview) return { stale: body.preview }
  }
  return { result: await json<CalResult>(res) }
}
export const calendarDisconnect = (delete_calendar: boolean) => post<{ disconnected: boolean; calendars_deleted: number }>('/api/harness/calendar/disconnect', { delete_calendar })
export const calendarConnectHref = (next: string) => `/api/auth/google/start?purpose=calendar&next=${encodeURIComponent(next)}`
